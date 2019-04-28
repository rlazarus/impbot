import asyncio
import json
import random
import string
from typing import Callable, Optional
from urllib import parse

import attr
import requests
import websockets

import bot
import data
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
        if not self.data.exists("access_token"):
            self.oauth_authorize()

        # The websockets library wants to be called asynchronously, so bridge
        # into async code here.
        asyncio.set_event_loop(asyncio.new_event_loop())
        asyncio.get_event_loop().run_until_complete(self.run_coro(callback))

    async def run_coro(self, callback: Callable[[bot.Event], None]) -> None:
        url = "wss://pubsub-edge.twitch.tv"
        async with websockets.connect(url) as websocket:
            response = await self.listen(websocket)
            if response["error"] == "ERR_BADAUTH":
                self.oauth_refresh()
                response = await self.listen(websocket)
                if response["error"] == "ERR_BADAUTH":
                    raise bot.AdminError("Two BADAUTH errors, giving up.")

            try:
                async for message in websocket:
                    print(message)
                    body = json.loads(message)
                    handle_message(callback, body)
            except websockets.ConnectionClosed:
                pass

    async def listen(self, websocket):
        alphabet = string.ascii_letters + string.digits
        nonce = "".join(random.choices(alphabet, k=30))

        await websocket.send(json.dumps({
            "type": "LISTEN",
            "nonce": nonce,
            "data": {
                "topics": [
                    f"channel-bits-events-v2.{self.channel_id}",
                    f"channel-subscribe-events-v1.{self.channel_id}",
                    # TODO: Is "commerce" donations? (Probably not -- bet we
                    #   need a separate streamlabs connection.)
                    f"channel-commerce-events-v1.{self.channel_id}",
                ],
                "auth_token": self.data.get("access_token"),
            }
        }))

        # Keep listening until we get a response with the correct nonce. It's
        # generally the first one.
        async for message in websocket:
            response = json.loads(message)
            print(response)
            if response["nonce"] == nonce:
                break
        else:
            # TODO: Here and elsewhere, raise ServerError, not AdminError.
            raise bot.AdminError("Websocket closed without response.")

        if response["type"] != "RESPONSE":
            raise bot.AdminError(f"Bad pubsub response: {response}")
        return response

    def oauth_authorize(self):
        scopes = ["bits:read", "channel_subscriptions"]
        params = parse.urlencode({"client_id": secret.TWITCH_CLIENT_ID,
                                  "redirect_uri": self.redirect_uri,
                                  "response_type": "code",
                                  "scope": " ".join(scopes)})
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
