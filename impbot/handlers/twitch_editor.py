import logging
from typing import Optional, Dict, cast

import requests

import secret
from impbot.core import base
from impbot.handlers import command
from impbot.util import twitch_util

logger = logging.getLogger(__name__)


class TwitchEditorHandler(command.CommandHandler):
    def __init__(self, util: twitch_util.TwitchUtil):
        super().__init__()
        self.twitch_util = util

    def startup(self) -> None:
        self.twitch_util.oauth.maybe_authorize()

    def run_title(self, message: base.Message, title: Optional[str]):
        if not title:
            data = self.twitch_util.get_stream_data(
                username=self.twitch_util.streamer_username)
            if data == twitch_util.OFFLINE:
                return "Stream is offline."
            current_title = data["title"]
            return f"Current title: {current_title}"
        if not (message.user.moderator or message.user.admin):
            raise base.UserError("You can't do that.")
        self._update_stream(title=title)
        return "Done!"

    def run_game(self, message: base.Message, game: Optional[str]):
        if not game:
            data = self.twitch_util.get_stream_data(
                username=self.twitch_util.streamer_username)
            if data == twitch_util.OFFLINE:
                return "Stream is offline."
            data = cast(twitch_util.OnlineStreamData, data)
            game_id = int(data["game_id"])
            current_game = self.twitch_util.game_name(game_id)
            return f"Current game: {current_game}"
        if not (message.user.moderator or message.user.admin):
            raise base.UserError("You can't do that.")
        self._update_stream(game=game)
        return "Done!"

    def _update_stream(self, title: Optional[str] = None,
                       game: Optional[str] = None) -> None:
        if not title and not game:
            raise ValueError("Must pass either title or game.")

        channel_id = self.twitch_util.get_channel_id(
            self.twitch_util.streamer_username)
        url = f"https://api.twitch.tv/kraken/channels/{channel_id}"
        headers = {
            "Accept": "application/vnd.twitchtv.v5+json",
            "Authorization": f"OAuth {self.twitch_util.oauth.access_token}",
            "Client-ID": secret.TWITCH_CLIENT_ID,
        }
        json: Dict[str, Dict[str, str]] = {"channel": {}}
        if title:
            json["channel"]["status"] = title
        if game:
            json["channel"]["game"] = game

        response = requests.put(url, headers=headers, json=json)
        if response.status_code == 401:
            self.twitch_util.oauth.refresh()
            token = self.twitch_util.oauth.access_token
            headers["Authorization"] = f"OAuth {token}"
            response = requests.put(url, headers=headers, json=json)
        if response.status_code == 401:
            raise base.ServerError(f"401 after refreshing: {response.text}")
        if response.status_code != 200:
            raise base.ServerError(f"{response.status_code} {response.text}")
