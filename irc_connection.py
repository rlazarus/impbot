import logging
import sys
from typing import Optional

from irc import client

import bot
import custom
import hello
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
        self.on_event: bot.EventCallback = None

    # bot.Connection overrides:

    def say(self, text: str) -> None:
        self.connection.privmsg(self.channel, text)

    def run(self, on_event: bot.EventCallback) -> None:
        self.on_event = on_event
        self.connect(self.host, self.port, self.nickname, self.password)
        # SimpleIRCClient.start() never returns even after disconnection, so
        # instead of calling into it, we run this loop ourselves.
        while self.connection.connected:
            self.reactor.process_once(0.2)

    def shutdown(self) -> None:
        self.connection.close()

    # client.SimpleIRCClient overrides:

    def on_welcome(self, connection: client.ServerConnection,
                   _: client.Event) -> None:
        connection.join(self.channel)

    def on_pubmsg(self, _: client.ServerConnection,
                  event: client.Event) -> None:
        user = bot.User(event.source.nick)
        self.on_event(bot.Message(user, event.arguments[0], self.say))


if __name__ == "__main__":
    logger = logging.getLogger(client.__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    conn = IrcConnection("irc.foonetic.net", 6667, "impbot", "#shrdlutesting")
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
        roulette.RouletteHandler(),
    ]
    b = bot.Bot("impbot.sqlite", [conn], handlers)
    b.main()
