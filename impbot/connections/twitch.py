import datetime
import logging
import sys
from typing import Optional, Set, List, cast, Tuple

import attr
from irc import client

from impbot.core import bot
from impbot.core import base
from impbot.handlers import custom
from impbot.handlers import hello
from impbot.handlers import roulette
from impbot.connections import irc_conn
import secret

logger = logging.getLogger(__name__)


@attr.s(frozen=True)
class TwitchUser(base.User):
    display_name: Optional[str] = attr.ib(cmp=False, default=None)
    # The streamer doesn't have a mod badge, but they have a superset of
    # mod privileges, so this is true for them too.
    is_moderator: Optional[bool] = attr.ib(cmp=False, default=None)
    is_subscriber: Optional[bool] = attr.ib(cmp=False, default=None)
    badges: Optional[Set[str]] = attr.ib(cmp=False, default=None)

    @property
    def moderator(self) -> Optional[bool]:
        return self.is_moderator

    def __str__(self) -> str:
        return self.display_name if self.display_name is not None else self.name


@attr.s(auto_attribs=True)
class TwitchMessage(base.Message):
    # A unique identifier for each line of chat.
    id: str
    # Twitch's msg-id tag for NOTICE. (https://dev.twitch.tv/docs/irc/msg-id)
    msg_id: Optional[str]
    user_id: int
    action: bool  # True if the message was a CTCP ACTION (/me).
    emotes: List[Tuple[int, int, int]]  # Emote ID, start index, end index


class TwitchChatConnection(irc_conn.IrcConnection):
    def __init__(self, bot_username: str, oauth_token: str,
                 streamer_username: str, admins: List[str]) -> None:
        if not oauth_token.startswith("oauth:"):
            oauth_token = "oauth:" + oauth_token
        super().__init__("irc.chat.twitch.tv", 6667, bot_username.lower(),
                         "#" + streamer_username.lower(), password=oauth_token,
                         capabilities=["twitch.tv/tags", "twitch.tv/commands"])
        self.admins = admins

    def _message(self, event: client.Event) -> base.Message:
        tags = {i['key']: i['value'] for i in event.tags}
        if "badges" in tags and tags["badges"]:
            # Each badge is in the form <name>/<number> (e.g. number of months
            # subscribed) and we don't need the numbers for anything.
            badges = set(badge.split("/", 1)[0]
                         for badge in tags["badges"].split(","))
        else:
            badges = set()
        display_name = tags.get("display-name", event.source.nick)
        admin = "broadcaster" in badges or event.source.nick in self.admins
        moderator = "broadcaster" in badges or "moderator" in badges
        subscriber = "subscriber" in badges
        user = TwitchUser(event.source.nick, admin, display_name, moderator,
                          subscriber)
        emotes = []
        for entry in tags.get("emotes", "").split("/"):
            emote_id, positions = entry.split(":")
            for position in positions.split(","):
                start, end = position.split("-")
                emotes.append((int(emote_id), int(start), int(end)))

        return TwitchMessage(self, user, event.arguments[0], tags.get("id", ""),
                             tags.get("msg-id"), int(tags.get("user-id")),
                             False, emotes)

    def _action(self, event: client.Event) -> base.Message:
        message = cast(TwitchMessage, self._message(event))
        message.action = True
        return message

    def say(self, text: str) -> None:
        # Twitch commands are sent as PRIVMSGs that start with "/" or "." We
        # avoid triggering them via say(), so that the bot doesn't become a
        # confused deputy: if the bot is a mod, unprivileged users can't trick
        # it into (for example) banning people, even if a handler lets them
        # control the beginning of the output.
        if text.startswith("/") or text.startswith("."):
            text = " " + text
        super().say(text)

    def command(self, text: str) -> None:
        # Like say(), but without nerfing commands.
        super().say(text)

    def on_reconnect(self, _conn: client.ServerConnection,
                     _event: client.Event) -> None:
        logger.info("Got a RECONNECT command from Twitch.")
        # Superclass automatically reconnects, since shutdown() wasn't called.
        self.disconnect()

    # TODO: Add a more general moderation API to ChatConnection.
    def timeout(self, target: base.User, duration: datetime.timedelta,
                reply: Optional[str] = None) -> None:
        self.command(f".timeout {target.name} {duration.total_seconds():.0f}")
        if reply:
            self.say(reply)

    def permaban(self, target: base.User, reply: Optional[str] = None) -> None:
        self.command(f".ban {target.name}")
        if reply:
            self.say(reply)

    def delete(self, message: TwitchMessage,
               reply: Optional[str] = None) -> None:
        if not message.id:
            raise base.ServerError(
                f"Message {message} is missing id, can't delete")
        self.command(f".delete {message.id}")
        if reply:
            self.say(reply)
