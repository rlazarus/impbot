import threading

import bot
import custom
import hello
import roulette


class StdioConnection(bot.Connection):
    def __init__(self) -> None:
        self._canceled = threading.Event()

    def say(self, text: str) -> None:
        print(text)

    def run(self, on_event: bot.EventCallback) -> None:
        # Because of the way input() works, we only exit the loop after being
        # canceled and then getting another line from the user.
        while not self._canceled.is_set():
            m = bot.Message("stdin", input("> "), self.say)
            on_event(m)

    def shutdown(self) -> None:
        self._canceled.set()


if __name__ == "__main__":
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
        roulette.RouletteHandler(),
    ]
    b = bot.Bot("impbot.sqlite", [StdioConnection()], handlers)
    b.main()
