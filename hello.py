import bot
import command


class HelloHandler(command.CommandHandler):
    def run_hello(self, _: bot.Message) -> str:
        return "Hello, world!"
