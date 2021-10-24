import logging
from typing import Optional, cast

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
            data = self.twitch_util.get_stream_data(username=self.twitch_util.streamer_username)
            if data == twitch_util.OFFLINE:
                return 'Stream is offline.'
            current_title = data['title']
            return f'Current title: {current_title}'
        if not (message.user.moderator or message.user.admin):
            raise base.UserError("You can't do that.")
        channel_id = self.twitch_util.get_channel_id(self.twitch_util.streamer_username)
        self.twitch_util.helix_patch(
            'channels', params={'broadcaster_id': channel_id}, json={'title': title})
        return 'Done!'

    def run_game(self, message: base.Message, game: Optional[str]):
        if not game:
            data = self.twitch_util.get_stream_data(username=self.twitch_util.streamer_username)
            if data == twitch_util.OFFLINE:
                return 'Stream is offline.'
            data = cast(twitch_util.OnlineStreamData, data)
            game_id = int(data['game_id'])
            current_game = self.twitch_util.game_name(game_id)
            return f'Current game: {current_game}'
        if not (message.user.moderator or message.user.admin):
            raise base.UserError("You can't do that.")
        channel_id = self.twitch_util.get_channel_id(self.twitch_util.streamer_username)
        game_id = self.twitch_util.game_id(game)  # Raises UserError if the game doesn't exist.
        self.twitch_util.helix_patch(
            'channels', params={'broadcaster_id': channel_id}, json={'game_id': game_id})
        return 'Done!'
