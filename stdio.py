from typing import Callable

import bot
import custom
import hello


class StdioConnection(bot.Connection):
    def say(self, text: str) -> None:
        print(text)

    def run(self, callback: Callable[[bot.Message], None]) -> None:
        while True:
            m = bot.Message("stdin", input("> "), self.say)
            callback(m)


if __name__ == "__main__":
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
    ]
    bot.Bot("bot", [StdioConnection()], handlers).run()
