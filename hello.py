import command
import web


class HelloHandler(command.CommandHandler):
    def run_hello(self) -> str:
        return "Hello, world!"

    @web.url("/hello")
    def web(self) -> str:
        return "Hello, world, but in HTTP!"
