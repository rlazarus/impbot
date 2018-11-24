import sys
from typing import Callable, Optional

from irc import client

import bot
import custom
import data
import hello
import logging
import roulette


class IrcConnection(bot.Connection, client.SimpleIRCClient):
    def __init__(self, host: str, port: int, nickname: str, channel: str,
                 password: Optional[str] = None) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.nickname = nickname
        self.channel = channel
        self.password = password
        self.callback: Callable[[bot.Message], None] = None

    # bot.Connection overrides:

    def say(self, text: str) -> None:
        self.connection.privmsg(self.channel, text)

    def run(self, callback: Callable[[bot.Message], None]) -> None:
        self.callback = callback
        self.connect(self.host, self.port, self.nickname, self.password)
        self.start()

    # client.SimpleIRCClient overrides:

    def on_welcome(self, connection: client.ServerConnection,
                   _: client.Event) -> None:
        connection.join(self.channel)

    def on_pubmsg(self, _: client.ServerConnection,
                  event: client.Event) -> None:
        self.callback(
            bot.Message(event.source.nick, event.arguments[0], self.say))


if __name__ == "__main__":
    logger = logging.getLogger(client.__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    data.startup("impbot.sqlite")
    conn = IrcConnection("irc.foonetic.net", 6667, "impbot", "#shrdlutesting")
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
        roulette.RouletteHandler(),
    ]
    bot.Bot("bot", [conn], handlers).run()
    data.shutdown()
