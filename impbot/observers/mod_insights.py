import threading
from datetime import datetime, timedelta, timezone
from typing import cast

import dateutil.parser

from impbot.connections import twitch
from impbot.core import base
from impbot.util import discord_log, twitch_util

EMBED_COLOR = 0xFFFFFF


class ModInsightsObserver(base.Observer[twitch.TwitchMessage]):
    def __init__(self, discord: discord_log.DiscordLogger, util: twitch_util.TwitchUtil):
        super().__init__()
        self.discord = discord
        self.twitch_util = util

    def observe(self, event: twitch.TwitchMessage) -> None:
        user = cast(twitch.TwitchUser, event.user)
        try:
            seen_name = self.data.get(str(event.user_id))
        except KeyError:
            self.data.set(str(event.user_id), user.name)
            # Spin off the young-account alert into a new thread, to avoid blocking the rest of this
            # message handling, since we have to call out to the Twitch API for it.
            threading.Thread(name=f'ModInsightsObserver-new_user {user.name}',
                             target=self.new_user,
                             args=(event.user_id, user)).start()
            return
        if seen_name != user.name:
            viewercard = self.viewercard(user)
            self.discord.embed(
                EMBED_COLOR,
                f'🔎 **{seen_name} ** changed their Twitch username to **{viewercard}**.')
            self.data.set(str(event.user_id), user.name)

    def new_user(self, user_id: int, user: twitch.TwitchUser):
        age = self.account_age(user_id)
        if age < timedelta(minutes=1):
            self.discord.embed(
                EMBED_COLOR,
                f'🔎 **{self.viewercard(user)}** created their account less than a minute ago.')
        elif age < timedelta(minutes=2):
            self.discord.embed(
                EMBED_COLOR,
                f'🔎 **{self.viewercard(user)}** created their account 1 minute ago.')
        elif age < timedelta(hours=1):
            minutes = age.seconds // 60
            self.discord.embed(
                EMBED_COLOR,
                f'🔎 **{self.viewercard(user)}** created their account {minutes} minutes ago.')

    def viewercard(self, viewer: twitch.TwitchUser) -> str:
        # TODO: Move into TwitchUtil to dedupe from ModLogObserver
        return (f'[{viewer}](https://twitch.tv/popout/{self.twitch_util.streamer_username}/'
                f'viewercard/{viewer.name})')

    def account_age(self, user_id: int) -> timedelta:
        response = self.twitch_util.helix_get('users', {'id': user_id})
        created = dateutil.parser.isoparse(response['data'][0]['created_at'])
        return datetime.now(timezone.utc) - created
