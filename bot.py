import logging
import queue
import sys
import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional, Dict, Sequence

import attr

import data

logger = logging.getLogger(__name__)


@attr.s(auto_attribs=True, frozen=True)
class User:
    name: str


class Event:
    def reply(self, text: str) -> None:
        raise NotImplementedError


class Shutdown(Event):
    pass


@attr.s(auto_attribs=True)
class Message(Event):
    user: User
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


class ServerError(Exception):
    """A server we're connected to did something unexpected.

    The difference between this and AdminError is that an AdminError can be
    resolved by fixing the bot's configuration. If the server sends us an
    "incorrect password" error, that's an AdminError, but if it hangs up on us
    that's a ServerError.
    """
    pass


EventCallback = Callable[[Event], None]


class Connection(ABC):
    @abstractmethod
    def say(self, text: str) -> None:
        pass

    @abstractmethod
    def run(self, on_event: EventCallback) -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class Handler(ABC):
    def __init__(self) -> None:
        self.data = data.Namespace(type(self).__name__)

    @abstractmethod
    def check(self, event: Event) -> bool:
        pass

    @abstractmethod
    def run(self, event: Event) -> Optional[str]:
        pass


class Bot:
    def __init__(self, db: Optional[str], connections: Sequence[Connection],
                 handlers: Sequence[Handler]) -> None:
        self.connections = connections

        # Check for duplicate commands.
        commands: Dict[str, Handler] = {}
        for handler in handlers:
            for command in getattr(handler, "commands", []):
                if command in commands:
                    raise ValueError(f"Both {type(commands[command])} and "
                                     f"{type(handler)} register '{command}'.")
                commands[command] = handler

        if db is not None:
            data.startup(db)

        self.handlers = handlers
        self._queue = queue.Queue()

        # Initialize the handler thread here, but we'll start it in run().
        self._handler_thread = threading.Thread(
            name="Event handler", target=self.handle_queue)

    def process(self, event: Event) -> None:
        self._queue.put(event)

    def handle_queue(self) -> None:
        while True:
            event = self._queue.get()
            if isinstance(event, Shutdown):
                self._queue.task_done()
                break
            self.handle(event)
            self._queue.task_done()

        data.shutdown()

    def handle(self, event: Event) -> None:
        for handler in self.handlers:
            if handler.check(event):
                try:
                    response = handler.run(event)
                    if response:
                        event.reply(response)
                except UserError as e:
                    event.reply(str(e))
                return

    def main(self) -> None:
        logger.info("Starting...")
        self._handler_thread.start()
        conn_threads = []
        for connection in self.connections:
            t = threading.Thread(name=type(connection).__name__,
                                 target=connection.run, args=[self.process])
            t.start()
            conn_threads.append(t)

        try:
            self._handler_thread.join()
        except KeyboardInterrupt:
            logger.info("Exiting...")
            self._queue.put(Shutdown())
            self._handler_thread.join()

        for connection in self.connections:
            connection.shutdown()
        graceful_exit = True
        for thread in conn_threads:
            thread.join(timeout=10.0)
            if thread.is_alive():
                graceful_exit = False
        if not graceful_exit:
            sys.exit(1)
