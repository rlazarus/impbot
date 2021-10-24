import functools
import inspect
import typing
from typing import (Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, Union, _GenericAlias,
                    cast)

import attr

from impbot.core import base
from impbot.util import types

T = TypeVar('T')
CommandFunc = Callable[..., Optional[str]]


@attr.s(auto_attribs=True, frozen=True)
class Command:
    # For now this looks pretty useless, but it'll grow more functionality like cooldowns and
    # permissions.
    name: str  # Without prefix: e.g. "foo" not "!foo".
    func: CommandFunc


class CommandHandler(base.Handler[base.Message]):
    # We don't actually use this class field on CommandHandler -- each subclass gets its own, added
    # by the decorator.
    tagged_commands: Dict[str, Command] = {}

    def __init__(self) -> None:
        super().__init__()
        self.commands: Dict[str, Command] = {}
        # We don't need to check for duplicate names here because it's done by the decorator.
        # Collect all the @command methods, binding them to self in the process...
        for name, cmd in self.tagged_commands.items():
            bound_func = functools.partial(cmd.func, self)
            self.commands[f'!{name}'] = Command(name, bound_func)
        # ... and all the run_foo methods, which are already bound via getattr.
        for i in dir(self):
            if i.startswith('run_') and callable(getattr(self, i)):
                name = i[len('run_'):]
                self.commands[f'!{name}'] = Command(name, getattr(self, i))

    def _cmd_argstring(self, message) -> Optional[Tuple[Command, str]]:
        parts = message.text.split(None, 1)
        if not parts:
            return None
        command = parts[0]
        argstring = parts[1] if len(parts) == 2 else ''
        try:
            return self.commands[command], argstring
        except KeyError:
            return None

    def check(self, message: base.Message) -> bool:
        return self._cmd_argstring(message) is not None

    def run(self, message: base.Message) -> Optional[str]:
        # We can cast away the Optional because if _cmd_argstring returned None, check() would have
        # returned False, so run() wouldn't be called.
        cmd, argstring = typing.cast(Tuple[Command, str], self._cmd_argstring(message))
        params = inspect.signature(cmd.func).parameters
        argtypes = [p.annotation for p in params.values()]
        # Optionally, the first parameter to a handler function can be special: it can take the
        # bot.Message directly, rather than an argument parsed from the message.
        pass_message = argtypes and argtypes[0] == base.Message
        if pass_message:
            # If the function takes a Message, the args we'll parse are the parameters after it.
            argtypes = argtypes[1:]
        args = _args(argtypes, cmd, argstring)
        try:
            if pass_message:
                return cmd.func(message, *args)
            else:
                return cmd.func(*args)
        except base.UserError as e:
            if str(e):
                raise e
            raise UsageError(cmd)


def _args(argtypes: List[Type], cmd: Command, argstring: str) -> List[Any]:
    if not argtypes:
        # For commands with no arguments, silently ignore any other text on
        # the line.
        return []
    # Split at most len(argtypes) - 1 times, so that len(argstrings) <= len(argtypes).
    argstrings = argstring.split(None, len(argtypes) - 1)
    args = []
    for i, argtype in enumerate(argtypes):
        if i < len(argstrings):
            # If the arg needs to be converted to something other than string, do that and replace
            # it. If that fails, it's a usage error.
            try:
                args.append(_convert_arg(argtype, argstrings[i]))
            except (TypeError, ValueError):
                raise UsageError(cmd)
        else:
            # We're off the end of argstrings, so there are fewer args provided than expected.
            # That's allowed, if all the remaining args are Optional. In that case, extend it with
            # Nones.
            if not types.is_optional(argtype):
                raise UsageError(cmd)
            args.append(None)

    return args


def _convert_arg(t: Type[T], value: str) -> T:
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
    raise TypeError


def command(name: str):
    """
    Decorator that registers a CommandHandler method as a chat command.
    """
    if name.startswith('!'):
        name = name[1:]
    return functools.partial(_CommandDecorator, name)


class _CommandDecorator:
    def __init__(self, name: str, func: CommandFunc):
        self.cmd_name = name
        self.func = func

    def __set_name__(self, owner: Type, name: str):
        if not issubclass(owner, CommandHandler):
            raise TypeError(
                '@command decorator may only be used on methods of a CommandHandler subclass.')
        # We want to modify the subclass's tagged_commands, not one inherited from CommandHandler
        # itself, so we check __dict__ directly and add one if it's not there already.
        if 'tagged_commands' not in owner.__dict__:
            owner.tagged_commands = {}
        if self.cmd_name in owner.tagged_commands:
            raise ValueError(f'{self.cmd_name} is defined twice in {owner.__name__}')
        if hasattr(owner, f'run_{self.cmd_name}'):
            raise ValueError(f'{self.cmd_name} is defined by both a @command decorator and a '
                             f'run_ method in {owner.__name__}')
        owner.tagged_commands[self.cmd_name] = Command(self.cmd_name, self.func)
        setattr(owner, name, self.func)


class UsageError(base.UserError):
    def __init__(self, cmd: Command):
        super().__init__('Usage: ' + self._usage(cmd))

    @staticmethod
    def _usage(cmd: Command) -> str:
        if cmd.func.__doc__:
            return cmd.func.__doc__
        usage = ['!' + cmd.name]
        params = inspect.signature(cmd.func).parameters.items()
        for name, param in params:
            if param.annotation == base.Message:
                continue
            if types.is_optional(param.annotation):
                usage.append(f'[<{name}>]')
            else:
                usage.append(f'<{name}>')
        return ' '.join(usage)
