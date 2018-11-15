from typing import Dict, Optional

import bot
import command
import cooldown


def normalize(command: str) -> str:
    if command.startswith('!'):
        return command[1:].lower()
    return command.lower()


class Command(object):
    def __init__(self, command: str, response: str) -> None:
        self.command = command
        self.response = response
        self.count = 0
        self.cooldowns = cooldown.GlobalAndUserCooldowns(None, None)


class CustomCommandHandler(command.CommandHandler):
    def __init__(self):
        super().__init__()
        self.commands: Dict[str, Command] = {}

    def check(self, message: bot.Message) -> bool:
        if super().check(message):
            return True
        if not message.text.startswith("!"):
            return False
        return normalize(message.text.split(" ", 1)[0]) in self.commands

    def run(self, message: bot.Message) -> Optional[str]:
        # If CommandHandler's check() passes, this is a built-in like !addcom,
        # so let CommandHandler's run() dispatch to it.
        if super().check(message):
            return super().run(message)
        # Otherwise, it's a custom command so we do our own thing.
        if " " in message.text:
            name, args = message.text.split(" ", 1)
        else:
            name, args = message.text, ""
        name = normalize(name)
        c = self.commands[name]
        if not c.cooldowns.fire(message.username):
            return None
        c.count += 1
        return c.response.replace("(count)", str(c.count))

    def run_addcom(self, message: bot.Message, name: str, text: str) -> str:
        name = normalize(name)
        if name in self.commands:
            raise bot.UserError(f"!{name} already exists.")
        if hasattr(self, "run_" + name):
            raise bot.UserError(f"Can't use !{name} for a command.")
        self.commands[name] = Command(name, text)
        return f"Added !{name}."

    def run_editcom(self, message: bot.Message, name: str, text: str) -> str:
        name = normalize(name)
        if name in self.commands:
            self.commands[name].response = text
            return f"Edited !{name}."
        else:
            self.commands[name] = Command(name, text)
            return f"!{name} didn't exist; added it."

    def run_delcom(self, message: bot.Message, name: str) -> str:
        name = normalize(name)
        if name not in self.commands:
            raise bot.UserError(f"!{name} doesn't exist.")
        del self.commands[name]
        return f"Deleted !{name}."

    def run_resetcount(self, message: bot.Message, args: str) -> str:
        """!resetcount <command> [<count>]"""
        # TODO: Type-infer Optional parameters so this can be rolled up as
        # def run_resetcount(..., name: str, count: Optional[int])
        if " " in args:
            fst, snd = args.split(" ", 1)
            if snd.isdigit():
                name, count = fst, int(snd)
            elif fst.isdigit():
                name, count = snd, int(fst)
            else:
                raise bot.UserError
        else:
            name, count = args, 0
        name = normalize(name)
        if name not in self.commands:
            raise bot.UserError(f"!{name} doesn't exist")
        self.commands[name].count = count
        return f"Reset !{name} counter to {count}."