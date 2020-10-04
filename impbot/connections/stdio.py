import logging
import threading

from impbot.core import base


class StdioConnection(base.ChatConnection):
    def __init__(self) -> None:
        self._canceled = threading.Event()

    def say(self, text: str) -> None:
        print(text)

    def run(self, on_event: base.EventCallback) -> None:
        # Because of the way input() works, we only exit the loop after being
        # canceled and then getting another line from the user.
        while not self._canceled.is_set():
            m = base.Message(self, base.User("stdin"), input("> "))
            logging.info(m)
            on_event(m)

    def shutdown(self) -> None:
        self._canceled.set()
