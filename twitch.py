import logging
import sys

from irc import client

import bot
import custom
import hello
import irc_connection
import roulette
import secret
from twitch_event import TwitchEventConnection


class TwitchChatConnection(irc_connection.IrcConnection):
    def __init__(self, bot_username: str, oauth_token: str,
                 streamer_username: str) -> None:
        if not oauth_token.startswith("oauth:"):
            oauth_token = "oauth:" + oauth_token
        super().__init__("irc.chat.twitch.tv", 6667, bot_username.lower(),
                         "#" + streamer_username.lower(), password=oauth_token)


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
