import bot


class HelloHandler(bot.Handler):
    def check(self, message: bot.Message) -> bool:
        return message.text == "!hello"

    def run(self, message: bot.Message) -> str:
        return "Hello, world!"
