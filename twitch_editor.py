import logging
from typing import Optional, Dict

import requests

import base
import command
import secret
import twitch_util

logger = logging.getLogger(__name__)


class TwitchEditorHandler(command.CommandHandler):
    def __init__(self, streamer_username: str):
        super().__init__()
        self.channel_id = twitch_util.get_channel_id(streamer_username)
        self.oauth = twitch_util.TwitchOAuth(streamer_username)

    def run_title(self, message: base.Message, title: Optional[str]):
        if not title:
            data = twitch_util.get_stream_data(user_id=self.channel_id)
            if data == twitch_util.OFFLINE:
                return "Stream is offline."
            logger.debug(data)
            current_title = data["title"]
            return f"Current title: {current_title}"
        if not (message.user.moderator or message.user.admin):
            raise base.UserError("You can't do that.")
        self._update_stream(self.channel_id, title=title)
        return "Done!"

    def run_game(self, message: base.Message, game: Optional[str]):
        if not game:
            data = twitch_util.get_stream_data(user_id=self.channel_id)
            if data == twitch_util.OFFLINE:
                return "Stream is offline."
            game_id = data["game_id"]
            current_game = twitch_util.game_name(game_id)
            return f"Current game: {current_game}"
        if not (message.user.moderator or message.user.admin):
            raise base.UserError("You can't do that.")
        self._update_stream(self.channel_id, game=game)
        return "Done!"

    def _update_stream(self, channel_id: int, title: Optional[str] = None,
                       game: Optional[str] = None) -> None:
        if not title and not game:
            raise ValueError("Must pass either title or game.")

        # TODO: Move this to a startup phase, after the DB is available but
        #       before we print "ready", so that nobody is surprised when they
        #       need to authorize after startup time.
        self.oauth.maybe_authorize()

        url = f"https://api.twitch.tv/kraken/channels/{channel_id}"
        headers = {
            "Accept": "application/vnd.twitchtv.v5+json",
            "Authorization": f"OAuth {self.oauth.access_token}",
            "Client-ID": secret.TWITCH_CLIENT_ID,
        }
        json: Dict[str, Dict[str, str]] = {"channel": {}}
        if title:
            json["channel"]["status"] = title
        if game:
            json["channel"]["game"] = game

        response = requests.put(url, headers=headers, json=json)
        if response.status_code == 401:
            self.oauth.refresh()
            headers["Authorization"] = f"Oauth {self.oauth.access_token}"
            response = requests.put(url, headers=headers, json=json)
        if response.status_code == 401:
            raise base.ServerError(f"401 after refreshing: {response.text}")
        if response.status_code != 200:
            raise base.ServerError(f"{response.status_code} {response.text}")
