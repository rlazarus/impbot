from typing import (Callable, List, Tuple, Optional, Type, Any, cast, Union,
                    TypeVar, _GenericAlias)

import bot
import inspect


T = TypeVar("T")


class CommandHandler(bot.Handler):
    def __init__(self) -> None:
        super().__init__()
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
        # TODO: Replace this with proper type handling.
        if not isinstance(message, bot.Message):
            return False
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
        args = _args(argtypes, func, argstring)
        try:
            if pass_message:
                return func(message, *args)
            else:
                return func(*args)
        except bot.UserError as e:
            if str(e):
                raise e
            raise UsageError(func)


def _args(argtypes: List[Type], func: Callable, argstring: str) -> List[Any]:
    if not argtypes:
        # For commands with no arguments, silently ignore any other text on
        # the line.
        return []
    # Split at most len(argtypes) - 1 times, so that len(args) <= len(argtypes).
    argstrings = argstring.split(None, len(argtypes) - 1)
    args = []
    for i, argtype in enumerate(argtypes):
        if i < len(argstrings):
            # If the arg needs to be converted to something other than string,
            # do that and replace it. If that fails, it's a usage error.
            try:
                args.append(_convert_arg(argtype, argstrings[i]))
            except (TypeError, ValueError):
                raise UsageError(func)
        else:
            # We're off the end of args, so there are fewer args provided than
            # expected. That's allowed, if all the remaining args are Optional.
            # In that case, extend it with Nones.
            if not _is_optional(argtype):
                raise UsageError(func)
            args.append(None)

    return args


def _is_optional(t: Type) -> bool:
    # Optional[T] is just sugar for Union[T, None], so really what we want to
    # know is, is the given type a Union that has None as one of its members?
    # Unfortunately some of this is still undocumented as of 3.7, so this may
    # need to be updated for future versions.
    #
    # The most elegant implementation would be "return isinstance(None, t)" but
    # subscripted generics like Union don't work with isinstance.
    if not isinstance(t, _GenericAlias):
        return False
    t = cast(_GenericAlias, t)
    return t.__origin__ == Union and type(None) in t.__args__


def _convert_arg(t: T, value: str) -> T:
    if t == str:
        return value
    if isinstance(t, type):
        return t(value)
    if isinstance(t, _GenericAlias):
        t = cast(_GenericAlias, t)
        if t.__origin__ == Union:
            for subtype in t.__args__:
                try:
                    return _convert_arg(subtype, value)
                except (TypeError, ValueError):
                    continue
        raise ValueError


class UsageError(bot.UserError):
    def __init__(self, func: Callable):
        assert func.__name__.startswith("run_")
        super().__init__("Usage: " + self._usage(func))

    @staticmethod
    def _usage(func: Callable) -> str:
        if func.__doc__:
            return func.__doc__
        usage = ["!" + func.__name__[len("run_"):]]
        params = inspect.signature(func).parameters.items()
        for name, param in params:
            if param.annotation == bot.Message:
                continue
            if _is_optional(param.annotation):
                usage.append(f"[<{name}>]")
            else:
                usage.append(f"<{name}>")
        return " ".join(usage)
