from typing import Optional, Set

from impbot.connections import twitch
from impbot.core import base
from impbot.handlers import command
from impbot.util import twitch_util


class OnCallModHandler(command.CommandHandler):
    def __init__(self, util: twitch_util.TwitchUtil, on_call_mods: Set[str]):
        super().__init__()
        self.twitch_util = util
        self.on_call_mods = {twitch.TwitchUser(i.lower()) for i in on_call_mods}

    def run_modme(self, msg: base.Message) -> Optional[str]:
        if msg.user not in self.on_call_mods:
            return (f"@{msg.user} That command is only for our mods to use. "
                    f"valeGiggle But thanks for your interest in modding! Type "
                    f"!m2 for more info.")
        self.twitch_util.irc_command_as_streamer(f".mod {msg.user.name}")
        return f"@{msg.user} vale7"

    def run_unmodme(self, msg: base.Message) -> Optional[str]:
        if msg.user not in self.on_call_mods:
            if msg.user.moderator:
                return (f"@{msg.user} Sorry pal, you signed a blood oath, "
                        f"that's over my head.")
            return
        self.twitch_util.irc_command_as_streamer(f".unmod {msg.user.name}")
        return f"@{msg.user} valeLove"

    def run_modsdosomething(self, msg: base.Message) -> Optional[str]:
        if msg.user.name != self.twitch_util.streamer_username.lower():
            return
        commands = [f".mod {i}" for i in self.on_call_mods]
        self.twitch_util.irc_command_as_streamer(commands)
        return "Mods assemble! vale7"
