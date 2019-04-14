import queue
import sys
import threading
from abc import ABC, abstractmethod
from typing import NamedTuple, Callable, Optional, Dict, Sequence

import data


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

    @abstractmethod
    def shutdown(self) -> None:
        pass


class Handler(ABC):
    def __init__(self) -> None:
        self.data = data.Namespace(type(self).__name__)

    @abstractmethod
    def check(self, message: Message) -> bool:
        pass

    @abstractmethod
    def run(self, message: Message) -> Optional[str]:
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

        self.handlers = handlers
        self._queue = queue.Queue()

        # Initialize the handler thread here, but we'll start it in run().
        self._handler_thread = threading.Thread(target=self.handle_queue,
                                                args=[db])

    def process(self, message: Message) -> None:
        self._queue.put(message)

    def handle_queue(self, db: Optional[str]) -> None:
        # Initialize the DB. We can't do this in __init__ because sqlite objects
        # can't be passed between threads, and the one belonging to the data
        # module should be available in the handler thread.
        if db is not None:
            data.startup(db)

        while True:
            message = self._queue.get()
            if message is None:
                self._queue.task_done()
                break
            self.handle(message)
            self._queue.task_done()

        data.shutdown()

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

    def main(self) -> None:
        self._handler_thread.start()
        conn_threads = []
        for connection in self.connections:
            t = threading.Thread(target=connection.run, args=[self.process])
            t.start()
            conn_threads.append(t)

        try:
            self._handler_thread.join()
        except KeyboardInterrupt:
            print("Exiting...")
            self._queue.put(None)
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