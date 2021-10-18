import hmac
import json
import logging
import random
import string
import threading
from typing import Iterable, Optional, Tuple

import flask
import werkzeug.exceptions
from dateutil.parser import parse

from impbot.connections import twitch_webhook
from impbot.connections.twitch_webhook import NewFollowerEvent, \
    StreamChangedEvent, StreamEndedEvent, StreamStartedEvent
from impbot.core import base, web, data
from impbot.core.base import EventCallback
from impbot.util import twitch_util

logger = logging.getLogger(__name__)


class TwitchEventSubConnection(base.Connection):
    # TODO: This replaces TwitchWebhookConnection, which speaks a now-deprecated
    #  protocol. Move the TwitchWebhookEvent hierarchy into this module, then
    #  delete twitch_webhook.
    def __init__(self, reply_conn: base.ChatConnection,
                 util: twitch_util.TwitchUtil):
        self.reply_conn = reply_conn
        self.twitch_util = util

        self._startup_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._on_event: Optional[base.EventCallback] = None  # Set in run().
        self._secret = ""

    def run(self, on_event: EventCallback) -> None:
        db = data.Namespace(
            "impbot.connections.twitch_eventsub.TwitchEventSubConnection")
        try:
            self._secret = db.get("secret")
        except KeyError:
            self._secret = "".join(
                random.choices(string.ascii_letters + string.digits, k=64))
            db.set("secret", self._secret)
        self._on_event = on_event
        self._startup_event.set()

        id = str(
            self.twitch_util.get_channel_id(self.twitch_util.streamer_username))
        self._ensure_subscribed([
            ("stream.online", {"broadcaster_user_id": id}),
            ("stream.offline", {"broadcaster_user_id": id}),
            ("channel.update", {"broadcaster_user_id": id}),
            ("channel.follow", {"broadcaster_user_id": id}),
        ])

        # Everything else happens on web requests, so just wait for shutdown.
        self._shutdown_event.wait()

    def shutdown(self) -> None:
        self._shutdown_event.set()

    def _ensure_subscribed(self, subs: Iterable[Tuple[str, dict]]) -> None:
        body = self.twitch_util.helix_get("eventsub/subscriptions", params={},
                                          token_type="app")
        for type, condition in subs:
            for sub in body["data"]:
                if sub["type"] != type or sub["condition"] != condition:
                    continue
                if sub["status"] != "enabled":
                    logging.warning("Found subscription with status %s, trying "
                                    "to resubscribe: %s", sub["status"], sub)
                    self._subscribe(type, condition)
                break
            else:
                self._subscribe(type, condition)

    def _subscribe(self, type: str, condition: dict) -> None:
        callback = flask.url_for("TwitchEventSubConnection.callback",
                                 _external=True, _scheme="https")
        self.twitch_util.helix_post(
            "eventsub/subscriptions",
            {
                "type": type,
                "version": "1",
                "condition": condition,
                "transport": {
                    "method": "webhook",
                    "callback": callback,
                    "secret": self._secret,
                }
            },
            token_type="app",
            expected_status=202)

    @web.url("/eventsub/callback", methods=["POST"])
    def callback(self):
        # If we just started up (but the subscriptions are still enabled from a
        # previous run) the event callback and secret might not be populated
        # yet, so wait until they are.
        self._startup_event.wait()

        # We need the verbatim request body, with original whitespace, to check
        # the message signature. So instead of going straight to request.json()
        # we pull the body data ourselves first.
        data = self._safe_get_data()
        self._verify_signature(data)

        message_type = flask.request.headers["Twitch-Eventsub-Message-Type"]
        body = json.loads(data)
        if message_type == "webhook_callback_verification":
            # Subscription confirmation: respond by returning the challenge.
            return body["challenge"]

        if message_type == "revocation":
            logging.error("Subscription revoked (%s): %s %s",
                          body["subscription"]["status"],
                          body["subscription"]["type"],
                          body["subscription"]["condition"])
            return ""

        if message_type == "notification":
            self._on_event(self._parse_notification(
                body["subscription"]["type"], body["event"]))
            return ""

        logger.error("Unexpected message_type %s, body %s", message_type, body)
        raise werkzeug.exceptions.BadRequest

    def _safe_get_data(self) -> bytes:
        if flask.request.content_length is None:
            logging.error("No Content-Length header, rejecting")
            raise werkzeug.exceptions.LengthRequired
        if flask.request.content_length > 2 ** 20:
            logging.error("Content length %d greater than 1 MB, rejecting",
                          flask.request.content_length)
            raise werkzeug.exceptions.RequestEntityTooLarge
        return flask.request.get_data()

    def _verify_signature(self, data) -> None:
        signature = flask.request.headers["Twitch-Eventsub-Message-Signature"]

        id = flask.request.headers["Twitch-Eventsub-Message-Id"]
        timestamp = flask.request.headers["Twitch-Eventsub-Message-Timestamp"]
        computed_signature = hmac.digest(self._secret.encode(),
                                         (id + timestamp).encode() + data,
                                         "sha256")
        if signature != "sha256=" + computed_signature.hex():
            logging.error(
                "id: %s\ntimestamp: %s\nbody: %r\n"
                "Computed signature sha256=%s,\n"
                "received signature %s",
                id, timestamp, data, computed_signature.hex(), signature)
            raise werkzeug.exceptions.Forbidden("Signature mismatch")

    def _parse_notification(self, sub_type,
                            event) -> twitch_webhook.TwitchWebhookEvent:
        if sub_type == "stream.online":
            # TODO: The old webhook subscription would provide title and
            #  game information with the event, so we make a separate
            #  roundtrip for it here for compatibility. Let's phase it out.
            stream_data = self.twitch_util.get_stream_data(
                username=self.twitch_util.streamer_username)
            return StreamStartedEvent(self.reply_conn, stream_data.get("title"),
                                      stream_data.get("game"))

        if sub_type == "stream.offline":
            return StreamEndedEvent(self.reply_conn)

        if sub_type == "channel.update":
            return StreamChangedEvent(self.reply_conn, event["title"],
                                      event["category_name"])

        if sub_type == "channel.follow":
            return NewFollowerEvent(
                self.reply_conn, event["user_name"],
                parse(event["followed_at"]))

        logger.error("Unexpected event for subscription type %s: %s",
                     sub_type, event)
        raise werkzeug.exceptions.BadRequest
