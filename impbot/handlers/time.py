import datetime
import logging
from typing import Optional

from impbot.connections import timer, twitch
from impbot.core import base, data
from impbot.handlers import command
from impbot.observers import mod_insights
from impbot.util import twitch_util

INTERVAL_SECONDS = 60
logger = logging.getLogger(__name__)


class TimeHandler(command.CommandHandler):
    def __init__(self, util: twitch_util.TwitchUtil,
                 chat: twitch.TwitchChatConnection,
                 timer_conn: timer.TimerConnection):
        super().__init__()
        self.twitch_util = util
        self.chat = chat
        self.mod_insights_data = data.Namespace(
            mod_insights.ModInsightsObserver.__name__)
        timer_conn.start_repeating(datetime.timedelta(seconds=INTERVAL_SECONDS),
                                   self.increment_all)

    def increment_all(self) -> None:
        data = self.twitch_util.get_stream_data(
            username=self.twitch_util.streamer_username)
        if data == twitch_util.OFFLINE:
            return

        # TODO: Do this away from the event thread, if it turns out to be slow
        #  when there are a lot of viewers.

        start = datetime.datetime.utcnow()
        ids = self.twitch_util.get_channel_ids(self.chat.all_chatters())
        self.data.increment_subkeys("total_time", ids, INTERVAL_SECONDS)
        if self.data.exists("event_name"):
            self.data.increment_subkeys("event_time", ids, INTERVAL_SECONDS)
        finish = datetime.datetime.utcnow()
        logger.info("Time incremented in %s.", finish - start)

    def run_watchtime(self, message: base.Message, who: Optional[str]) -> str:
        return self.run_time(message, who)

    def run_time(self, message: base.Message, who: Optional[str]) -> str:
        if not who:
            who = message.user.name
        if who.startswith("@"):
            who = who[1:]
        try:
            id = self.twitch_util.get_channel_id(who)
        except KeyError:
            # They're not a Twitch user. But maybe they used to be -- we have
            # some old entries in the database from when these were stored by
            # name, not by ID, so users who changed their names before December
            # 2020 will still have their old names stored there.
            try:
                seconds = int(self.data.get("legacy_time", who.lower()))
                return f"{who} spent {human_duration(seconds)} in the chat."
            except KeyError:
                raise base.UserError(
                    f"@{message.user} {who} isn't a Twitch user.")

        seconds = int(self.data.get("total_time", str(id), default="0"))
        if (not seconds and not self.mod_insights_data.exists(str(id)) and
                who.lower() not in self.chat.all_chatters()):
            if who == message.user.name:
                return (f"@{message.user} Uh, it says here you've never been "
                        f"in the chat, but that can't be right, because here "
                        f"you are... valeS")
            else:
                who = self.twitch_util.get_display_name(who)
                return f"{who} hasn't been in the chat."

        event = self.data.get("event_name", default="")
        if event:
            event_seconds = int(
                self.data.get("event_time", str(id), default="0"))
            event_time = (f" ({human_duration(event_seconds)} during the "
                          f"{event} event)")
        else:
            event_time = ""

        if who.lower() == message.user.name.lower():
            name_has = f"@{message.user} You've"
        else:
            name_has = f"{self.twitch_util.get_display_name(who)} has"

        return (f"{name_has} spent {human_duration(seconds)} in the "
                f"chat{event_time}.")

    def run_startevent(self, message: base.Message, name: str) -> Optional[str]:
        if not message.user.admin:
            return
        try:
            existing_name = self.data.get("event_name")
            raise base.UserError(f"@{message.user} I'm already tracking watch "
                                 f"time for the {existing_name} event.")
        except KeyError:
            self.data.set("event_name", name)
            return f"@{message.user} Tracking watch time for the {name} event!"

    def run_endevent(self, message: base.Message) -> Optional[str]:
        if not message.user.admin:
            return
        try:
            name = self.data.get("event_name")
        except KeyError:
            raise base.UserError(
                f"@{message.user} I'm not tracking watch time for an event.")
        else:
            self.data.unset("event_name")
            return (f"@{message.user} Stopped tracking watch time for the "
                    f"{name} event.")


def human_duration(seconds: int):
    parts = []
    hours = seconds // 3600
    if hours == 1:
        parts.append("1 hour")
    elif hours:
        parts.append(f"{hours:,} hours")
    seconds %= 3600
    minutes = seconds // 60
    if minutes == 1:
        parts.append("1 minute")
    elif minutes:
        parts.append(f"{minutes:,} minutes")

    if parts:
        return " and ".join(parts)
    else:
        return "less than a minute"
