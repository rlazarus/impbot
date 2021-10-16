from datetime import datetime, timedelta, timezone
import logging
import threading
from typing import Optional

import dateutil.parser

from impbot.connections import timer
from impbot.core import base
from impbot.handlers import command
from impbot.util import twitch_util

logger = logging.getLogger(__name__)


class AnnouncementHandler(command.CommandHandler):
    def __init__(self, chat: base.ChatConnection,
                 timer_conn: timer.TimerConnection,
                 util: twitch_util.TwitchUtil):
        super().__init__()
        self.chat = chat
        self.timer_conn = timer_conn
        self.util = util

    def startup(self) -> None:
        interval = self._interval()
        try:
            last_announce = self.data.get("last_announce")
        except KeyError:
            last_announce_time = datetime.fromtimestamp(0, tz=timezone.utc)
        else:
            last_announce_time = dateutil.parser.isoparse(last_announce)
        if datetime.now(timezone.utc) - last_announce_time > interval:
            # The announcement is overdue. This happens if the bot was offline
            # when it should have fired. (It also happens when the bot is
            # started up for the first time, but then we just announce the empty
            # string until the text is set.)
            self.announce()
            last_announce_time = datetime.now(timezone.utc)
        # Wait out the rest of the interval, then announce and start the
        # repeating timer.
        wait = last_announce_time + interval - datetime.now(timezone.utc)

        def run():
            self.announce()
            self.timer_conn.start_repeating(self._interval(), self.announce)

        threading.Timer(wait.total_seconds(), run).start()

    def _interval(self) -> timedelta:
        return timedelta(minutes=int(self.data.get("interval", default=30)))

    def announce(self):
        data = self.util.get_stream_data(username=self.util.streamer_username)
        logger.debug(f"Stream data: {data}")
        if data != twitch_util.OFFLINE:
            announcement = self.data.get("announcement", default="")
            logger.info(f"Online, announcing! {announcement}")
            self.chat.say(announcement)
        else:
            logger.debug("Offline, not announcing.")
        self.data.set("last_announce", str(datetime.now(timezone.utc)))

    def run_setannouncement(self, message: base.Message,
                            text: str) -> Optional[str]:
        if not (message.user.moderator or message.user.admin):
            return
        self.data.set("announcement", text)
        return "Announcement set!"
