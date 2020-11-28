import datetime
import functools
import logging
import random
import string
import threading
from typing import Dict, Union, Optional, List, Any, Set, Tuple, Iterable
from urllib import parse

import requests
from irc import client
from mypy_extensions import TypedDict

import secret
from impbot.core import base
from impbot.core import data
from impbot.util import cooldown

logger = logging.getLogger(__name__)


class TwitchOAuth:
    def __init__(self, streamer_username: str):
        self.streamer_username = streamer_username
        self.data = data.Namespace("impbot.util.twitch_util.TwitchOAuth")
        self.lock = threading.Lock()

    def maybe_authorize(self) -> None:
        """
        Go through the initial authorization flow if it's our first time running
        and we don't have an access code yet.
        """
        with self.lock:
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
            "bits:read",  # For TwitchEventConnection
            "channel_subscriptions",  # For TwitchEventConnection
            "channel_editor",  # For TwitchEditorHandler
            "channel:read:redemptions",  # For TwitchEventConnection
            # For TwitchUtil.irc_command_as_streamer() and (channel:moderate)
            # also for TwitchEventConnection:
            "chat:edit", "chat:read", "channel:moderate",
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
        with self.lock:  # Hold the lock between the DB read and writes.
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
        body = response.json()
        if "error" in body:
            raise base.ServerError(body)
        self.data.set("access_token", body["access_token"])
        self.data.set("refresh_token", body["refresh_token"])


OnlineStreamData = TypedDict("OnlineStreamData",
                             {"id": str, "user_id": str, "user_name": str,
                              "game_id": str, "community_ids": List[str],
                              "type": str, "title": str, "viewer_count": int,
                              "started_at": str, "language": str,
                              "thumbnail_url": str})
OfflineStreamData = TypedDict("OfflineStreamData", {})  # Always empty.
StreamData = Union[OnlineStreamData, OfflineStreamData]
OFFLINE = OfflineStreamData()


class TwitchUtil:
    def __init__(self, oauth: TwitchOAuth):
        self.oauth = oauth
        self.streamer_username = oauth.streamer_username
        self._cached_sub_count: Optional[int] = None
        self._sub_count_ttl = cooldown.Cooldown(datetime.timedelta(minutes=5))
        self._channel_id_cache: Dict[str, int] = {}

    def get_channel_id(self, streamer_username: str) -> int:
        result = self.get_channel_ids([streamer_username])
        if not result:
            raise KeyError(f"No Twitch channel '{streamer_username}'")
        return list(result)[0]

    def get_channel_ids(self, streamer_usernames: Iterable[str]) -> Set[int]:
        streamer_usernames = list(streamer_usernames)
        result = set()
        to_fetch: List[str] = []
        # First, grab any that we already have from cache.
        for name in streamer_usernames:
            name = name.lower()
            try:
                result.add(self._channel_id_cache[name])
            except KeyError:
                to_fetch.append(name)
        # Break the list up into multiple requests, asking for at most 100 names
        # at a time (per the API docs).
        for i in range(0, len(to_fetch), 100):
            body = self.helix_get(
                "users", [("login", name) for name in to_fetch[i:i+100]])
            # We *don't* check that all names are present -- if any of the input
            # names were bogus, then the output will be smaller than the input.
            for user in body["data"]:
                result.add(int(user["id"]))
                self._channel_id_cache[user["login"]] = int(user["id"])
        return result

    def get_display_name(self, username: str) -> str:
        return self._get_display_name(username.lower())

    @functools.lru_cache()
    def _get_display_name(self, username: str) -> str:
        body = self.helix_get("users", {"login": username})
        if not body["data"]:
            raise KeyError(f"No Twitch user '{username}")
        return body["data"][0]["display_name"]

    def get_stream_data(self, user_id: Optional[int] = None,
                        username: Optional[str] = None) -> StreamData:
        if user_id:
            body = self.helix_get("streams", params={"user_id": user_id})
        elif username:
            body = self.helix_get("streams", params={"user_login": username})
        else:
            raise ValueError("Must pass either user_id or username.")
        if not body["data"]:
            return OFFLINE
        return body["data"][0]

    def game_name(self, game_id: int) -> str:
        body = self.helix_get("games", {"id": game_id})
        if not body["data"]:
            raise base.ServerError(f"No Game with ID {game_id}")
        return body["data"][0]["name"]

    def sub_count(self) -> int:
        if not self._sub_count_ttl.fire():
            return self._cached_sub_count
        id = self.get_channel_id(self.streamer_username)
        response = self.kraken_get(f"channels/{id}/subscriptions",
                                   params={"limit": 1})
        self._cached_sub_count = response['_total']
        return response['_total']

    def helix_get(self, path: str,
                  params: Union[Dict[str, Any], List[Tuple[str, Any]]],
                  expected_status: int = 200) -> Dict:
        request = requests.Request(
            method="GET",
            url=f"https://api.twitch.tv/helix/{path}",
            params=params)
        return self._request(request, "Bearer", expected_status=expected_status)

    def helix_post(self, path: str, json: Dict[str, Any],
                   expected_status: int = 200) -> Dict:
        request = requests.Request(
            method="POST",
            url=f"https://api.twitch.tv/helix/{path}",
            json=json)
        return self._request(request, "Bearer", expected_status=expected_status)

    def kraken_get(self, path: str,
                   params: Optional[Dict[str, Any]] = None) -> Dict:
        request = requests.Request(
            method="GET",
            url=f"https://api.twitch.tv/kraken/{path}",
            params=params,
            headers={"Accept": "application/vnd.twitchtv.v5+json"})
        return self._request(request, "OAuth")

    def kraken_put(self, path: str, json: Dict[str, Any] = None) -> Dict:
        request = requests.Request(
            method="PUT",
            url=f"https://api.twitch.tv/kraken/{path}",
            json=json,
            headers={"Accept": "application/vnd.twitchtv.v5+json"})
        return self._request(request, "OAuth")

    def _request(self, request, auth_type: str,
                 expected_status: int = 200) -> Dict:
        request.headers["Client-ID"] = secret.TWITCH_CLIENT_ID
        if auth_type:
            request.headers.update(
                {"Authorization": f"{auth_type} {self.oauth.access_token}"})
        with requests.Session() as s:
            response = s.send(request.prepare())
        if response.status_code == 401 and auth_type:
            self.oauth.refresh()
            request.headers.update(
                {"Authorization": f"{auth_type} {self.oauth.access_token}"})
            with requests.Session() as s:
                response = s.send(request.prepare())
        if response.status_code != expected_status:
            logging.error(request.prepare())
            logging.error(f"{request.method} {request.url} {request.params} "
                          f"{request.headers}")
            logging.error(f"{response.status_code} {response.text}")
            raise base.ServerError(f"{response.status_code} {response.text}")
        if not response.text:
            return {}
        return response.json()

    def irc_command_as_streamer(self, commands: Union[str, List[str]]):
        if isinstance(commands, str):
            commands = [commands]

        channel = "#" + self.oauth.streamer_username.lower()

        def on_welcome(connection: client.ServerConnection, _: client.Event):
            for command in commands:
                connection.privmsg(channel, command)
            connection.disconnect()

        self.oauth.refresh()
        reactor = client.Reactor()
        connection = reactor.server().connect(
            "irc.chat.twitch.tv", 6667, self.oauth.streamer_username.lower(),
            password=f"oauth:{self.oauth.access_token}")
        connection.add_global_handler("welcome", on_welcome)
        while connection.is_connected():
            reactor.process_once(0.2)


def nonce() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=30))
