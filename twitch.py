import asyncio
import json
import logging
import sys
from typing import Callable, Optional
from urllib import parse

import attr
import requests
import websockets
from irc import client

import bot
import custom
import data
import hello
import irc_connection
import roulette
import secret


@attr.s(auto_attribs=True)
class TwitchEvent(bot.Event):
    username: Optional[str]  # None if anonymous


@attr.s(auto_attribs=True)
class Bits(TwitchEvent):
    bits_used: int
    chat_message: str


@attr.s(auto_attribs=True)
class Subscription(TwitchEvent):
    sub_plan: str  # "Twitch Prime", "Tier 1", "Tier 2", or "Tier 3"
    cumulative_months: int
    streak_months: Optional[int]
    message: str


@attr.s(auto_attribs=True)
class GiftSubscription(Subscription):
    # For a TwitchEvent, `username` is always the user who took some action. For
    # a gift, it's the donor, not the new subscriber!
    recipient_username: str


class TwitchChatConnection(irc_connection.IrcConnection):
    def __init__(self, bot_username: str, oauth_token: str,
                 streamer_username: str) -> None:
        if not oauth_token.startswith("oauth:"):
            oauth_token = "oauth:" + oauth_token
        super().__init__("irc.chat.twitch.tv", 6667, bot_username.lower(),
                         "#" + streamer_username.lower(), password=oauth_token)


class TwitchEventConnection(bot.Connection):
    def __init__(self, streamer_username: str, redirect_uri: str):
        self.data = data.Namespace("TwitchEventConnection")
        self.streamer_username = streamer_username
        self.channel_id = self._get_channel_id(streamer_username)
        self.redirect_uri = redirect_uri

        print(self.channel_id)

    def _get_channel_id(self, streamer_username):
        response = requests.get("https://api.twitch.tv/helix/users",
                                params={"login": streamer_username},
                                headers={"Client-ID": secret.TWITCH_CLIENT_ID})
        if response.status_code != 200:
            raise bot.AdminError(response)
        body = json.loads(response.text)
        if not body["data"]:
            raise bot.AdminError(f"No Twitch channel '{streamer_username}'")
        return body["data"][0]["id"]

    def say(self, text: str) -> None:
        raise NotImplementedError("TwitchEventConnection doesn't have chat"
                                  "functionality -- use TwitchChatConnection.")

    def run(self, callback: Callable[[bot.Event], None]) -> None:
        if self.data.exists("access_token"):
            self.oauth_refresh()
        else:
            self.oauth_authorize()

        # The websockets library wants to be called asynchronously, so bridge
        # into async code here.
        asyncio.set_event_loop(asyncio.new_event_loop())
        asyncio.get_event_loop().run_until_complete(self.run_coro(callback))

    async def run_coro(self, callback: Callable[[bot.Event], None]) -> None:
        url = "wss://pubsub-edge.twitch.tv"
        async with websockets.connect(url) as websocket:
            request = json.dumps({
                "type": "LISTEN",
                "nonce": "dummy-nonce-fixme",
                "data": {
                    "topics": [
                        f"channel-bits-events-v2.{self.channel_id}",
                        f"channel-subscribe-events-v1.{self.channel_id}",
                        # TODO: Is "commerce" donations? (Probably not -- bet we
                        #   need a separate streamlabs connection.)
                        f"channel-commerce-events-v1.{self.channel_id}",
                    ],
                    # TODO: OAuth refresh if necessary.
                    "auth_token": self.data.get("access_token"),
                }
            })
            await websocket.send(request)

            response = await websocket.recv()
            body = json.loads(response)
            print(body)
            if body["type"] != "RESPONSE":
                raise bot.AdminError(f"Bad pubsub response: {body}")
            if body["error"] == "ERR_BADAUTH":
                self.oauth_refresh()
                # TODO: Resend the LISTEN request instead.
                raise bot.AdminError("ERR_BADAUTH, try again.")

            try:
                async for message in websocket:
                    print(message)
                    body = json.loads(message)
                    handle_message(callback, body)
            except websockets.ConnectionClosed:
                pass

    def oauth_authorize(self):
        params = parse.urlencode({
            "client_id": secret.TWITCH_CLIENT_ID,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(["bits:read", "channel_subscriptions"]),
        })
        print(f"While logged into Twitch as {self.streamer_username}, please "
              f"visit: https://id.twitch.tv/oauth2/authorize?{params}")
        access_code = input("Access code: ")
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": secret.TWITCH_CLIENT_ID,
                "client_secret": secret.TWITCH_CLIENT_SECRET,
                "code": access_code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            })
        if response.status_code != 200:
            raise bot.AdminError(response)
        body = json.loads(response.text)
        self.data.set("access_token", body["access_token"])
        self.data.set("refresh_token", body["refresh_token"])
        print("Auth'd!")

    def oauth_refresh(self):
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "grant_type": "refresh_token",
                "refresh_token": self.data.get("refresh_token"),
                "client_id": secret.TWITCH_CLIENT_ID,
                "client_secret": secret.TWITCH_CLIENT_SECRET,
            })
        if response.status_code != 200:
            raise bot.AdminError(response)
        body = json.loads(response.text)
        if "error" in body:
            raise bot.AdminError(body)
        self.data.set("access_token", body["access_token"])
        self.data.set("refresh_token", body["refresh_token"])
        print("Refresh'd!")

    def shutdown(self) -> None:
        pass


def handle_message(callback, body):
    if body["type"] != "MESSAGE":
        raise NotImplementedError(body)
    topic = body["data"]["topic"]
    msg = json.loads(body["data"]["message"])
    if "-bits-" in topic:
        data = msg["data"]
        callback(Bits(data.get("user_name", None), data["bits_used"],
                      data["chat_message"]))
    elif "-subscribe-" in topic:
        if "recipient_user_name" in msg:
            callback(GiftSubscription(
                msg.get("user_name", None), SUB_PLANS[msg["sub_plan"]],
                msg["months"], None, msg["sub_message"]["message"],
                msg["recipient_user_name"]))
        else:
            callback(Subscription(
                msg["user_name"], SUB_PLANS[msg["sub_plan"]],
                msg["cumulative-months"], msg["streak-months"],
                msg["sub_message"]["message"]))
    elif "-commerce-" in topic:
        raise NotImplementedError(body)

# Mapping from the strings used in the API to human-readable English names.
SUB_PLANS = {
    "Prime": "Twitch Prime",
    "1000": "Tier 1",
    "2000": "Tier 2",
    "3000": "Tier 3",
}


if __name__ == "__main__":
    logger = logging.getLogger(client.__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    connections = [
        TwitchChatConnection("BotAltBTW", secret.BOTALTBTW_OAUTH, "Shrdluuu"),
        TwitchEventConnection("Shrdluuu", "http://45.79.95.51:8765"),
    ]
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
        roulette.RouletteHandler(),
    ]
    b = bot.Bot("impbot.sqlite", connections, handlers)
    b.main()
