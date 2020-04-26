import datetime

import requests

import secret
from impbot.core import base
from impbot.handlers import command


class TwitchInfoHandler(command.CommandHandler):
    def __init__(self, streamer_username: str):
        super().__init__()
        self.streamer_username = streamer_username

    def run_uptime(self):
        response = requests.get("https://api.twitch.tv/helix/streams",
                                params={"user_login": self.streamer_username},
                                headers={"Client-ID": secret.TWITCH_CLIENT_ID})
        if response.status_code != 200:
            raise base.ServerError(f"{response.status_code} {response.text}")
        body = response.json()
        if not body["data"]:
            return "Stream is offline."
        start_str = body["data"][0]["started_at"]
        start = datetime.datetime.fromisoformat(start_str[:-1])
        uptime = datetime.datetime.utcnow() - start
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        if hours == 0:
            hours_str = ""
        elif hours == 1:
            hours_str = "1 hour and "
        else:
            hours_str = f"{hours} hours and "
        if minutes == 1:
            minutes_str = "1 minute"
        else:
            minutes_str = f"{minutes} minutes"
        return f"Stream has been live for {hours_str}{minutes_str}."