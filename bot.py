from abc import ABC, abstractmethod
from typing import List, NamedTuple, Callable, Optional, Dict, Sequence


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


class AdminError(Exception):
    """Something went wrong with the bot's settings.

    For now, this always crashes the bot.
    TODO: If it happens after we start up successfully, alert the bot's admins
    but do our best to carry on.
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
    def __init__(self, username: str, connections: Sequence[Connection],
                 handlers: Sequence[Handler]) -> None:
        self.username = username
        assert len(connections) == 1  # for now
        self.connections = connections

        # Check for duplicate commands.
        commands: Dict[str, Handler] = {}
        for handler in handlers:
            for command in getattr(handler, "commands", []):
                if command in commands:
                    raise ValueError(f"Both {type(commands[command])} and "
                                     f"{type(handler)} register '{command}'.")
                commands[command] = handler

        self.handlers = handlers

    def handle(self, message: Message) -> None:
        for handler in self.handlers:
            if handler.check(message):
                try:
                    response = handler.run(message)
                    if response:
                        message.reply(response)
                except UserError as e:
                    message.reply(str(e))
                return

    def run(self) -> None:
        for connection in self.connections:
            connection.run(self.handle)
