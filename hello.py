import command


class HelloHandler(command.CommandHandler):
    @property
    def url_rules(self):
        return [("/hello", self.web, None)]

    def run_hello(self) -> str:
        return "Hello, world!"

    def web(self) -> str:
        return "Hello, world, but in HTTP!"
