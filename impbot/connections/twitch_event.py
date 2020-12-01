import asyncio
import datetime
import json
import logging
import random
import threading
from typing import Optional, Dict, Any, Literal, cast

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
class Bits(TwitchEvent):
    bits_used: int
    chat_message: str


SubPlan = Literal["Twitch Prime", "Tier 1", "Tier 2", "Tier 3"]


@attr.s(auto_attribs=True)
class Subscription(TwitchEvent):
    sub_plan: SubPlan
    cumulative_months: int
    streak_months: Optional[int]  # None if the user declines to show it.
    message: str


@attr.s(auto_attribs=True)
class GiftSubscription(Subscription):
    # For a TwitchEvent, `username` is always the user who took some action. For
    # a gift, it's the donor, not the new subscriber!
    recipient_username: twitch.TwitchUser


@attr.s(auto_attribs=True)
class PointsReward(TwitchEvent):
    reward_title: str
    reward_prompt: str
    cost: int
    user_input: Optional[str]  # None if the reward doesn't include any.
    status: Literal["FULFILLED", "UNFULFILLED"]


@attr.s(auto_attribs=True)
class ModAction(TwitchEvent):
    target: twitch.TwitchUser


@attr.s(auto_attribs=True)
class Ban(ModAction):
    reason: str  # "" if the moderator didn't provide one.


@attr.s(auto_attribs=True)
class Unban(ModAction):
    pass


@attr.s(auto_attribs=True)
class Timeout(ModAction):
    duration: datetime.timedelta
    reason: str  # "" if the moderator didn't provide one.


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
        # threading.Event, not asyncio.Event: We need it for communicating
        # between threads, not between coroutines.
        self.shutdown_event = threading.Event()

        asyncio.set_event_loop(self.event_loop)

    def run(self, on_event: base.EventCallback) -> None:
        self.twitch_util.oauth.maybe_authorize()

        # The websockets library wants to be called asynchronously, so bridge
        # into async code here.
        self.event_loop.run_until_complete(self.run_coro(on_event))

    async def run_coro(self, on_event: base.EventCallback) -> None:
        while not self.shutdown_event.is_set():
            async with websockets.connect("wss://pubsub-edge.twitch.tv",
                                          close_timeout=1) as self.websocket:
                response = await self.subscribe(self.websocket)
                if response["error"] == "ERR_BADAUTH":
                    self.twitch_util.oauth.refresh()
                    response = await self.subscribe(self.websocket)
                    if response["error"] == "ERR_BADAUTH":
                        raise base.ServerError("Two BADAUTH errors, giving up.")

                ping_task = asyncio.create_task(_ping_forever(self.websocket))

                try:
                    async for message in self.websocket:
                        logger.debug(message)
                        body = json.loads(message)
                        if body["type"] == "RECONNECT":
                            logger.info("Reconnecting by request...")
                            break
                        self.handle_message(on_event, body)
                except websockets.ConnectionClosed:
                    pass

                ping_task.cancel()

    async def subscribe(
            self,
            websocket: websockets.WebSocketClientProtocol) -> Dict[str, str]:
        channel_id = self.twitch_util.get_channel_id(
            self.twitch_util.streamer_username)
        nonce = twitch_util.nonce()

        await websocket.send(json.dumps({
            "type": "LISTEN",
            "nonce": nonce,
            "data": {
                "topics": [
                    f"channel-bits-events-v2.{channel_id}",
                    f"channel-points-channel-v1.{channel_id}",
                    f"channel-subscribe-events-v1.{channel_id}",
                    f"chat_moderator_actions.{channel_id}",
                ],
                "auth_token": self.twitch_util.oauth.access_token,
            }
        }))

        # Keep listening until we get a response with the correct nonce. It's
        # generally the first one.
        async for message in websocket:
            response = json.loads(message)
            logger.debug(response)
            if response["nonce"] == nonce:
                break
        else:
            raise base.ServerError("Websocket closed without response.")

        if response["type"] != "RESPONSE":
            raise base.ServerError(f"Bad pubsub response: {response}")
        return response

    def shutdown(self) -> None:
        self.shutdown_event.set()
        if self.websocket:
            asyncio.run_coroutine_threadsafe(self.websocket.close(),
                                             self.event_loop)

    def handle_message(self, on_event: base.EventCallback,
                       body: Dict[str, Any]) -> None:
        if body["type"] == "PONG":
            return
        if body["type"] != "MESSAGE":
            raise base.ServerError(body)
        topic = body["data"]["topic"]
        msg = json.loads(body["data"]["message"])
        if "-bits-" in topic:
            mdata = msg["data"]
            username = mdata.get("user_name", None)
            user = self.twitch_user(username) if username else None
            on_event(
                Bits(self.reply_conn, user, mdata["bits_used"],
                     mdata["chat_message"]))
        elif "-subscribe-" in topic:
            if "recipient_user_name" in msg:
                username = msg.get("user_name", None)
                user = self.twitch_user(username) if username else None
                on_event(GiftSubscription(
                    self.reply_conn, user, SUB_PLANS[msg["sub_plan"]],
                    msg["months"], None, msg["sub_message"]["message"],
                    self.twitch_user(msg["recipient_user_name"])))
            else:
                on_event(Subscription(
                    self.reply_conn, self.twitch_user(msg["user_name"]),
                    SUB_PLANS[msg["sub_plan"]], msg["cumulative_months"],
                    msg.get("streak_months", None),
                    msg["sub_message"]["message"]))
        elif "-points-channel-" in topic:
            redemption = msg["data"]["redemption"]
            user = twitch.TwitchUser(
                redemption["user"]["login"], None,
                redemption["user"]["display_name"], None, None)
            reward = redemption["reward"]
            on_event(PointsReward(
                self.reply_conn, user, reward["title"], reward["prompt"],
                reward["cost"], redemption.get("user_input"),
                redemption["status"]))
        elif "_moderator_actions" in topic:
            mdata = msg["data"]
            if (mdata["moderation_action"] not in
                    {"ban", "unban", "timeout", "untimeout", "delete"}):
                logger.info(f"Ignoring mod action {mdata['moderation_action']}")
                return
            user = self.twitch_user(mdata["created_by"], is_moderator=True)
            if mdata["moderation_action"] == "ban":
                [target_username, reason] = mdata["args"]
                on_event(Ban(self.reply_conn, user,
                             self.twitch_user(target_username), reason))
            elif mdata["moderation_action"] == "unban":
                [target_username] = mdata["args"]
                on_event(Unban(self.reply_conn, user,
                               self.twitch_user(target_username)))
            elif mdata["moderation_action"] == "timeout":
                [target_username, duration_sec, reason] = mdata["args"]
                on_event(Timeout(
                    self.reply_conn, user, self.twitch_user(target_username),
                    datetime.timedelta(seconds=int(duration_sec)), reason))
            elif mdata["moderation_action"] == "untimeout":
                [target_username] = mdata["args"]
                on_event(Untimeout(self.reply_conn, user,
                                   self.twitch_user(target_username)))
            elif mdata["moderation_action"] == "delete":
                [target_username, message_text, message_id] = mdata["args"]
                on_event(Delete(
                    self.reply_conn, user, self.twitch_user(target_username),
                    message_text))

    def twitch_user(self, username,
                    is_moderator: Optional[bool] = None) -> twitch.TwitchUser:
        return twitch.TwitchUser(
            name=username,
            display_name=self.twitch_util.get_display_name(username),
            is_moderator=is_moderator)


async def _ping_forever(websocket: websockets.WebSocketCommonProtocol) -> None:
    try:
        while websocket.open:
            logger.debug("Pubsub PING")
            await websocket.send(json.dumps({"type": "PING"}))
            # Add some jitter, but ping at least every five minutes.
            await asyncio.sleep(295 + random.randint(-5, 5))
    except asyncio.CancelledError:
        return


# Mapping from the strings used in the API to human-readable English names.
SUB_PLANS = cast(Dict[str, SubPlan], {
    "Prime": "Twitch Prime",
    "1000": "Tier 1",
    "2000": "Tier 2",
    "3000": "Tier 3",
})
