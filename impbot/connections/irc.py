import logging
import sys
from typing import Optional, List

from irc import client

from impbot.core import bot
from impbot.core import base
from impbot.handlers import custom
from impbot.handlers import hello
from impbot.handlers import roulette


class IrcConnection(base.ChatConnection, client.SimpleIRCClient):
    def __init__(self, host: str, port: int, nickname: str, channel: str,
                 password: Optional[str] = None,
                 capabilities: Optional[List[str]] = None) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.nickname = nickname
        self.channel = channel
        self.password = password
        self.capabilities = capabilities if capabilities is not None else []
        self.on_event: Optional[base.EventCallback] = None

    # bot.Connection overrides:

    def say(self, text: str) -> None:
        self.connection.privmsg(self.channel, text)

    def run(self, on_event: base.EventCallback) -> None:
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
        if self.capabilities:
            connection.cap("REQ", *self.capabilities)
            connection.cap("END")
        connection.join(self.channel)

    def on_pubmsg(self, _: client.ServerConnection,
                  event: client.Event) -> None:
        user = self._user(event)
        self.on_event(base.Message(self, user, event.arguments[0]))

    # Hook for subclasses to override:

    def _user(self, event: client.Event) -> base.User:
        return base.User(event.source.nick)


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
