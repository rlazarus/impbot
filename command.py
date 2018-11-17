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

        params = inspect.signature(func).parameters
        argtypes = [p.annotation for p in params.values()]
        # We subtract one because the first parameter is the bot.Message.
        argcount = len(argtypes)
        if len(argtypes) >= 1 and argtypes[0] == bot.Message:
            # If the function takes a Message, the argcount we're interested in
            # is the number of parameters after it.
            argcount -= 1

        if argcount == 0:
            # For commands with no arguments, silently ignore any other text on
            # the line.
            args: List[str] = []
        else:
            # Split the string argcount - 1 times, so len(args) == argcount.
            args = argstring.split(None, argcount - 1)
            if len(args) < argcount:
                raise UsageError(func)
            for i, argtype in enumerate(argtypes[1:]):
                # If the arg needs to be converted to something other than
                # string, do that and replace it. If that fails, it's a usage
                # error.
                # TODO: Eventually, this won't be enough -- converting to User
                # requires more context than just the string.
                if argtype != str:
                    try:
                        args[i] = argtype(args[i])
                    except ValueError:
                        raise UsageError(func)
        try:
            if argtypes[0] == bot.Message:
                return func(message, *args)
            else:
                return func(*args)
        except bot.UserError as e:
            if str(e):
                raise e
            raise UsageError(func)


class UsageError(bot.UserError):
    def __init__(self, func):
        assert func.__name__.startswith("run_")
        super().__init__("Usage: " + self._usage(func))

    @staticmethod
    def _usage(func: Callable) -> str:
        if func.__doc__:
            return func.__doc__
        command = "!" + func.__name__[len("run_"):]
        params = inspect.signature(func).parameters.items()
        argusage = [f"<{k}>" for k, v in params if v.annotation != bot.Message]
        if not argusage:
            return command
        return command + " " + " ".join(argusage)
