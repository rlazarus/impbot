import datetime
import logging
from typing import Optional

import pytz
import requests

import secret
from impbot.connections import twitch_event, timer, twitch, twitch_webhook
from impbot.core import base
from impbot.util import twitch_util
from impbot.util.twitch_util import OFFLINE

logger = logging.getLogger(__name__)
DURATION = datetime.timedelta(minutes=2)
REDEEMED_BETWEEN_STREAMS = "REDEEMED_BETWEEN_STREAMS"


class ValePointsHandler(base.Handler[twitch_event.PointsReward]):
    def __init__(self, twitch_conn: twitch.TwitchChatConnection,
                 timer_conn: timer.TimerConnection,
                 util: twitch_util.TwitchUtil):
        super().__init__()
        self.twitch_conn = twitch_conn
        self.timer_conn = timer_conn
        self.timer: Optional[timer.Timer] = None
        self.end_time: Optional[datetime.datetime] = None
        self.twitch_util = util

    def check(self, event: twitch_event.PointsReward) -> bool:
        return event.reward_title.startswith(
            ("Emote only mode", "VIP for the day", "Movie night pass"))

    def run(self, event: twitch_event.PointsReward) -> Optional[str]:
        if event.reward_title.startswith("Emote only mode"):
            return self.emote_only(event)
        elif event.reward_title.startswith("VIP for the day"):
            return self.vip(event)
        elif event.reward_title.startswith("Movie night pass"):
            return self.movie_night(event)
        else:
            return None

    def emote_only(self, event: twitch_event.PointsReward) -> str:
        if not self.timer:
            self.twitch_conn.command(".emoteonly")
            self.end_time = datetime.datetime.now() + DURATION
            self.timer = self.timer_conn.start(
                DURATION, lambda: self.twitch_conn.command(".emoteonlyoff"))
            return (f"{event.user} redeemed emote-only mode for two minutes! "
                    f"valePanic")
        else:
            self.end_time += DURATION
            self.timer.cancel()
            time_left = self.end_time - datetime.datetime.now()
            self.timer = self.timer_conn.start(
                time_left,
                lambda: self.twitch_conn.command(".emoteonlyoff"))
            return (f"{event.user} redeemed emote-only mode for ANOTHER two "
                    f"minutes! {time_left.seconds // 60}:"
                    f"{time_left.seconds % 60:02} left now! valePanic")

    def vip(self, event: twitch_event.PointsReward) -> str:
        if self.data.exists(event.user.name):
            return f"@{event.user} What, again? valeThink"
        self.twitch_util.irc_command_as_streamer(f".vip {event.user}")
        stream_data = self.twitch_util.get_stream_data(
            username=self.twitch_util.streamer_username)
        if stream_data != OFFLINE:
            timezone = pytz.timezone("America/Los_Angeles")
            today = str(datetime.datetime.now(tz=timezone).date())
            self.data.set(event.user.name, today)
            return f"{event.user} redeemed VIP for the Day! valeJoy"
        else:
            self.data.set(event.user.name, REDEEMED_BETWEEN_STREAMS)
            return f"{event.user} redeemed VIP for the Day! valeJoy (You'll " \
                   f"have it for the next stream.)"

    def movie_night(self, event: twitch_event.PointsReward) -> str:
        uid = self.twitch_util.get_channel_id(event.user.name)
        url = f"https://valestream.fatalsyntax.com/api/twitch_token/{uid}"
        response = requests.post(url, headers={
            "Authorization": secret.MOVIE_NIGHT_API_KEY,
            "Accept": "application/json",
        })
        if response.status_code != 200:
            logger.error(response.status_code)
            logger.error(response.text)
            return (f"@{event.user} tried to redeem a movie night pass, but "
                    f"something went wrong. valeS")
        json = response.json()
        if not json["success"]:
            logger.error(json)
            return (f"@{event.user} tried to redeem a movie night pass, but "
                    f"something went wrong. valeRIP")
        logger.info(json)
        return (f"@{event.user} redeemed a movie night pass! See you there! "
                f"valeCool")


class ValePointsCleanupObserver(
        base.Observer[twitch_webhook.StreamStartedEvent]):
    def __init__(self, points_handler: ValePointsHandler):
        super().__init__()
        self.data = points_handler.data
        self.twitch_util = points_handler.twitch_util

    def observe(self, event: twitch_webhook.StreamStartedEvent) -> None:
        timezone = pytz.timezone("America/Los_Angeles")
        today = str(datetime.datetime.now(tz=timezone).date())
        commands = []
        for key, value in self.data.get_all_values().items():
            if value == REDEEMED_BETWEEN_STREAMS:
                self.data.set(key, today)
            elif value == today:
                continue
            else:
                commands.append(f".unvip {key}")
                self.data.unset(key)
        if commands:
            self.twitch_util.irc_command_as_streamer(commands)