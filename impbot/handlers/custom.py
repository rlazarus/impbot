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
        comm = self.data.get_dict(name)
        if "cooldowns" in comm:
            cooldowns = eval(comm["cooldowns"])
            if not cooldowns.fire(message.user):
                return None
            self.data.set_subkey(name, "cooldowns", repr(cooldowns))
        count = int(comm["count"]) + 1
        self.data.set_subkey(name, "count", str(count))
        return comm["response"].replace("(count)", str(count))

    @web.url("/commands")
    def web(self) -> str:
        commands = [(key, subkeys["response"])
                    for key, subkeys in self.data.get_all_dicts().items()]
        return flask.render_template("commands.html", commands=commands)

    def run_addcom(self, name: str, text: str) -> str:
        name = normalize(name)
        if self.data.exists(name):
            raise base.UserError(f"!{name} already exists.")
        if hasattr(self, "run_" + name):
            raise base.UserError(f"Can't use !{name} for a command.")
        self.data.set(name, {
            "response": text,
            "count": "0",
            "cooldowns": repr(cooldown.GlobalAndUserCooldowns(
                datetime.timedelta(seconds=5), None)),
        })
        return f"Added !{name}."

    def run_editcom(self, name: str, text: str) -> str:
        name = normalize(name)
        if self.data.exists(name):
            self.data.set_subkey(name, "response", text)
            return f"Edited !{name}."
        else:
            self.data.set(name, {
                "response": text,
                "count": "0"
            })
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
        self.data.set_subkey(name, "count", str(count))
        return f"Reset !{name} counter to {count}."
