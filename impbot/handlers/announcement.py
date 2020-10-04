import datetime
import logging
import threading
from typing import Optional

from impbot.connections import timer
from impbot.core import base
from impbot.handlers import command
from impbot.util import twitch_util

INTERVAL = datetime.timedelta(hours=2)

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
        try:
            last_announce = self.data.get("last_announce")
        except KeyError:
            last_announce_time = datetime.datetime.utcfromtimestamp(0)
        else:
            last_announce_time = datetime.datetime.fromisoformat(last_announce)
        if datetime.datetime.utcnow() - last_announce_time > INTERVAL:
            # The announcement is overdue. This happens if the bot was offline
            # when it should have fired. (It also happens when the bot is
            # started up for the first time, but then we just announce the empty
            # string until the text is set.)
            self.announce()
            last_announce_time = datetime.datetime.now()
        # Wait out the rest of the interval, then announce and start the
        # repeating timer.
        wait = last_announce_time + INTERVAL - datetime.datetime.now()

        def run():
            logger.info("### Timer!")
            self.announce()
            self.timer_conn.start_repeating(INTERVAL, self.announce)

        threading.Timer(wait.total_seconds(), run).start()

    def announce(self):
        data = self.util.get_stream_data(username=self.util.streamer_username)
        logger.info(f"### Data: {data}")
        if data != twitch_util.OFFLINE:
            logger.info(f"### Online, announcing! {self.data.get('announcement')}")
            self.chat.say(self.data.get("announcement", default=""))
        else:
            logger.info("### Offline, not announcing.")
        self.data.set("last_announce", str(datetime.datetime.utcnow()))

    def run_setannouncement(self, message: base.Message,
                            text: str) -> Optional[str]:
        if not (message.user.moderator or message.user.admin):
            return
        self.data.set("announcement", text)
        return "Announcement set!"
