from datetime import datetime, timedelta
from typing import Optional

from impbot.connections import twitch
from impbot.core import base, web
from impbot.util import cooldown


MAX_ENTRIES = 4
END_TIME = datetime(2019, 11, 28, 2)

class GiveawayHandler(base.Handler[twitch.TwitchMessage]):

    def __init__(self) -> None:
        super().__init__()
        self.error_cooldown = cooldown.Cooldown(timedelta(seconds=30))

    def check(self, message: twitch.TwitchMessage) -> bool:
        return (message.msg_id == "highlighted-message" and
                "enter" in message.text.lower())

    def run(self, message: twitch.TwitchMessage) -> Optional[str]:
        if datetime.now() > END_TIME:
            if self.error_cooldown.fire():
                raise base.UserError(f"Sorry @{message.user.display_name}, "
                                     f"it's too late to enter! NotLikeThis")
            else:
                return None
        entries = int(self.data.get(message.user.name, default="0"))
        if entries == MAX_ENTRIES:
            raise base.UserError(f"Sorry @{message.user.display_name}, you "
                                 f"already have the max {MAX_ENTRIES} entries.")
        entries += 1
        self.data.set(message.user.name, str(entries))
        if entries == 1:
            return (f"@{message.user.display_name} You've entered the "
                    f"giveaway, good luck!")
        elif entries == MAX_ENTRIES:
            return (f"@{message.user.display_name} You've entered {entries} "
                    f"times now -- that's the maximum, good luck!")
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
        return "\n".join(f"{i + 1}. {name}" for i, name in enumerate(entries))
