import logging
from datetime import datetime, timedelta
from typing import Optional

from impbot.connections import twitch_event
from impbot.core import base, web
from impbot.util import cooldown

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10
END_TIME = datetime(2020, 1, 16, 2)


class PointsGiveawayHandler(base.Handler[twitch_event.PointsReward]):

    def __init__(self) -> None:
        super().__init__()
        self.error_cooldown = cooldown.Cooldown(timedelta(seconds=30))

    def check(self, event: twitch_event.PointsReward) -> bool:
        return "giveaway" in event.reward_title.lower()

    def run(self, event: twitch_event.PointsReward) -> Optional[str]:
        if datetime.now() > END_TIME:
            if self.error_cooldown.fire():
                raise base.UserError(f"Sorry @{event.user}, it's too late to "
                                     f"enter! NotLikeThis")
            else:
                return None
        entries = int(self.data.get(event.user.name, default="0"))
        if entries == MAX_ENTRIES:
            raise base.UserError(f"Sorry @{event.user}, you already have the "
                                 f"max {MAX_ENTRIES} entries.")
        entries += 1
        self.data.set(event.user.name, str(entries))
        if entries == MAX_ENTRIES:
            return (f"@{event.user} You've entered {entries} times now -- "
                    f"that's the maximum, good luck!")
        else:
            return None

    @web.url("/giveaway")
    def _get_all_entries(self) -> str:
        items = self.data.get_all_values().items()
        if not items:
            return "No entries yet."
        entries = []
        for key, value in items:
            entries.extend([key] * int(value))
        entries.sort()
        return "<br>".join(f"{i + 1}. {name}" for i, name in enumerate(entries))
