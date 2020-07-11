import datetime
from typing import Dict, cast, Optional

import pytz

from impbot.connections import twitch_event, twitch
from impbot.core import base
from impbot.util import discord_log

EMBED_COLOR = 0xffc000


class LastMessageObserver(base.Observer[twitch.TwitchMessage]):
    def __init__(self) -> None:
        super().__init__()
        self.last_messages: Dict[twitch.TwitchUser, str] = {}

    def observe(self, event: twitch.TwitchMessage) -> None:
        user = cast(twitch.TwitchUser, event.user)
        self.last_messages[user] = event.text

    def get(self, user: twitch.TwitchUser) -> Optional[str]:
        return self.last_messages.get(user)


class DiscordModLogObserver(base.Observer[twitch_event.ModAction]):
    def __init__(self, streamer_username: str,
                 discord: discord_log.DiscordLogger,
                 last_messages: LastMessageObserver):
        super().__init__()
        self.streamer_username = streamer_username
        self.discord = discord
        self.last_messages = last_messages

    def observe(self, event: twitch_event.ModAction) -> None:
        target = self.viewercard(event.target)
        last_message = self.last_messages.get(event.target)
        fields = {}
        if isinstance(event, (twitch_event.Ban, twitch_event.Timeout)):
            if event.reason:
                fields["Reason"] = event.reason
            if last_message:
                fields["Last message"] = last_message

        if isinstance(event, twitch_event.Ban):
            self.discord.embed(EMBED_COLOR,
                               f"**{event.user}** banned **{target}**.",
                               fields)
        elif isinstance(event, twitch_event.Unban):
            self.discord.embed(EMBED_COLOR,
                               f"**{event.user}** unbanned **{target}**.")
        elif isinstance(event, twitch_event.Timeout):
            if event.duration.total_seconds() == 1.0:
                self.discord.embed(
                    EMBED_COLOR,
                    f"**{event.user}** purged **{target}**'s messages.", fields)
            else:
                duration = humanize(event.duration)
                exp = expires(event.duration)
                if exp:
                    fields["Expires"] = exp
                self.discord.embed(
                    EMBED_COLOR,
                    f"**{event.user}** timed out **{target}** for {duration}.",
                    fields)
        elif isinstance(event, twitch_event.Untimeout):
            self.discord.embed(
                EMBED_COLOR,
                f"**{event.user}** un-timed-out **{target}**.")
        elif isinstance(event, twitch_event.Delete):
            self.discord.embed(
                EMBED_COLOR,
                f"**{event.user}** deleted **{target}**'s message:\n\n"
                f"{event.message_text}")

    def viewercard(self, viewer: twitch.TwitchUser) -> str:
        return (f"[{viewer}](https://twitch.tv/popout/"
                f"{self.streamer_username}/viewercard/{viewer.name})")


def humanize(duration: datetime.timedelta) -> str:
    parts = [
        [duration.days, "days"],
        (duration.seconds // 3600, "hours"),
        ((duration.seconds % 3600) // 60, "minutes"),
        (duration.seconds % 60, "seconds"),
    ]
    parts = [f"{num} {unit[:-1] if num == 1 else unit}"
             for num, unit in parts if num]
    if not parts:
        return "0 seconds"
    else:
        return " ".join(parts)


def expires(duration: datetime.timedelta) -> str:
    if duration <= datetime.timedelta(minutes=5):
        return ""
    now = datetime.datetime.now(tz=(pytz.timezone("America/Los_Angeles")))
    exptime = now + duration
    if exptime.date() == now.date():
        return f"{exptime:%I:%M %p} PT"
    if exptime.date() == now.date() + datetime.timedelta(days=1):
        return f"Tomorrow {exptime:%I:%M %p} PT"
    if exptime.date() <= now.date() + datetime.timedelta(days=7):
        return f"{exptime:%a %I:%M %p} PT"
    if duration < datetime.timedelta(days=365):
        return f"{exptime:%B %d, %I:%M %p} PT"
    return f"{exptime:%B %d, %Y %I:%M %p} PT"
