import collections
import datetime
import html
from typing import Dict, Optional, Tuple, cast

import flask

from impbot.core import base
from impbot.core import web
from impbot.handlers import command
from impbot.util import cooldown, discord_log

EMBED_COLOR = 0x0000ff


def normalize(command: str) -> str:
    if command.startswith('!'):
        return command[1:].lower()
    return command.lower()


CommandDict = Dict[str, str]


class CustomCommandHandler(command.CommandHandler):
    def __init__(self, discord: Optional[discord_log.DiscordLogger] = None):
        super().__init__()
        self.discord = discord
        self.lookup: Optional[Tuple[str, CommandDict]] = None

    def check(self, message: base.Message) -> bool:
        self.lookup = self._lookup_message(message)
        if super().check(message):
            return True
        if not message.text.startswith('!'):
            return False
        return self.lookup is not None

    def run(self, message: base.Message) -> Optional[str]:
        # If CommandHandler's check() passes, this is a built-in like !addcom, so let
        # CommandHandler's run() dispatch to it.
        if super().check(message):
            # As it happens, all the builtins are for mods only, so we'll do that check here.
            # TODO: Real per-command ACLs.
            if not (message.user.moderator or message.user.admin):
                raise base.UserError("You can't do that.")
            return super().run(message)
        # Otherwise, it's a custom command so we do our own thing.

        # self.lookup is guaranteed non-None by check().
        name, comm = cast(Tuple[str, CommandDict], self.lookup)
        if 'cooldowns' in comm:
            cooldowns = eval(comm['cooldowns'])
            if not cooldowns.fire(message.user):
                return None
            self.data.set_subkey(name, 'cooldowns', repr(cooldowns))
        count = int(comm['count']) + 1
        self.data.set_subkey(name, 'count', str(count))
        return comm['response'].replace('(count)', f'{count:,}')

    @web.url('/commands')
    def web(self) -> str:
        data = self.data.get_all_dicts().items()
        aliases = collections.defaultdict(set)
        for key, subkeys in data:
            if 'alias' in subkeys:
                aliases[subkeys['alias']].add(html.escape(f'!{key}'))

        # This omits any aliases to commands that don't exist.
        commands = []
        for key, subkeys in data:
            if 'response' not in subkeys:  # Skip aliases.
                continue
            response = html.escape(subkeys['response']).replace(
                '(count)',
                "<span class='variable'>(count)</span>")
            commands.append((html.escape(f'!{key}'), aliases[key], response))
        return flask.render_template('commands.html', commands=commands)

    def _lookup_message(self, message: base.Message) -> Optional[Tuple[str, CommandDict]]:
        name = normalize(message.text.split(None, 1)[0])
        return self._lookup(name)

    def _lookup(self, name: str) -> Optional[Tuple[str, CommandDict]]:
        """
        Look up the right command from the DB, resolving aliases, or None if it doesn't exist
        (including if an alias points to a command that isn't there, or if there are aliases in a
        loop). Never returns an alias.

        (We don't actually expect aliases to point to other aliases, but if it does happen, better
        to follow the chain than have problems.)
        """
        visited = set()
        while True:
            visited.add(name)
            try:
                result = self.data.get_dict(name)
            except KeyError:
                return None
            if 'alias' in result:
                name = result['alias']
                if name in visited:
                    # Whoops, found a loop.
                    return None
                continue
            else:
                return name, result

    def run_addcom(self, message: base.Message, name: str, text: str) -> str:
        name = normalize(name)
        if self.data.exists(name):
            raise base.UserError(f'!{name} already exists.')
        if hasattr(self, 'run_' + name):
            raise base.UserError(f"Can't use !{name} for a command.")
        self.data.set(name, {
            'response': text,
            'count': '0',
            'cooldowns': repr(cooldown.GlobalAndUserCooldowns(datetime.timedelta(seconds=5), None)),
        })
        if self.discord:
            msg = f'**{message.user}** created the command **!{name}**:\n\n{text}'
            self.discord.embed(EMBED_COLOR, msg)
        return f'Added !{name}.'

    def run_editcom(self, message: base.Message, name: str, text: str) -> str:
        name = normalize(name)
        lookup = self._lookup(name)
        if lookup:
            lookup_name, lookup_data = lookup
            self.data.set_subkey(lookup_name, 'response', text)
            if self.discord:
                msg = f'**{message.user}** edited the command **!{lookup_name}**:\n\n{text}'
                self.discord.embed(EMBED_COLOR, msg, {'Old response': lookup_data['response']})
            if name == lookup_name:
                return f'Edited !{name}.'
            else:
                return f'Edited !{name} (alias to !{lookup_name}).'
        else:
            self.data.set(name, {
                'response': text,
                'count': '0'
            })
            if self.discord:
                msg = f'**{message.user}** created the command **!{name}**:\n\n{text}'
                self.discord.embed(EMBED_COLOR, msg)
            return f"!{name} didn't exist; added it."

    def run_delcom(self, message: base.Message, name: str) -> str:
        name = normalize(name)
        try:
            comm = self.data.get_dict(name)
        except KeyError:
            raise base.UserError(f"!{name} doesn't exist.")
        self.data.unset(name)
        if 'alias' in comm:
            target = comm['alias']
            if self.discord:
                self.discord.embed(
                    EMBED_COLOR,
                    f'**{message.user}** deleted the command **!{name}** (alias to **!{target}**).')
            return f'Deleted !{name}. (It was an alias to !{target}.)'
        else:
            if self.discord:
                msg = f'**{message.user}** deleted the command **!{name}**.'
                fields = {'Old response': comm['response']}
                if '(count)' in comm['response']:
                    fields['Count'] = comm['count']
                self.discord.embed(EMBED_COLOR, msg, fields)
            return f'Deleted !{name}.'

    def run_resetcount(self, name: str, count: Optional[int]) -> str:
        if count is None:
            count = 0
        name = normalize(name)
        lookup = self._lookup(name)
        if not lookup:
            raise base.UserError(f"!{name} doesn't exist")
        name, _ = lookup
        self.data.set_subkey(name, 'count', str(count))
        return f'Reset !{name} counter to {count}.'

    def run_aliascom(self, message: base.Message, name: str, target: str):
        name = normalize(name)
        target = normalize(target)
        if self.data.exists(name):
            raise base.UserError(f'!{name} already exists.')
        if hasattr(self, 'run_' + name):
            raise base.UserError(f"Can't use !{name} for a command.")
        lookup = self._lookup(target)
        if not lookup:
            raise base.UserError(f"!{target} isn't a custom command.")
        target, _ = lookup
        self.data.set(name, {'alias': target})
        if self.discord:
            msg = f'**{message.user}** created **!{name}** as an alias to **!{target}**.'
            self.discord.embed(EMBED_COLOR, msg)
        return f'Added !{name} as an alias to !{target}.'
