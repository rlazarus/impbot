from typing import Callable

import bot
import custom
import data
import hello
import roulette


class StdioConnection(bot.Connection):
    def say(self, text: str) -> None:
        print(text)

    def run(self, callback: Callable[[bot.Message], None]) -> None:
        while True:
            m = bot.Message("stdin", input("> "), self.say)
            callback(m)


if __name__ == "__main__":
    data.startup("impbot.sqlite")
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
        roulette.RouletteHandler(),
    ]
    bot.Bot("bot", [StdioConnection()], handlers).run()
    data.shutdown()
