import bot
import command


class HelloHandler(command.CommandHandler):
    def run_hello(self) -> str:
        return "Hello, world!"
