import hmac
import json
import logging
import random
import string
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, Literal, Optional, Tuple, cast

import attr
import flask
import werkzeug.exceptions
from dateutil.parser import parse

from impbot.connections import twitch
from impbot.core import base, data, web
from impbot.core.base import EventCallback
from impbot.util import twitch_util

logger = logging.getLogger(__name__)


class TwitchEventSubEvent(base.Event):
    pass


class StreamStartedEvent(TwitchEventSubEvent):
    pass


class StreamEndedEvent(TwitchEventSubEvent):
    pass


@attr.s(auto_attribs=True)
class StreamChangedEvent(TwitchEventSubEvent):
    title: Optional[str]
    category: Optional[str]


@attr.s(auto_attribs=True)
class NewFollowerEvent(TwitchEventSubEvent):
    follower_name: str
    time: datetime


@attr.s(auto_attribs=True)
class Bits(TwitchEventSubEvent):
    user: Optional[twitch.TwitchUser]  # None for anonymous events.
    bits_used: int
    chat_message: str


SubTier = Literal['Tier 1', 'Tier 2', 'Tier 3']

# Mapping from the strings used in the API to human-readable English names.
SUB_TIERS = cast(Dict[str, SubTier], {
    '1000': 'Tier 1',
    '2000': 'Tier 2',
    '3000': 'Tier 3',
})


@attr.s(auto_attribs=True)
class Subscription(TwitchEventSubEvent):
    user: Optional[twitch.TwitchUser]  # None for anonymous events.
    sub_tier: SubTier
    is_gift: bool


@attr.s(auto_attribs=True)
class SubscriptionMessage(TwitchEventSubEvent):
    user: Optional[twitch.TwitchUser]  # None for anonymous events.
    sub_tier: SubTier
    cumulative_months: int
    streak_months: Optional[int]  # None if the user declines to show it.
    message: str


@attr.s(auto_attribs=True)
class GiftSubscription(TwitchEventSubEvent):
    # For a TwitchEventSubEvent, `user` is always the user who took some action. For a gift, it's
    # the donor, not the new subscriber!  TODO: This was a carry-over, consider renaming it.
    user: Optional[twitch.TwitchUser]  # None for anonymous events.
    total: int  # The number of subscriptions in the gift.
    sub_tier: SubTier


@attr.s(auto_attribs=True)
class PointsRewardRedemption(TwitchEventSubEvent):
    user: Optional[twitch.TwitchUser]  # None for anonymous events.
    reward_title: str
    reward_prompt: str
    cost: int
    user_input: Optional[str]  # None if the reward doesn't include any.
    status: Literal['unknown', 'unfulfilled', 'fulfilled', 'canceled']


class TwitchEventSubConnection(base.Connection):
    def __init__(self, reply_conn: base.ChatConnection, util: twitch_util.TwitchUtil):
        self.reply_conn = reply_conn
        self.twitch_util = util

        self._startup_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._on_event: Optional[base.EventCallback] = None  # Set in run().
        self._secret = ''

    def run(self, on_event: EventCallback) -> None:
        db = data.Namespace('impbot.connections.twitch_eventsub.TwitchEventSubConnection')
        try:
            self._secret = db.get('secret')
        except KeyError:
            self._secret = ''.join(random.choices(string.ascii_letters + string.digits, k=64))
            db.set('secret', self._secret)
        self._on_event = on_event
        self._startup_event.set()

        id = str(self.twitch_util.get_channel_id(self.twitch_util.streamer_username))
        types = ['stream.online', 'stream.offline', 'channel.update', 'channel.follow',
                 'channel.cheer', 'channel.subscribe', 'channel.subscription.message',
                 'channel.subscription.gift', 'channel.channel_points_custom_reward_redemption.add']
        self._ensure_subscribed([(type, {'broadcaster_user_id': id}) for type in types])

        # Everything else happens on web requests, so just wait for shutdown.
        self._shutdown_event.wait()

    def shutdown(self) -> None:
        self._shutdown_event.set()

    def _ensure_subscribed(self, subs: Iterable[Tuple[str, dict]]) -> None:
        body = self.twitch_util.helix_get('eventsub/subscriptions', token_type='app')
        for type, condition in subs:
            for sub in body['data']:
                if not (sub['type'] == type and _condition_matches(sub['condition'], condition)):
                    continue
                if sub['status'] != 'enabled':
                    logger.warning('Found subscription with status %s, trying to resubscribe: %s',
                                   sub['status'], sub)
                    self._subscribe(type, condition)
                break
            else:
                self._subscribe(type, condition)

    def _subscribe(self, type: str, condition: dict) -> None:
        callback = flask.url_for(
            'TwitchEventSubConnection.callback', _external=True, _scheme='https')
        self.twitch_util.helix_post(
            'eventsub/subscriptions',
            {
                'type': type,
                'version': '1',
                'condition': condition,
                'transport': {
                    'method': 'webhook',
                    'callback': callback,
                    'secret': self._secret,
                }
            },
            token_type='app',
            expected_status=202)

    @web.url('/eventsub/callback', methods=['POST'])
    def callback(self):
        # If we just started up (but the subscriptions are still enabled from a previous run) the
        # event callback and secret might not be populated yet, so wait until they are.
        self._startup_event.wait()

        # We need the verbatim request body, with original whitespace, to check the message
        # signature. So instead of going straight to request.json() we pull the body data ourselves
        # first.
        data = self._safe_get_data()
        self._verify_signature(data)

        message_type = flask.request.headers['Twitch-Eventsub-Message-Type']
        body = json.loads(data)
        if message_type == 'webhook_callback_verification':
            # Subscription confirmation: respond by returning the challenge.
            return body['challenge']

        if message_type == 'revocation':
            logger.error('Subscription revoked (%s): %s %s', body['subscription']['status'],
                         body['subscription']['type'], body['subscription']['condition'])
            return ''

        if message_type == 'notification':
            self._on_event(self._parse_notification(body['subscription']['type'], body['event']))
            return ''

        logger.error('Unexpected message_type %s, body %s', message_type, body)
        raise werkzeug.exceptions.BadRequest

    def _safe_get_data(self) -> bytes:
        if flask.request.content_length is None:
            logger.error('No Content-Length header, rejecting')
            raise werkzeug.exceptions.LengthRequired
        if flask.request.content_length > 2 ** 20:
            logger.error(
                'Content length %d greater than 1 MB, rejecting', flask.request.content_length)
            raise werkzeug.exceptions.RequestEntityTooLarge
        return flask.request.get_data()

    def _verify_signature(self, data) -> None:
        signature = flask.request.headers['Twitch-Eventsub-Message-Signature']

        id = flask.request.headers['Twitch-Eventsub-Message-Id']
        timestamp = flask.request.headers['Twitch-Eventsub-Message-Timestamp']
        computed_signature = hmac.digest(self._secret.encode(), (id + timestamp).encode() + data,
                                         'sha256')
        if signature != 'sha256=' + computed_signature.hex():
            logger.error('id: %s\ntimestamp: %s\nbody: %r\n'
                         'Computed signature sha256=%s,\nreceived signature %s',
                         id, timestamp, data, computed_signature.hex(), signature)
            raise werkzeug.exceptions.Forbidden('Signature mismatch')

    def _parse_notification(self, sub_type: str, event: Dict[str, Any]) -> TwitchEventSubEvent:
        if sub_type == 'stream.online':
            return StreamStartedEvent(self.reply_conn)

        if sub_type == 'stream.offline':
            return StreamEndedEvent(self.reply_conn)

        if sub_type == 'channel.update':
            return StreamChangedEvent(self.reply_conn, event['title'], event['category_name'])

        if sub_type == 'channel.follow':
            return NewFollowerEvent(
                self.reply_conn, event['user_name'], parse(event['followed_at']))

        if sub_type == 'channel.cheer':
            return Bits(self.reply_conn, _event_user(event), event['bits'], event['message'])

        if sub_type == 'channel.subscribe':
            return Subscription(
                self.reply_conn, _event_user(event), sub_tier=SUB_TIERS[event['tier']],
                is_gift=event['is_gift'])

        if sub_type == 'channel.subscription.message':
            return SubscriptionMessage(
                self.reply_conn, _event_user(event), sub_tier=SUB_TIERS[event['tier']],
                cumulative_months=event['cumulative_months'], streak_months=event['streak_months'],
                message=event['message']['text'])

        if sub_type == 'channel.subscription.gift':
            return GiftSubscription(
                self.reply_conn, _event_user(event), total=event['total'],
                sub_tier=SUB_TIERS[event['tier']])

        if sub_type == 'channel.channel_points_custom_reward_redemption.add':
            return PointsRewardRedemption(
                self.reply_conn, _event_user(event), reward_title=event['reward']['title'],
                reward_prompt=event['reward']['prompt'], cost=int(event['reward']['cost']),
                user_input=event['user_input'] if event['user_input'] else None,
                status=event['status'])

        logger.error('Unexpected event for subscription type %s: %s', sub_type, event)
        raise werkzeug.exceptions.BadRequest


def _event_user(event: Dict[str, Any]) -> Optional[twitch.TwitchUser]:
    if event.get('is_anonymous', False):
        return None
    return twitch.TwitchUser(name=event['user_login'], display_name=event['user_name'])


def _condition_matches(found: Dict[str, str], expected: Dict[str, str]) -> bool:
    # Sometimes optional keys are omitted, but Twitch passes them back present, with a '' value.
    # This function evaluates whether two dicts are equal, ignoring keys absent in one side and
    # ''-valued on the other.
    for key in expected.keys() | found.keys():
        if expected.get(key, '') != found.get(key, ''):
            return False
    return True
