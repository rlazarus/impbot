import logging
import sys
from typing import Optional, Set, List

import attr
from irc import client

import bot
import custom
import hello
import irc_connection
import roulette
import secret


class TwitchChatConnection(irc_connection.IrcConnection):
    def __init__(self, bot_username: str, oauth_token: str,
                 streamer_username: str, admins: List[str]) -> None:
        if not oauth_token.startswith("oauth:"):
            oauth_token = "oauth:" + oauth_token
        super().__init__("irc.chat.twitch.tv", 6667, bot_username.lower(),
                         "#" + streamer_username.lower(), password=oauth_token,
                         capabilities=["twitch.tv/tags"])
        self.admins = admins

    def _user(self, event: client.Event) -> bot.User:
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
        return TwitchUser(event.source.nick, admin, display_name, moderator)


@attr.s(frozen=True)
class TwitchUser(bot.User):
    display_name: Optional[str] = attr.ib(cmp=False, default=None)
    # The streamer doesn't have a mod badge, but they have a superset of
    # mod privileges, so this is true for them too.
    moderator: Optional[bool] = attr.ib(cmp=False, default=None)
    badges: Optional[Set[str]] = attr.ib(cmp=False, default=None)

    def __str__(self) -> str:
        return self.display_name if self.display_name is not None else self.name


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    connections = [
        TwitchChatConnection("BotAltBTW", secret.BOTALTBTW_OAUTH, "Shrdluuu",
                             []),
    ]
    handlers = [
        custom.CustomCommandHandler(),
        hello.HelloHandler(),
        roulette.RouletteHandler(),
    ]
    b = bot.Bot(None, None, "impbot.sqlite", connections, handlers)
    b.main()
