import datetime
import logging
import threading
import time
from typing import Optional, List

from irc import client

from impbot.core import base

PING_TIMEOUT = datetime.timedelta(minutes=5, seconds=30)

logger = logging.getLogger(__name__)


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
        self.shutdown_event = threading.Event()
        self.expect_disconnection = threading.Event()
        self.last_ping = datetime.datetime.now()
        self.on_event: Optional[base.EventCallback] = None

    # bot.Connection overrides:

    def say(self, text: str) -> None:
        self.connection.privmsg(self.channel, text)

    def run(self, on_event: base.EventCallback) -> None:
        self.on_event = on_event
        while not self.shutdown_event.is_set():
            logger.info("Connecting...")
            self.connect(self.host, self.port, self.nickname, self.password)
            # SimpleIRCClient.start() never returns even after disconnection, so
            # instead of calling into it, we run this loop ourselves. That also
            # lets us time out when we haven't gotten a ping.
            while self.connection.connected:
                self.reactor.process_once(0.2)
                if datetime.datetime.now() - self.last_ping > PING_TIMEOUT:
                    logger.info(
                        f"{datetime.datetime.now() - self.last_ping} since "
                        "last ping; reconnecting.")
                    self.disconnect()
            logger.info("Disconnected.")
            if not self.expect_disconnection.is_set():
                time.sleep(3)  # It's, uh, exponential backoff with a base of 1.
            self.expect_disconnection.clear()

    def shutdown(self) -> None:
        self.shutdown_event.set()
        self.disconnect()

    def disconnect(self) -> None:
        self.expect_disconnection.set()
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

    def on_ping(self, _conn: client.ServerConnection,
                _event: client.Event) -> None:
        self.last_ping = datetime.datetime.now()
