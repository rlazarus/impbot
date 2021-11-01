from datetime import timedelta
from typing import Optional, cast

import flask

from impbot.connections import twitch
from impbot.core import base, web
from impbot.handlers import command
from impbot.util import cooldown


class CommandGiveawayHandler(command.CommandHandler):

    def __init__(self) -> None:
        super().__init__()
        self.error_cooldown = cooldown.Cooldown(timedelta(seconds=10))

    def run_enter(self, message: base.Message) -> Optional[str]:
        if self.data.exists('_ended'):
            if self.error_cooldown.fire():
                raise base.UserError(f"Sorry @{message.user}, it's too late to enter! NotLikeThis")
            else:
                return None
        if self.data.exists(message.user.name):
            raise base.UserError(f"@{message.user} Don't worry, you're already entered.")
        self.data.set(message.user.name, cast(twitch.TwitchUser, message.user).display_name)
        return f"@{message.user} You've entered the giveaway, good luck!"

    def run_unenter(self, message: base.Message, target: Optional[str]) -> Optional[str]:
        if target:
            target = target.lower()
            if target != message.user.name and not (message.user.moderator or message.user.admin):
                return None
        else:
            target = message.user.name

        if not self.data.exists(target):
            if target == message.user.name:
                return None
            else:
                return f"@{message.user} {target} isn't in the giveaway."

        self.data.unset(target)
        if target == message.user.name:
            return f"Okay @{message.user}, you're out of the giveaway."
        else:
            return f'Removed {target} from the giveaway.'

    def run_endgiveaway(self, message: base.Message) -> Optional[str]:
        if not (message.user.moderator or message.user.admin):
            return None
        self.data.set('_ended', '1')
        return 'No more entries! vale7'

    @web.url('/giveaway')
    def web(self) -> str:
        data = self.data.get_all_values()
        data.pop('_ended', None)
        values = sorted(data.values(), key=str.casefold)
        return flask.render_template('giveaway.html', entries=values)
