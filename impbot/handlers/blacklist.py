import datetime
import enum
import re
from typing import List, Pattern, cast, Dict, Tuple, Optional

from mypy_extensions import TypedDict

from impbot.connections import twitch
from impbot.core import base


class Action(enum.Enum):
    ALLOW = enum.auto()
    PERMABAN = enum.auto()
    TIMEOUT = enum.auto()
    DELETE = enum.auto()


# Required fields for blacklist and whitelist entries.
class EntryBase(TypedDict):
    pattern: str
    action: Action


class BlacklistEntry(EntryBase, total=False):
    reply: str
    duration_seconds: int  # Required if action is TIMEOUT, unset otherwise.


# Action, reply, duration_seconds.
Response = Tuple[Action, Optional[str], Optional[int]]


# Until the moderation API is generalized, only moderate Twitch messages.
class BlacklistModerationHandler(base.Handler[twitch.TwitchMessage]):
    def __init__(self) -> None:
        super().__init__()
        self.whitelist: List[Pattern] = []
        self.blacklist: Dict[Pattern, Response] = {}

        # Valid and non-None during run, if check returned True.
        self.response: Optional[Response] = None

    def startup(self) -> None:
        # We read everything out of the DB and store a copy in memory, so that
        # we don't have to re-compile every regex for every message.
        for data in self.data.get_all_dicts().values():
            action = Action[data["action"]]
            pattern = re.compile(data["pattern"])
            if action is Action.ALLOW:
                self.whitelist.append(pattern)
                continue
            data = cast(BlacklistEntry, data)
            try:
                duration_seconds = int(data["duration_seconds"])
            except KeyError:
                duration_seconds = None
            self.blacklist[pattern] = (action, data.get("reply"),
                                       duration_seconds)

    def add(self, pattern: str, action: Action, reply: Optional[str] = None,
            duration_seconds: Optional[int] = None) -> None:
        if action is Action.TIMEOUT and duration_seconds is None:
            raise ValueError("If action is TIMEOUT, duration must be set.")
        if action is not Action.TIMEOUT and duration_seconds is not None:
            raise ValueError(
                f"If action is {action.name}, duration must be None.")
        if action is Action.ALLOW:
            if reply is not None:
                raise ValueError("If action is ALLOW, reply must be None.")
            self.whitelist.append(re.compile(pattern))
            self._add(
                BlacklistEntry({"pattern": pattern, "action": action.name}))
            return
        self.blacklist[re.compile(pattern)] = action, reply, duration_seconds
        data = BlacklistEntry({"pattern": pattern, "action": action.name})
        if reply is not None:
            data["reply"] = reply
        if duration_seconds is not None:
            data["duration_seconds"] = duration_seconds
        self._add(data)

    def _add(self, data: BlacklistEntry) -> None:
        id = self.data.get("next_id", default="0")
        self.data.set(id, data)
        self.data.set("next_id", str(int(id) + 1))

    def check(self, message: twitch.TwitchMessage) -> bool:
        # We stop at the first blacklist entry that matches a substring of the
        # message, where that substring is not also matched in full by a
        # whitelist entry.
        for pattern, response in self.blacklist.items():
            for match in pattern.finditer(message.text):
                if not any(p.search(match[0]) for p in self.whitelist):
                    self.response = response
                    return True
        return False

    def run(self, message: twitch.TwitchMessage) -> None:
        conn = cast(twitch.TwitchChatConnection, message.reply_connection)
        action, reply, duration_seconds = self.response
        if action is Action.PERMABAN:
            conn.permaban(message.user, reply)
        elif action is Action.TIMEOUT:
            duration = datetime.timedelta(seconds=duration_seconds)
            conn.timeout(message.user, duration, reply)
        elif action is Action.DELETE:
            conn.delete(message, reply)
        self.response = None
