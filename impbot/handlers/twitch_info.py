from datetime import date, datetime, timedelta, timezone
from typing import Optional

import dateutil.parser

from impbot.core import base
from impbot.handlers import command
from impbot.util import twitch_util


class TwitchInfoHandler(command.CommandHandler):
    def __init__(self, util: twitch_util.TwitchUtil):
        super().__init__()
        self.twitch_util = util
        self.streamer_username = util.streamer_username

    # TODO: Support User args in CommandHandler, then take one here.
    def run_followage(self, message: base.Message, who: Optional[str]):
        if not who:
            who = message.user.name
        if who.startswith('@'):
            who = who[1:]
        try:
            from_id = self.twitch_util.get_channel_id(who)
        except KeyError:
            raise base.UserError(f"@{message.user} {who} isn't a Twitch user.")
        to_id = self.twitch_util.get_channel_id(self.streamer_username)
        body = self.twitch_util.helix_get('users/follows', {'from_id': from_id, 'to_id': to_id})
        if not body['data']:
            if who.lower() == message.user.name.lower():
                return f"@{message.user} You aren't following {self.streamer_username}."
            else:
                return f"{who} isn't following {self.streamer_username}."

        data = body['data'][0]
        if who.lower() == message.user.name.lower():
            name_has = f"@{message.user} You've"
        else:
            name_has = f'{data["from_name"]} has'

        since_str = data['followed_at']
        since = date.fromisoformat(since_str[:len('YYYY-MM-DD')])
        if (date.today() - since) < timedelta(days=365):
            since_str = since.strftime('%B %d').replace(' 0', ' ')
        else:
            since_str = since.strftime('%B %d, %Y').replace(' 0', ' ')

        if since == date.today():
            duration = 'today'
        elif since == date.today() - timedelta(days=1):
            duration = 'yesterday'
        elif since < date.today():
            days = (date.today() - since).days
            duration = f'{days:,} days ago'
        else:
            duration = 'the future??'

        return (
            f'{name_has} been following {self.streamer_username} since {since_str} ({duration}).')

    def run_followers(self):
        return self.run_follows()

    def run_follows(self):
        streamer_id = self.twitch_util.get_channel_id(self.streamer_username)
        body = self.twitch_util.helix_get('users/follows', {'to_id': streamer_id, 'first': 1})
        followers = body['total']
        return f'{self.streamer_username} has {followers:,} followers.'

    def run_game(self):
        streamer_id = self.twitch_util.get_channel_id(self.streamer_username)
        data = self.twitch_util.get_stream_data(streamer_id)
        if data == twitch_util.OFFLINE:
            return f'{self.streamer_username} is offline.'
        game = self.twitch_util.game_name(data['game_id'])
        return f'{self.streamer_username} is streaming {game}.'

    def run_subcount(self) -> str:
        return f'There are {self.twitch_util.sub_count():,} subscribers.'

    def run_title(self):
        streamer_id = self.twitch_util.get_channel_id(self.streamer_username)
        data = self.twitch_util.get_stream_data(streamer_id)
        if data == twitch_util.OFFLINE:
            return f'{self.streamer_username} is offline.'
        return f"{self.streamer_username}'s title is: {data['title']}"

    def run_uptime(self):
        streamer_id = self.twitch_util.get_channel_id(self.streamer_username)
        data = self.twitch_util.get_stream_data(streamer_id)
        if data == twitch_util.OFFLINE:
            return f'{self.streamer_username} is offline.'
        started_at = dateutil.parser.isoparse(data['started_at'])
        uptime = datetime.now(timezone.utc) - started_at
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        if hours == 0:
            hours_str = ''
        elif hours == 1:
            hours_str = '1 hour and '
        else:
            hours_str = f'{hours} hours and '
        if minutes == 1:
            minutes_str = '1 minute'
        else:
            minutes_str = f'{minutes} minutes'
        return f'{self.streamer_username} has been live for {hours_str}{minutes_str}.'
