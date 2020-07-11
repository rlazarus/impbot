import datetime
from typing import cast

from impbot.connections import twitch
from impbot.core import base
from impbot.util import discord_log, twitch_util

EMBED_COLOR = 0xFFFFFF


class ModInsightsObserver(base.Observer[twitch.TwitchMessage]):
    def __init__(self, discord: discord_log.DiscordLogger,
                 util: twitch_util.TwitchUtil):
        super().__init__()
        self.discord = discord
        self.twitch_util = util

    def observe(self, event: twitch.TwitchMessage) -> None:
        user = cast(twitch.TwitchUser, event.user)
        try:
            seen_name = self.data.get(event.user_id)
        except KeyError:
            self.new_user(event.user_id, user)
            return
        if seen_name != user.name:
            self.discord.embed(EMBED_COLOR,
                               f"🔎 **{seen_name} ** changed their Twitch "
                               f"username to **{self.viewercard(user)}**.")
            self.data.set(event.user_id, user.name)

    def new_user(self, user_id: int, user: twitch.TwitchUser):
        self.data.set(user_id, user.name)
        age = self.account_age(user_id)
        if age < datetime.timedelta(minutes=1):
            self.discord.embed(
                EMBED_COLOR,
                f"🔎 **{self.viewercard(user)}** created their account "
                f"less than a minute ago.")
        elif age < datetime.timedelta(minutes=2):
            self.discord.embed(
                EMBED_COLOR,
                f"🔎 **{self.viewercard(user)}** created their account 1 "
                f"minute ago.")
        elif age < datetime.timedelta(hours=1):
            self.discord.embed(
                EMBED_COLOR,
                f"🔎 **{self.viewercard(user)}** created their account "
                f"{age.seconds // 60} minutes ago.")

    def viewercard(self, viewer: twitch.TwitchUser) -> str:
        # TODO: Move into TwitchUtil to dedupe from ModLogObserver
        return (f"[{viewer}](https://twitch.tv/popout/"
                f"{self.twitch_util.streamer_username}/viewercard/"
                f"{viewer.name})")

    def account_age(self, user_id: int) -> datetime.timedelta:
        response = self.twitch_util.kraken_get(f"users/{user_id}")
        created = datetime.datetime.fromisoformat(response["created_at"][:-1])
        return datetime.datetime.utcnow() - created
