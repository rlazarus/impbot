import asyncio
import datetime
import json
import logging
import random
import threading
from typing import Any, Dict, Optional

import attr
import websockets

from impbot.connections import twitch
from impbot.core import base
from impbot.util import twitch_util

logger = logging.getLogger(__name__)


@attr.s(auto_attribs=True)
class TwitchEvent(base.Event):
    user: Optional[twitch.TwitchUser]  # None for anonymous events.


@attr.s(auto_attribs=True)
class ModAction(TwitchEvent):
    target: twitch.TwitchUser


@attr.s(auto_attribs=True)
class Ban(ModAction):
    reason: str  # '' if the moderator didn't provide one.


@attr.s(auto_attribs=True)
class Unban(ModAction):
    pass


@attr.s(auto_attribs=True)
class Timeout(ModAction):
    duration: datetime.timedelta
    reason: str  # '' if the moderator didn't provide one.


@attr.s(auto_attribs=True)
class Untimeout(ModAction):
    pass


@attr.s(auto_attribs=True)
class Delete(ModAction):
    message_text: str


class TwitchEventConnection(base.Connection):
    def __init__(self, util: twitch_util.TwitchUtil,
                 reply_conn: Optional[base.ChatConnection] = None) -> None:
        self.reply_conn = reply_conn
        self.event_loop = asyncio.new_event_loop()
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.twitch_util = util
        # threading.Event, not asyncio.Event: We need it for communicating between threads, not
        # between coroutines.
        self.shutdown_event = threading.Event()

        asyncio.set_event_loop(self.event_loop)

    def run(self, on_event: base.EventCallback) -> None:
        self.twitch_util.oauth.maybe_authorize()

        # The websockets library wants to be called asynchronously, so bridge into async code here.
        self.event_loop.run_until_complete(self.run_coro(on_event))

    async def run_coro(self, on_event: base.EventCallback) -> None:
        while not self.shutdown_event.is_set():
            async with websockets.connect(
                    'wss://pubsub-edge.twitch.tv', close_timeout=1) as self.websocket:
                response = await self.subscribe(self.websocket)
                if response['error'] == 'ERR_BADAUTH':
                    self.twitch_util.oauth.refresh()
                    response = await self.subscribe(self.websocket)
                    if response['error'] == 'ERR_BADAUTH':
                        raise base.ServerError('Two BADAUTH errors, giving up.')

                ping_task = asyncio.create_task(_ping_forever(self.websocket))

                try:
                    async for message in self.websocket:
                        logger.debug(message)
                        body = json.loads(message)
                        if body['type'] == 'RECONNECT':
                            logger.info('Reconnecting by request...')
                            break
                        self.handle_message(on_event, body)
                except websockets.ConnectionClosed:
                    pass

                ping_task.cancel()

    async def subscribe(self, websocket: websockets.WebSocketClientProtocol) -> Dict[str, str]:
        channel_id = self.twitch_util.get_channel_id(
            self.twitch_util.streamer_username)
        nonce = twitch_util.nonce()

        await websocket.send(json.dumps({
            'type': 'LISTEN',
            'nonce': nonce,
            'data': {
                'topics': [
                    f'chat_moderator_actions.{channel_id}',
                ],
                'auth_token': self.twitch_util.oauth.access_token,
            }
        }))

        # Keep listening until we get a response with the correct nonce. It's generally the first
        # one.
        async for message in websocket:
            response = json.loads(message)
            logger.debug(response)
            if response['nonce'] == nonce:
                break
        else:
            raise base.ServerError('Websocket closed without response.')

        if response['type'] != 'RESPONSE':
            raise base.ServerError(f'Bad pubsub response: {response}')
        return response

    def shutdown(self) -> None:
        self.shutdown_event.set()
        if self.websocket:
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.event_loop)

    def handle_message(self, on_event: base.EventCallback, body: Dict[str, Any]) -> None:
        if body['type'] == 'PONG':
            return
        if body['type'] != 'MESSAGE':
            raise base.ServerError(body)
        topic = body['data']['topic']
        msg = json.loads(body['data']['message'])
        if '_moderator_actions' not in topic:
            return
        mdata = msg['data']
        if mdata['moderation_action'] not in {'ban', 'unban', 'timeout', 'untimeout', 'delete'}:
            logger.info(f'Ignoring mod action {mdata["moderation_action"]}')
            return
        user = self.twitch_user(mdata['created_by'], is_moderator=True)
        if mdata['moderation_action'] == 'ban':
            [target_username, reason] = mdata['args']
            on_event(Ban(self.reply_conn, user, self.twitch_user(target_username), reason))
        elif mdata['moderation_action'] == 'unban':
            [target_username] = mdata['args']
            on_event(Unban(self.reply_conn, user, self.twitch_user(target_username)))
        elif mdata['moderation_action'] == 'timeout':
            [target_username, duration_sec, reason] = mdata['args']
            on_event(Timeout(
                self.reply_conn, user, self.twitch_user(target_username),
                datetime.timedelta(seconds=int(duration_sec)), reason))
        elif mdata['moderation_action'] == 'untimeout':
            [target_username] = mdata['args']
            on_event(Untimeout(self.reply_conn, user, self.twitch_user(target_username)))
        elif mdata['moderation_action'] == 'delete':
            [target_username, message_text, message_id] = mdata['args']
            on_event(
                Delete(self.reply_conn, user, self.twitch_user(target_username), message_text))

    def twitch_user(self, username, is_moderator: Optional[bool] = None) -> twitch.TwitchUser:
        return twitch.TwitchUser(
            name=username, display_name=self.twitch_util.get_display_name(username),
            is_moderator=is_moderator)


async def _ping_forever(websocket: websockets.WebSocketCommonProtocol) -> None:
    try:
        while websocket.open:
            logger.debug('Pubsub PING')
            await websocket.send(json.dumps({'type': 'PING'}))
            # Add some jitter, but ping at least every five minutes.
            await asyncio.sleep(295 + random.randint(-5, 5))
    except asyncio.CancelledError:
        return


