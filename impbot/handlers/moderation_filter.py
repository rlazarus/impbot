import datetime
import re
import socket
import string
from typing import Optional, cast, Literal, Set

import pytz
import requests

from impbot.connections import twitch
from impbot.core import base
from impbot.handlers import command

MAX_EMOTES = 27

TRIGGER_LENGTH = 50
CAPS = set(string.ascii_uppercase + ' ')
LETTERS = set(string.ascii_letters + string.digits + ' ')
MAX_SYMBOL_FRACTION = 0.75
REPEATING_PATTERN = re.compile(r'(.)\1{34}')

SCHEME = "(?:(?:[a-z][a-z0-9+.-]*:)?//)"
USERINFO = "(?:(?:[a-z0-9_.+!~*'();:&=+$,-]|%[0-9a-f]{2})+@)"
# The IP address patterns are overbroad -- we'll just parse them with inet_pton.
IPV4 = r"(\d+.\d+.\d+.\d+)"
IPV6 = r"(?:\[([0-9a-f:]+)\])"
TLDS_URL = "https://data.iana.org/TLD/tlds-alpha-by-domain.txt"
TLD = "|".join(line for line in requests.get(TLDS_URL).text.splitlines()
               if not line.startswith("#"))
NAME = rf"(?:[a-z0-9-]+\.)+(?:{TLD})"
PORT = r"(?::\d+)"
PCHAR = "[a-z0-9._~!$&'()*+,;=:@-]|%[0-9a-f]{2}"
PATH = f"(?:/(?:{PCHAR}|/)*)"
QUERY = rf"(?:\?(?:{PCHAR}|[/?])*)"
HOST = f"(?:{IPV4}|{IPV6}|{NAME})"
LINK_PATTERN = re.compile(
    rf"(?:\b|^){SCHEME}?{USERINFO}?{HOST}{PORT}?{PATH}?{QUERY}?(?:\b|$)",
    re.IGNORECASE)


class PermitHandler(command.CommandHandler):
    def __init__(self, link_allowed_users: Set[twitch.TwitchUser]) -> None:
        super().__init__()
        self.link_allowed_users = link_allowed_users

    def run_permit(self, message: base.Message, username: str) -> Optional[str]:
        if not message.user.moderator:
            return
        if username.startswith("@"):
            username = username[1:]
        user = twitch.TwitchUser(username.lower(), display_name=username)
        if user in self.link_allowed_users:
            return (f"@{message.user} That's okay, {user} is always allowed to "
                    f"post links.")
        if self.is_permitted(user):
            # We must've already done this just now -- treat it like a cooldown.
            return
        now = datetime.datetime.utcnow()
        self.data.set_subkey("permitted", user.name, str(now))
        return f"{user} is now permitted to post a link in the next 45 seconds."

    def is_permitted(self, user: twitch.TwitchUser) -> bool:
        if user in self.link_allowed_users:
            return True
        try:
            permitted = self.data.get("permitted", user.name)
            permission_time = datetime.datetime.fromisoformat(permitted)
            permission_age = datetime.datetime.utcnow() - permission_time
            return permission_age < datetime.timedelta(seconds=45)
        except KeyError:
            return False

    def unpermit(self, user: twitch.TwitchUser):
        self.data.unset("permitted", user.name)


class ModerationFilterHandler(base.Handler[twitch.TwitchMessage]):
    def __init__(self, permit_handler: PermitHandler, allowed_urls: Set[str]):
        super().__init__()
        self.permit_handler = permit_handler
        self.allowed_urls = {url.lower() for url in allowed_urls}
        self.action: Optional[Literal["delete", "timeout"]] = None
        self.duration: Optional[datetime.timedelta] = None
        self.reply: Optional[str] = None

    def check(self, message: twitch.TwitchMessage) -> bool:
        user = cast(twitch.TwitchUser, message.user)
        if user.moderator or user.admin:
            return False
        if self.check_links(message):
            if self.permit_handler.is_permitted(user):
                self.permit_handler.unpermit(user)
            else:
                self.action = "timeout"
                if self.warning(user):
                    self.duration = datetime.timedelta(minutes=3)
                else:
                    self.duration = datetime.timedelta(seconds=15)
                self.reply = (f"@{user} If you want to post a link, ask a mod "
                              f"to permit you!")
                return True

        if user.is_subscriber:
            return False
        # TODO: Disable temporarily on raid/host.
        if message.action:
            # TODO: Escalate from delete to timeout after a warning, throughout.
            self.action = "delete"
            self.reply = f"@{user} Colored text is for subs only."
            return True
        if len(message.emotes) > MAX_EMOTES:
            self.action = "delete"
            self.reply = f"@{user} Too many emotes."
            return True

        if len(message.text) < TRIGGER_LENGTH:
            return False
        if all(c in CAPS for c in message.text):
            self.action = "delete"
            self.reply = f"@{user} Shhh, please don't shout."
            return True
        symbol_count = sum(1 if c not in LETTERS else 0 for c in message.text)
        if symbol_count > MAX_SYMBOL_FRACTION * len(message.text):
            self.action = "delete"
            self.reply = f"@{user} Too many symbols."
            return True
        if REPEATING_PATTERN.match(message.text):
            self.action = "delete"
            self.reply = f"@{user} Too many repeating characters."
            return True
        return False

    def check_links(self, message: twitch.TwitchMessage) -> bool:
        for match in LINK_PATTERN.finditer(message.text):
            # Our IP-address capturing groups are overbroad -- they'll match
            # stuff like 999.999.999.999 or 1::1:::1. If we get something that
            # *might* be an IP address, it's easiest to just try to parse it
            # with inet_pton, to see if we succeed.
            try:
                if match.group(1):
                    _ = socket.inet_pton(socket.AF_INET, match.group(1))
                elif match.group(2):
                    _ = socket.inet_pton(socket.AF_INET6, match.group(2))
            except OSError:
                continue
            url = match.group().lower()
            if not any(allowed in url for allowed in self.allowed_urls):
                return True
        return False

    def warning(self, user: twitch.TwitchUser) -> bool:
        # Warnings reset at midnight. We use midnight Pacific Time, since it's
        # more likely to fall between streams than midnight UTC.
        timezone = pytz.timezone("America/Los_Angeles")
        today = str(datetime.datetime.now(tz=timezone).date())
        if self.data.get("warning", user.name, default="") == today:
            return True
        self.data.set_subkey("warning", user.name, today)
        return False

    def run(self, message: twitch.TwitchMessage) -> None:
        conn = cast(twitch.TwitchChatConnection, message.reply_connection)
        if self.action == "delete":
            conn.delete(message, self.reply)
        elif self.action == "timeout":
            conn.timeout(message.user, self.duration, self.reply)

        self.action = None
        self.duration = None
        self.reply = None


def module_group(
        allowed_urls: Set[str],
        link_allowed_users: Set[twitch.TwitchUser]) -> base.ModuleGroup:
    permit_handler = PermitHandler(link_allowed_users)
    # The mod filter comes first, because otherwise non-mods could type
    # "!permit link.com" and get ignored.
    return [ModerationFilterHandler(permit_handler, allowed_urls),
            permit_handler]
