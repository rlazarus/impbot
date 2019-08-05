import functools
import json
import logging
import random
import string
from typing import Dict, Union, Optional
from urllib import parse

import requests

import secret
from impbot.core import base
from impbot.core import data

logger = logging.getLogger(__name__)


class TwitchOAuth:
    def __init__(self, streamer_username: str):
        self.streamer_username = streamer_username
        # TODO: Migrate this over in the DB and rename the namespace.
        self.data = data.Namespace("TwitchEventConnection")

    def maybe_authorize(self) -> None:
        """
        Go through the initial authorization flow if it's our first time running
        and we don't have an access code yet.
        """
        if not self.has_access_token:
            self.authorize()

    def authorize(self) -> None:
        # TODO: Now that there's a web server built in, do the server side of
        #   this authorization flow properly, rather than fishing it out of
        #   HTTP logs and entering it by hand.
        # TODO: Better yet, set up a persistent web service shared by all Impbot
        #   installations -- that service should be the host for the OAuth
        #   redirect URI, and should hold the Twitch client secret. Until then,
        #   other installations need to register with Twitch and get their own
        #   client secret.
        scopes = [
            "bits:read",              # For TwitchEventConnection
            "channel_subscriptions",  # For TwitchEventConnection
            "channel_editor",         # For TwitchEditorHandler
        ]
        params = parse.urlencode({"client_id": secret.TWITCH_CLIENT_ID,
                                  "redirect_uri": secret.TWITCH_REDIRECT_URI,
                                  "response_type": "code",
                                  "scope": " ".join(scopes)})
        access_code = input(
            f"While logged into Twitch as {self.streamer_username}, please "
            f"visit: https://id.twitch.tv/oauth2/authorize?{params}\n"
            f"Access code: ")
        self._fetch({"grant_type": "authorization_code",
                     "code": access_code,
                     "redirect_uri": secret.TWITCH_REDIRECT_URI})
        logger.info("Twitch OAuth: Authorized!")

    def refresh(self) -> None:
        self._fetch({"grant_type": "refresh_token",
                     "refresh_token": self.data.get("refresh_token")})
        logger.info("Twitch OAuth: Refreshed!")

    @property
    def has_access_token(self) -> bool:
        return self.data.exists("access_token")

    @property
    def access_token(self) -> str:
        return self.data.get("access_token")

    def _fetch(self, params: Dict[str, str]) -> None:
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": secret.TWITCH_CLIENT_ID,
                "client_secret": secret.TWITCH_CLIENT_SECRET,
                **params
            })
        if response.status_code != 200:
            raise base.ServerError(f"{response.status_code} {response.text}")
        body = json.loads(response.text)
        if "error" in body:
            raise base.ServerError(body)
        self.data.set("access_token", body["access_token"])
        self.data.set("refresh_token", body["refresh_token"])


def get_channel_id(streamer_username: str) -> int:
    # Canonicalize the username to share a cache entry.
    return _get_channel_id(streamer_username.lower())


@functools.lru_cache()
def _get_channel_id(streamer_username: str) -> int:
    response = requests.get("https://api.twitch.tv/helix/users",
                            params={"login": streamer_username},
                            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
    if response.status_code != 200:
        raise base.ServerError(f"{response.status_code} {response.text}")
    body = json.loads(response.text)
    if not body["data"]:
        raise base.AdminError(f"No Twitch channel '{streamer_username}'")
    return int(body["data"][0]["id"])


def nonce() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=30))


StreamData = Dict[str, Union[str, int]]
OFFLINE: StreamData = dict()


def get_stream_data(user_id: Optional[int] = None,
                    username: Optional[str] = None) -> StreamData:
    if user_id:
        params: Dict[str, Union[str, int]] = {"user_id": user_id}
    elif username:
        params = {"user_login": username}
    else:
        raise ValueError("Must pass either user_id or username.")
    response = requests.get("https://api.twitch.tv/helix/streams",
                            params=params,
                            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
    if response.status_code != 200:
        raise base.ServerError(f"{response.status_code} {response.text}")
    body = response.json()
    if not body["data"]:
        return OFFLINE
    return body["data"][0]


def game_name(game_id: int) -> str:
    response = requests.get("https://api.twitch.tv/helix/games",
                            params={"id": game_id},
                            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
    if response.status_code != 200:
        raise base.ServerError(f"{response.status_code} {response.text}")
    body = response.json()
    if not body["data"]:
        raise base.ServerError(f"No Game with ID {game_id}")
    return body["data"][0]["name"]
