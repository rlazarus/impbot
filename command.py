from typing import Callable, List, Tuple, Optional

import bot
import inspect


class CommandHandler(bot.Handler):
    def __init__(self):
        self.commands = {"!" + i[len("run_"):] for i in dir(self)
                         if i.startswith("run_") and callable(getattr(self, i))}

    def _func_argstring(self, message) -> Optional[Tuple[Callable, str]]:
        parts = message.text.split(None, 1)
        if not parts:
            return None
        command = parts[0]
        argstring = parts[1] if len(parts) == 2 else ""
        if not command.startswith("!"):
            return None
        func = getattr(self, "run_" + command[1:], None)
        if not callable(func):
            return None
        return func, argstring

    def check(self, message: bot.Message) -> bool:
        return self._func_argstring(message) is not None

    def run(self, message: bot.Message) -> str:
        func, argstring = self._func_argstring(message)
        params = inspect.signature(func).parameters
        argtypes = [p.annotation for p in params.values()]
        # Optionally, the first parameter to a handler function can be special:
        # it can take the bot.Message directly, rather than an argument parsed
        # from the message.
        pass_message = argtypes and argtypes[0] == bot.Message
        if pass_message:
            # If the function takes a Message, the args we'll parse are the
            # parameters after it.
            argtypes = argtypes[1:]
        if not argtypes:
            # For commands with no arguments, silently ignore any other text on
            # the line.
            args: List[str] = []
        elif argtypes == [Optional[str]]:  # TODO: Generalize this further.
            args = [argstring if argstring else None]
        else:
            # Split at most len(argtypes) - 1 times: len(args) <= len(argtypes).
            args = argstring.split(None, len(argtypes) - 1)
            if len(args) < len(argtypes):
                raise UsageError(func)
            for i, cls in enumerate(argtypes):
                # If the arg needs to be converted to something other than
                # string, do that and replace it. If that fails, it's a usage
                # error.
                # TODO: Eventually, this won't be enough -- converting to User
                # requires more context than just the string.
                if cls != str:
                    try:
                        args[i] = cls(args[i])
                    except ValueError:
                        raise UsageError(func)
        try:
            if pass_message:
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
        usage = ["!" + func.__name__[len("run_"):]]
        params = inspect.signature(func).parameters.items()
        usage.extend(f"<{k}>" for k, v in params if v.annotation != bot.Message)
        return " ".join(usage)
