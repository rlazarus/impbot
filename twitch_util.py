import json
import random
import string

import requests

import bot
import secret


def get_channel_id(streamer_username: str) -> int:
    # TODO: Memoize.
    response = requests.get("https://api.twitch.tv/helix/users",
                            params={"login": streamer_username},
                            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
    if response.status_code != 200:
        raise bot.ServerError(response)
    body = json.loads(response.text)
    if not body["data"]:
        raise bot.AdminError(f"No Twitch channel '{streamer_username}'")
    return int(body["data"][0]["id"])


def nonce() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=30))