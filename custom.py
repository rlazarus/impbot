from typing import Dict, Optional

import bot
import command
import cooldown
import data
import datetime


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
    def check(self, message: bot.Message) -> bool:
        if super().check(message):
            return True
        if not message.text.startswith("!"):
            return False
        name = normalize(message.text.split(None, 1)[0])
        return data.exists(self, name)

    def run(self, message: bot.Message) -> Optional[str]:
        # If CommandHandler's check() passes, this is a built-in like !addcom,
        # so let CommandHandler's run() dispatch to it.
        if super().check(message):
            return super().run(message)
        # Otherwise, it's a custom command so we do our own thing.
        name = normalize(message.text.split(None, 1)[0])
        c = eval(data.get(self, name))
        if not c.cooldowns.fire(message.username):
            return None
        c.count += 1
        data.set(self, name, repr(c))
        return c.response.replace("(count)", str(c.count))

    def run_addcom(self, name: str, text: str) -> str:
        name = normalize(name)
        if data.exists(self, name):
            raise bot.UserError(f"!{name} already exists.")
        if hasattr(self, "run_" + name):
            raise bot.UserError(f"Can't use !{name} for a command.")
        data.set(self, name, repr(Command(name, text)))
        return f"Added !{name}."

    def run_editcom(self, name: str, text: str) -> str:
        name = normalize(name)
        if data.exists(self, name):
            c = eval(data.get(self, name))
            c.response = text
            data.set(self, name, repr(c))
            return f"Edited !{name}."
        else:
            data.set(self, name, repr(Command(name, text)))
            return f"!{name} didn't exist; added it."

    def run_delcom(self, name: str) -> str:
        name = normalize(name)
        if not data.exists(self, name):
            raise bot.UserError(f"!{name} doesn't exist.")
        data.unset(self, name)
        return f"Deleted !{name}."

    def run_resetcount(self, args: str) -> str:
        """!resetcount <command> [<count>]"""
        # TODO: Type-infer Optional parameters so this can be rolled up as
        # def run_resetcount(self, name: str, count: Optional[int])
        if " " in args:
            fst, snd = args.split(None, 1)
            if snd.isdigit():
                name, count = fst, int(snd)
            elif fst.isdigit():
                name, count = snd, int(fst)
            else:
                raise bot.UserError
        else:
            name, count = args, 0
        name = normalize(name)
        if not data.exists(self, name):
            raise bot.UserError(f"!{name} doesn't exist")
        c = eval(data.get(self, name))
        c.count = count
        data.set(self, name, repr(c))
        return f"Reset !{name} counter to {count}."
