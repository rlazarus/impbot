from abc import ABC, abstractmethod
from typing import List, NamedTuple, Callable, Optional


class Message(NamedTuple):
    username: str
    text: str
    reply: Callable[[str], None]


class UserError(Exception):
    """A user typed something wrong.

    This isn't really an exceptional condition, but it's convenient to have a
    quick escape route from the handler's control flow.
    """
    pass


class Connection(ABC):
    @abstractmethod
    def say(self, text: str) -> None:
        pass

    @abstractmethod
    def run(self, callback: Callable[[Message], None]) -> None:
        pass


class Handler(ABC):
    @abstractmethod
    def check(self, message: Message) -> bool:
        pass

    @abstractmethod
    def run(self, message: Message) -> Optional[str]:
        pass


class Bot:
    def __init__(self, username: str, connections: List[Connection],
                 handlers: List[Handler]) -> None:
        self.username = username
        assert len(connections) == 1  # for now
        self.connections = connections
        self.handlers = handlers

    def handle(self, message: Message) -> None:
        for handler in self.handlers:
            if handler.check(message):
                try:
                    message.reply(handler.run(message))
                except UserError as e:
                    message.reply(str(e))
                return

    def run(self) -> None:
        for connection in self.connections:
            connection.run(self.handle)