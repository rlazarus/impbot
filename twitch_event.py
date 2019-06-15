import asyncio
import json
import logging
import random
import threading
from typing import Optional, Dict, Any
from urllib import parse

import attr
import requests
import websockets

import bot
import data
import secret
import twitch_util

logger = logging.getLogger(__name__)

@attr.s(auto_attribs=True)
class TwitchEvent(bot.Event):
    user: Optional[bot.User]  # None for anonymous events.


@attr.s(auto_attribs=True)
class Bits(TwitchEvent):
    bits_used: int
    chat_message: str


@attr.s(auto_attribs=True)
class Subscription(TwitchEvent):
    sub_plan: str  # "Twitch Prime", "Tier 1", "Tier 2", or "Tier 3".
    cumulative_months: int
    streak_months: Optional[int]  # None if the user declines to show it.
    message: str


@attr.s(auto_attribs=True)
class GiftSubscription(Subscription):
    # For a TwitchEvent, `username` is always the user who took some action. For
    # a gift, it's the donor, not the new subscriber!
    recipient_username: str


class TwitchEventConnection(bot.Connection):
    def __init__(self, streamer_username: str, redirect_uri: str) -> None:
        self.data = data.Namespace("TwitchEventConnection")
        self.streamer_username = streamer_username
        self.redirect_uri = redirect_uri
        self.event_loop = asyncio.new_event_loop()
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        # threading.Event, not asyncio.Event: We need it for communicating
        # between threads, not between coroutines.
        self.shutdown_event = threading.Event()

        asyncio.set_event_loop(self.event_loop)

    def say(self, text: str) -> None:
        raise NotImplementedError("TwitchEventConnection doesn't have chat"
                                  "functionality -- use TwitchChatConnection.")

    def run(self, on_event: bot.EventCallback) -> None:
        if not self.data.exists("access_token"):
            self.oauth_authorize()

        # The websockets library wants to be called asynchronously, so bridge
        # into async code here.
        self.event_loop.run_until_complete(self.run_coro(on_event))

    async def run_coro(self, on_event: bot.EventCallback) -> None:
        while not self.shutdown_event.is_set():
            async with websockets.connect("wss://pubsub-edge.twitch.tv",
                                          close_timeout=1) as self.websocket:
                response = await self.subscribe(self.websocket)
                if response["error"] == "ERR_BADAUTH":
                    self.oauth_refresh()
                    response = await self.subscribe(self.websocket)
                    if response["error"] == "ERR_BADAUTH":
                        raise bot.ServerError("Two BADAUTH errors, giving up.")

                ping_task = asyncio.create_task(_ping_forever(self.websocket))

                try:
                    async for message in self.websocket:
                        logger.debug(message)
                        body = json.loads(message)
                        if body["type"] == "RECONNECT":
                            logger.info("Reconnecting by request...")
                            break
                        handle_message(on_event, body)
                except websockets.ConnectionClosed:
                    pass

                ping_task.cancel()

    async def subscribe(self, websocket: websockets.WebSocketClientProtocol) \
            -> Dict[str, str]:
        channel_id = twitch_util.get_channel_id(self.streamer_username)
        nonce = twitch_util.nonce()

        await websocket.send(json.dumps({
            "type": "LISTEN",
            "nonce": nonce,
            "data": {
                "topics": [
                    f"channel-bits-events-v2.{channel_id}",
                    f"channel-subscribe-events-v1.{channel_id}",
                ],
                "auth_token": self.data.get("access_token"),
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
            raise bot.ServerError("Websocket closed without response.")

        if response["type"] != "RESPONSE":
            raise bot.ServerError(f"Bad pubsub response: {response}")
        return response

    def oauth_authorize(self) -> None:
        # TODO: Replace this with a proper authorization flow, which requires a
        #   persistent web service shared by all Impbot installations -- that
        #   service should be the host for the OAuth redirect URI, and should
        #   hold the Twitch client secret. Without that service, the access
        #   code has to be fished out of HTTP logs and entered by hand.
        scopes = ["bits:read", "channel_subscriptions"]
        params = parse.urlencode({"client_id": secret.TWITCH_CLIENT_ID,
                                  "redirect_uri": self.redirect_uri,
                                  "response_type": "code",
                                  "scope": " ".join(scopes)})
        access_code = input(
            f"While logged into Twitch as {self.streamer_username}, please "
            f"visit: https://id.twitch.tv/oauth2/authorize?{params}\n"
            f"Access code: ")
        self._oauth_fetch({"grant_type": "authorization_code",
                           "code": access_code,
                           "redirect_uri": self.redirect_uri})
        logger.info("Twitch OAuth: Authorized!")

    def oauth_refresh(self) -> None:
        self._oauth_fetch({"grant_type": "refresh_token",
                           "refresh_token": self.data.get("refresh_token")})
        logger.info("Twitch OAuth: Refreshed!")

    def _oauth_fetch(self, params: Dict[str, str]) -> None:
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": secret.TWITCH_CLIENT_ID,
                "client_secret": secret.TWITCH_CLIENT_SECRET,
                **params
            })
        if response.status_code != 200:
            raise bot.ServerError(response)
        body = json.loads(response.text)
        if "error" in body:
            raise bot.ServerError(body)
        self.data.set("access_token", body["access_token"])
        self.data.set("refresh_token", body["refresh_token"])

    def shutdown(self) -> None:
        self.shutdown_event.set()
        if self.websocket:
            asyncio.run_coroutine_threadsafe(self.websocket.close(),
                                             self.event_loop)


def handle_message(on_event: bot.EventCallback, body: Dict[str, Any]):
    if body["type"] == "PONG":
        return
    if body["type"] != "MESSAGE":
        raise bot.ServerError(body)
    topic = body["data"]["topic"]
    msg = json.loads(body["data"]["message"])
    if "-bits-" in topic:
        mdata = msg["data"]
        user = bot.User(mdata["user_name"]) if "user_name" in mdata else None
        on_event(Bits(user, mdata["bits_used"], mdata["chat_message"]))
    elif "-subscribe-" in topic:
        if "recipient_user_name" in msg:
            user = bot.User(msg["user_name"]) if "user_name" in msg else None
            on_event(GiftSubscription(
                user, SUB_PLANS[msg["sub_plan"]], msg["months"], None,
                msg["sub_message"]["message"], msg["recipient_user_name"]))
        else:
            on_event(Subscription(
                bot.User(msg["user_name"]), SUB_PLANS[msg["sub_plan"]],
                msg["cumulative_months"], msg.get("streak_months", None),
                msg["sub_message"]["message"]))


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
SUB_PLANS = {
    "Prime": "Twitch Prime",
    "1000": "Tier 1",
    "2000": "Tier 2",
    "3000": "Tier 3",
}
