from typing import Dict, Optional

import bot
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


class CustomCommandHandler(bot.Handler):
    def __init__(self, *args, **kwargs):
        super(CustomCommandHandler, self).__init__(*args, **kwargs)
        self.commands: Dict[str, Command] = {}

    def check(self, message):
        if not message.text.startswith("!"):
            return False
        command = normalize(message.text.split(" ", 1)[0])
        return (command in SPECIALS) or (command in self.commands)

    def run(self, message: bot.Message) -> Optional[str]:
        if " " in message.text:
            command, args = message.text.split(" ", 1)
        else:
            command, args = message.text, ""
        command = normalize(command)
        if command in SPECIALS:
            return SPECIALS[command](self, args)
        c = self.commands[command]
        if not c.cooldowns.fire(message.username):
            return None
        c.count += 1
        return c.response.replace("(count)", str(c.count))

    def addcom(self, args: str) -> str:
        name, text = args.split(" ", 1)
        name = normalize(name)
        if name in self.commands:
            raise bot.UserError("!{} already exists.".format(name))
        if name in SPECIALS:
            raise bot.UserError("Can't use !{} for a command.".format(name))
        self.commands[name] = Command(name, text)
        return "Added !{}.".format(name)

    def editcom(self, args: str) -> str:
        name, text = args.split(" ", 1)
        name = normalize(name)
        existed = (name in self.commands)
        self.commands[name].response = text
        if existed:
            return "Edited !{}.".format(name)
        else:
            return "!{} didn't exist; added it.".format(name)

    def delcom(self, args: str) -> str:
        name = args.split(" ", 1)[0]
        name = normalize(name)
        if name not in self.commands:
            raise bot.UserError("!{} doesn't exist.".format(name))
        del self.commands[name]
        return "Deleted !{}.".format(name)

    def resetcount(self, args: str) -> str:
        if " " in args:
            fst, snd = args.split(" ", 1)
            if snd.isdigit():
                name, count = fst, int(snd)
            elif fst.isdigit():
                name, count = snd, int(fst)
            else:
                raise bot.UserError("Usage: !resetcount <command> [<count>]")
        else:
            name, count = args, 0
        name = normalize(name)
        if name not in self.commands:
            raise bot.UserError("!{} doesn't exist".format(name))
        self.commands[name].count = count
        return "Reset !{} counter to {}.".format(name, count)


SPECIALS = {
    'addcom': CustomCommandHandler.addcom,
    'editcom': CustomCommandHandler.editcom,
    'delcom': CustomCommandHandler.delcom,
    'resetcount': CustomCommandHandler.resetcount,
}
