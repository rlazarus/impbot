import asyncio
import json
import logging
import sys
from typing import Callable

import requests
import websockets
from irc import client

import bot
import custom
import hello
import irc_connection
import roulette
import secret


class TwitchChatConnection(irc_connection.IrcConnection):
    def __init__(self, bot_username: str, oauth_token: str,
                 streamer_username: str) -> None:
        if not oauth_token.startswith("oauth:"):
            oauth_token = "oauth:" + oauth_token
        super().__init__("irc.chat.twitch.tv", 6667, bot_username.lower(),
                         "#" + streamer_username.lower(), password=oauth_token)


class TwitchEventConnection(bot.Connection):
    def __init__(self, streamer_username: str):
        self.channel_id = self._get_channel_id(streamer_username)
        print(self.channel_id)

    def _get_channel_id(self, streamer_username):
        response = requests.get('https://api.twitch.tv/helix/users',
                                params={'login': streamer_username},
                                headers={'Client-ID': secret.TWITCH_CLIENT_ID})
        if response.status_code != 200:
            raise bot.AdminError(response)
        body = json.loads(response.text)
        if not body['data']:
            raise bot.AdminError(f"No Twitch channel '{streamer_username}'")
        return body['data'][0]['id']

    def say(self, text: str) -> None:
        raise NotImplementedError("TwitchEventConnection doesn't have chat"
                                  "functionality -- use TwitchChatConnection.")

    def run(self, callback: Callable[[bot.Message], None]) -> None:
        # The websockets library wants to be called asynchronously, so bridge
        # into async code here.
        asyncio.set_event_loop(asyncio.new_event_loop())
        asyncio.get_event_loop().run_until_complete(self.run_coro(callback))

    async def run_coro(self, callback: Callable[[bot.Message], None]) -> None:
        url = 'wss://pubsub-edge.twitch.tv'
        async with websockets.connect(url) as websocket:
            request = json.dumps({
                "type": "LISTEN",
                "nonce": "dummy-nonce-fixme",
                "data": {
                    "topics": [
                        f"channel-bits-events-v2.{self.channel_id}",
                        f"channel-subscribe-events-v1.{self.channel_id}",
                        # TODO: Is "commerce" donations?
                        f"channel-commerce-events-v1.{self.channel_id}",
                    ],
                    #### TODO: Here's where this left off. We need to do the
                    #      oauth dance now, which means being able to keep stuff
                    #      in the database, so this is blocked until the DB is
                    #      usable from outside of Handlers.
                    "auth_token": "",
                }
            })
            await websocket.send(request)

            response = await websocket.recv()
            print(response)
            callback(None)

    def shutdown(self) -> None:
        pass


if __name__ == "__main__":
    logger = logging.getLogger(client.__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    connections = [
        #TwitchChatConnection("BotAltBTW", secret.BOTALTBTW_OAUTH, "Shrdluuu"),
        TwitchEventConnection("Shrdluuu"),
    ]
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
        roulette.RouletteHandler(),
    ]
    b = bot.Bot("impbot.sqlite", connections, handlers)
    b.main()
