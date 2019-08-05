import datetime
from typing import Optional, List

import flask

from impbot.core import base
from impbot.core import web
from impbot.handlers import command
from impbot.util import cooldown


def normalize(command: str) -> str:
    if command.startswith('!'):
        return command[1:].lower()
    return command.lower()


class Command(object):
    def __init__(self, command: str, response: str, count: int = 0,
                 cooldowns: Optional[
                     cooldown.GlobalAndUserCooldowns] = None) -> None:
        self.command = command
        self.response = response
        self.count = count
        if cooldowns is None:
            cooldowns = cooldown.GlobalAndUserCooldowns(None, None)
        self.cooldowns = cooldowns

    def __repr__(self) -> str:
        return (f"Command({self.command!r}, {self.response!r}, "
                f"{self.count!r}, {self.cooldowns!r})")


class CustomCommandHandler(command.CommandHandler):
    def check(self, message: base.Message) -> bool:
        if super().check(message):
            return True
        if not message.text.startswith("!"):
            return False
        name = normalize(message.text.split(None, 1)[0])
        return self.data.exists(name)

    def run(self, message: base.Message) -> Optional[str]:
        # If CommandHandler's check() passes, this is a built-in like !addcom,
        # so let CommandHandler's run() dispatch to it.
        if super().check(message):
            # As it happens, all the builtins are for mods only, so we'll do
            # that check here. TODO: Real per-command ACLs.
            if not (message.user.moderator or message.user.admin):
                raise base.UserError("You can't do that.")
            return super().run(message)
        # Otherwise, it's a custom command so we do our own thing.
        name = normalize(message.text.split(None, 1)[0])
        c: Command = eval(self.data.get(name))
        if not c.cooldowns.fire(message.user):
            return None
        c.count += 1
        self.data.set(name, repr(c))
        return c.response.replace("(count)", str(c.count))

    @web.url("/commands")
    def web(self) -> str:
        commands: List[Command] = [eval(v) for k, v in self.data.list("")]
        return flask.render_template("commands.html", commands=commands)

    def run_addcom(self, name: str, text: str) -> str:
        name = normalize(name)
        if self.data.exists(name):
            raise base.UserError(f"!{name} already exists.")
        if hasattr(self, "run_" + name):
            raise base.UserError(f"Can't use !{name} for a command.")
        self.data.set(name, repr(Command(name, text)))
        return f"Added !{name}."

    def run_editcom(self, name: str, text: str) -> str:
        name = normalize(name)
        if self.data.exists(name):
            c = eval(self.data.get(name))
            c.response = text
            self.data.set(name, repr(c))
            return f"Edited !{name}."
        else:
            self.data.set(name, repr(Command(name, text)))
            return f"!{name} didn't exist; added it."

    def run_delcom(self, name: str) -> str:
        name = normalize(name)
        if not self.data.exists(name):
            raise base.UserError(f"!{name} doesn't exist.")
        self.data.unset(name)
        return f"Deleted !{name}."

    def run_resetcount(self, name: str, count: Optional[int]) -> str:
        if count is None:
            count = 0
        name = normalize(name)
        if not self.data.exists(name):
            raise base.UserError(f"!{name} doesn't exist")
        c = eval(self.data.get(name))
        c.count = count
        self.data.set(name, repr(c))
        return f"Reset !{name} counter to {count}."
