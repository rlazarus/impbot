import datetime
from typing import Optional

import requests

import secret
from impbot.core import base
from impbot.handlers import command
from impbot.util import twitch_util


class TwitchInfoHandler(command.CommandHandler):
    def __init__(self, streamer_username: str):
        super().__init__()
        self.streamer_username = streamer_username
        self.streamer_id = twitch_util.get_channel_id(streamer_username)

    # TODO: Support User args in CommandHandler, then take one here.
    def run_followage(self, message: base.Message, who: Optional[str]):
        if not who:
            who = message.user.name
        if who.startswith('@'):
            who = who[1:]
        from_id = twitch_util.get_channel_id(who)
        response = requests.get(
            "https://api.twitch.tv/helix/users/follows",
            params={"from_id": from_id, "to_id": self.streamer_id},
            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
        if response.status_code != 200:
            raise base.ServerError(f"{response.status_code} {response.text}")
        body = response.json()
        if not body["data"]:
            if who.lower() == message.user.name.lower():
                return (f"@{message.user} You aren't following "
                        f"{self.streamer_username}.")
            else:
                return f"{who} isn't following {self.streamer_username}."

        data = body["data"][0]
        if who.lower() == message.user.name.lower():
            name_has = f"@{message.user} You've"
        else:
            name_has = f"{data['from_name']} has"

        since_str = data["followed_at"]
        since = datetime.date.fromisoformat(since_str[:len("YYYY-MM-DD")])
        if (datetime.date.today() - since) < datetime.timedelta(days=365):
            date = since.strftime("%B %d").replace(" 0", " ")
        else:
            date = since.strftime("%B %d, %Y").replace(" 0", " ")

        if since == datetime.date.today():
            duration = "today"
        elif since == datetime.date.today() - datetime.timedelta(days=1):
            duration = "yesterday"
        elif since < datetime.date.today():
            days = (datetime.date.today() - since).days
            duration = f"{days:,} days ago"
        else:
            duration = "the future??"

        return (f"{name_has} been following {self.streamer_username} since "
                f"{date} ({duration}).")

    def run_followers(self):
        return self.run_follows()

    def run_follows(self):
        response = requests.get(
            "https://api.twitch.tv/helix/users/follows",
            params={"to_id": self.streamer_id, "first": 1},
            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
        if response.status_code != 200:
            raise base.ServerError(f"{response.status_code} {response.text}")
        followers = response.json()["total"]
        return f"{self.streamer_username} has {followers:,} followers."

    def run_game(self):
        data = twitch_util.get_stream_data(self.streamer_id)
        if data == twitch_util.OFFLINE:
            return f"{self.streamer_username} is offline."
        game = twitch_util.game_name(data["game_id"])
        return f"{self.streamer_username} is streaming {game}."

    def run_title(self):
        data = twitch_util.get_stream_data(self.streamer_id)
        if data == twitch_util.OFFLINE:
            return f"{self.streamer_username} is offline."
        return f"{self.streamer_username}'s title is: {data['title']}"

    def run_uptime(self):
        data = twitch_util.get_stream_data(self.streamer_id)
        if data == twitch_util.OFFLINE:
            return f"{self.streamer_username} is offline."
        started_at = datetime.datetime.fromisoformat(data["started_at"][:-1])
        uptime = datetime.datetime.utcnow() - started_at
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
        return (f"{self.streamer_username} has been live for "
                f"{hours_str}{minutes_str}.")
