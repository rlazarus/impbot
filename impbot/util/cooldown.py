import datetime
import collections
from typing import Optional, Dict

from impbot.core import base


class Cooldown(object):
    def __init__(self, duration: datetime.timedelta) -> None:
        self.duration = duration
        self.last_fire = datetime.datetime.fromtimestamp(0,
                                                         datetime.timezone.utc)

    def peek(self) -> bool:
        return (datetime.datetime.now(datetime.timezone.utc) >=
                self.last_fire + self.duration)

    def fire(self) -> bool:
        if not self.peek():
            return False
        self.last_fire = datetime.datetime.now(datetime.timezone.utc)
        return True


class GlobalAndUserCooldowns(object):
    def __init__(self, global_duration: Optional[datetime.timedelta],
                 user_duration: Optional[datetime.timedelta]) -> None:
        if global_duration is None:
            global_duration = datetime.timedelta(0)
        if user_duration is None:
            user_duration = datetime.timedelta(0)
        self.global_cd = Cooldown(global_duration)
        self.user_duration = user_duration
        self.user_cds: Dict[base.User, Cooldown] = collections.defaultdict(
            lambda: Cooldown(user_duration))

    def peek(self, user: base.User) -> bool:
        global_okay = self.global_cd.peek()
        user_okay = user not in self.user_cds or self.user_cds[user].peek()
        return global_okay and user_okay

    def fire(self, user: base.User) -> bool:
        # Peeking first is important: we only update the timestamp on either
        # cooldown if both will pass.
        if not (self.peek(user) and self.global_cd.peek()):
            return False
        self.user_cds[user].fire()
        self.global_cd.fire()
        return True

    def __repr__(self) -> str:
        return (f"cooldown.GlobalAndUserCooldowns({self.global_cd.duration!r}, "
                f"{self.user_duration!r})")
