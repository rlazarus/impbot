import logging
from typing import Any, Dict, Optional

import requests

import secret

logger = logging.getLogger(__name__)


class DiscordLogger:
    def __init__(self, channel_id: int):
        # TODO: Check that we already have access to the guild and the channel, and prompt with the
        #  invite link if we don't.
        self.channel_id = channel_id

    def embed(self, color: int, text: str, fields: Optional[Dict[str, str]] = None) -> None:
        if fields is None:
            fields = {}
        embed = {
            'description': text,
            'color': color,
            'fields': [{'name': name, 'value': value} for name, value in fields.items()]
        }
        self._post_message(embed=embed, allowed_mentions={'parse': []})

    def say(self, text: str) -> None:
        self._post_message(content=text, allowed_mentions={'parse': []})

    def _post_message(self, **json: Any) -> None:
        response = requests.post(f'https://discord.com/api/v6/channels/{self.channel_id}/messages',
                                 json=json,
                                 headers={
                                     'Authorization': f'Bot {secret.DISCORD_BOT_TOKEN}',
                                     'User-Agent': 'Impbot',
                                 })
        if response.status_code != 200:
            logging.error(f'{response.status_code} {response.text}')
