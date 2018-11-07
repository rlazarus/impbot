from typing import Callable, List

import bot
import inspect


class CommandHandler(bot.Handler):
    def __init__(self):
        self.commands = {"!" + i[len("run_"):] for i in dir(self)
                         if i.startswith("run_") and callable(getattr(self, i))}

    def check(self, message: bot.Message) -> bool:
        first = message.text.split(None, 1)[0]
        if not first.startswith("!"):
            return False
        funcname = "run_" + first[1:]
        return hasattr(self, funcname) and callable(getattr(self, funcname))

    def run(self, message: bot.Message) -> str:
        parts = message.text.split(None, 1)
        command = parts[0]
        argstring = parts[1] if len(parts) == 2 else ""
        assert command.startswith("!")
        func = getattr(self, "run_" + command[1:])

        # We subtract one because the first parameter is the bot.Message.
        params = inspect.signature(func).parameters
        argcount = len(params) - 1
        try:
            if argcount == 0:
                # For commands with no arguments, silently ignore any other text
                # on the line.
                return func(message)
            else:
                # Split the string argcount - 1 times, so len(args) == argcount.
                args = argstring.split(None, argcount - 1)
                if len(args) < argcount:
                    raise bot.UserError
                for i, param in enumerate(list(params.values())[1:]):
                    # If the arg needs to be converted to something other than
                    # string, do that and replace it. If that fails, it's a
                    # usage error.
                    # TODO: Eventually, this won't be enough -- converting to
                    # User requires more context than just the string.
                    if param.annotation != str:
                        try:
                            args[i] = param.annotation(args[i])
                        except ValueError:
                            raise bot.UserError
                return func(message, *args)
        except bot.UserError as e:
            if str(e):
                raise e
            raise bot.UserError("Usage: " + _usage(func))


def _usage(func: Callable) -> str:
    assert func.__name__.startswith("run_")
    command = "!" + func.__name__[len("run_"):]
    if func.__doc__:
        return func.__doc__
    sig = inspect.signature(func)
    if len(sig.parameters) == 1:
        return command
    return (command + " "
            + " ".join(f"<{arg}>" for arg in list(sig.parameters)[1:]))