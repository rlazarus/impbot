import collections
import datetime
from typing import Dict, Optional

from impbot.core import base


class Cooldown(object):
    def __init__(self, duration: datetime.timedelta) -> None:
        self.duration = duration
        self.last_fire = datetime.datetime.fromtimestamp(0, datetime.timezone.utc)

    def peek(self) -> bool:
        return (datetime.datetime.now(datetime.timezone.utc) >= self.last_fire + self.duration)

    def fire(self) -> bool:
        if not self.peek():
            return False
        self.last_fire = datetime.datetime.now(datetime.timezone.utc)
        return True


class GlobalAndUserCooldowns(object):
    def __init__(self, global_duration: Optional[datetime.timedelta],
                 user_duration: Optional[datetime.timedelta],
                 global_last_fire: Optional[datetime.datetime] = None,
                 user_last_fire: Optional[Dict[base.User, datetime.datetime]] = None) -> None:
        if global_duration is None:
            global_duration = datetime.timedelta(0)
        if user_duration is None:
            user_duration = datetime.timedelta(0)
        self.global_cd = Cooldown(global_duration)
        if global_last_fire is not None:
            self.global_cd.last_fire = global_last_fire
        self.user_duration = user_duration
        self.user_cds: Dict[base.User, Cooldown] = collections.defaultdict(
            lambda: Cooldown(self.user_duration))
        if user_last_fire is not None:
            for user, last_fire in user_last_fire.items():
                self.user_cds[user].last_fire = last_fire

    def peek(self, user: base.User) -> bool:
        global_okay = self.global_cd.peek()
        user_okay = user not in self.user_cds or self.user_cds[user].peek()
        return global_okay and user_okay

    def fire(self, user: base.User) -> bool:
        # Peeking first is important: we only update the timestamp on either cooldown if both will
        # pass.
        if not (self.peek(user) and self.global_cd.peek()):
            return False
        self.user_cds[user].fire()
        self.global_cd.fire()
        return True

    def __repr__(self) -> str:
        user_last_fires = {user: cd.last_fire for user, cd in self.user_cds.items()
                           if not cd.peek()}
        return (f'cooldown.GlobalAndUserCooldowns({self.global_cd.duration!r}, '
                f'{self.user_duration!r}, {self.global_cd.last_fire!r}, {user_last_fires!r})')
