import datetime
from typing import Optional, Set

import pytz

from impbot.connections import twitch, twitch_webhook
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
        self.data.set(msg.user.name, today())
        self.twitch_util.mod(msg.user.name)
        return f"@{msg.user} vale7"

    def run_unmodme(self, msg: base.Message) -> Optional[str]:
        if msg.user not in self.on_call_mods:
            if msg.user.moderator:
                return (f"@{msg.user} Sorry pal, you signed a blood oath, "
                        f"that's over my head.")
            return
        self.data.unset(msg.user.name)
        self.twitch_util.unmod(msg.user.name)
        return f"@{msg.user} valeLove"

    def run_modsdosomething(self, msg: base.Message) -> Optional[str]:
        if msg.user.name != self.twitch_util.streamer_username.lower():
            return
        for i in self.on_call_mods:
            self.data.set(i.name, today())
        self.twitch_util.mod([user.name for user in self.on_call_mods])
        return "Mods assemble! vale7"


class OnCallModCleanupObserver(
        base.Observer[twitch_webhook.StreamStartedEvent]):
    def __init__(self, on_call_mod_handler: OnCallModHandler):
        super().__init__()
        self.data = on_call_mod_handler.data
        self.twitch_util = on_call_mod_handler.twitch_util

    def observe(self, event: twitch_webhook.StreamStartedEvent) -> None:
        usernames = []
        for key, value in self.data.get_all_values().items():
            if value == today():
                continue
            else:
                usernames.append(key)
                self.data.unset(key)
        if usernames:
            self.twitch_util.unmod(usernames)


def today():
    timezone = pytz.timezone("America/Los_Angeles")
    return str(datetime.datetime.now(tz=timezone).date())


def module_group(util: twitch_util.TwitchUtil,
                 on_call_mods: Set[str]) -> base.ModuleGroup:
    handler = OnCallModHandler(util, on_call_mods)
    return [handler, OnCallModCleanupObserver(handler)]