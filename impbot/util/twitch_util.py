import datetime
import functools
import logging
import queue
import random
import string
import threading
from typing import Dict, Union, Optional, List, Any, Set, Tuple, Iterable, \
    Container, Literal
from urllib import parse

import flask
import requests
from irc import client
from mypy_extensions import TypedDict

import secret
from impbot.core import base, web
from impbot.core import data
from impbot.util import cooldown

logger = logging.getLogger(__name__)


class TwitchOAuth:
    def __init__(self, streamer_username: str):
        self.streamer_username = streamer_username
        self.data = data.Namespace("impbot.util.twitch_util.TwitchOAuth")
        self.lock = threading.Lock()
        self.auth_finished = threading.Event()
        # TODO: In principle you could DoS this by starting a bunch of OAuth
        #  flows, so that this would consume too much memory. The fix is to make
        #  it a FIFO queue instead of (or in addition to) a hash set -- but
        #  frankly there are more effective ways to DoS a chat bot anyway.
        self.states = set()

    def maybe_authorize(self) -> None:
        """
        Go through the initial authorization flow if it's our first time running
        and we don't have an access code yet.
        """
        with self.lock:
            if not self.has_access_token:
                self.authorize()

    def authorize(self) -> None:
        # TODO: Consider setting up a persistent web service shared by all
        #   Impbot installations -- that service should be the host for the
        #   OAuth redirect URI, and should hold the Twitch client secret. Until
        #   then, other installations need to register with Twitch and get their
        #   own client secret.
        logger.critical(
            "While logged into Twitch as %s, please visit %s",
            self.streamer_username,
            flask.url_for("TwitchOAuthWebHandler.login", _scheme="https"))
        self.auth_finished.wait()
        logger.info("Twitch OAuth: Authorized!")

    def authorize_url(self) -> str:
        scopes = [
            "bits:read",  # For TwitchEventConnection
            "channel_subscriptions",  # For TwitchEventConnection
            "channel_editor",  # For TwitchEditorHandler
            "channel:read:redemptions",  # For TwitchEventConnection
            "chat:edit",  # For TwitchUtil._irc_command_as_streamer()
            "chat:read",  # For TwitchUtil._irc_command_as_streamer()
            # TwitchUtil._irc_command_as_streamer() and TwitchEventConnection:
            "channel:moderate",
        ]
        state = nonce()
        self.states.add(state)
        params = parse.urlencode({"client_id": secret.TWITCH_CLIENT_ID,
                                  "redirect_uri": secret.TWITCH_REDIRECT_URI,
                                  "response_type": "code",
                                  "scope": " ".join(scopes),
                                  "state": state})
        url = f"https://id.twitch.tv/oauth2/authorize?{params}"
        return url

    def finish_authorization(self, code: str) -> None:
        try:
            access_token, refresh_token = self._fetch({
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": secret.TWITCH_REDIRECT_URI,
            })
        except base.ServerError:
            logger.exception("Couldn't exchange code for token")
            raise

        response = requests.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Client-ID": secret.TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {access_token}"
            })
        if response.status_code != 200:
            logging.error(
                "Couldn't fetch user info with new bearer token: %d %s",
                response.status_code, response.text)
            raise base.ServerError(f"{response.status_code} {response.text}")
        body = response.json()
        login = body["data"][0]["login"]
        if login != self.streamer_username.lower():
            display_name = body["data"][0]["display_name"]
            raise base.UserError(
                f"You're logged into Twitch as {display_name}. Please log in "
                f"as {self.streamer_username} to authorize the bot.")

        self.data.set("access_token", access_token)
        self.data.set("refresh_token", refresh_token)
        self.auth_finished.set()

    def refresh(self) -> None:
        with self.lock:  # Hold the lock between the DB read and writes.
            access_token, refresh_token = self._fetch({
                "grant_type": "refresh_token",
                "refresh_token": self.data.get("refresh_token"),
            })
            self.data.set("access_token", access_token)
            self.data.set("refresh_token", refresh_token)
        logger.info("Twitch OAuth: Refreshed!")

    @property
    def has_access_token(self) -> bool:
        return self.data.exists("access_token")

    @property
    def access_token(self) -> str:
        return self.data.get("access_token")

    def refresh_app_access_token(self) -> None:
        access_token, refresh_token = self._fetch(
            {"grant_type": "client_credentials"})
        # There's no refresh token in this case, since we refresh with the
        # client ID and secret.
        self.data.set("app_access_token", access_token)

    @property
    def app_access_token(self) -> str:
        try:
            return self.data.get("app_access_token")
        except KeyError:
            self.refresh_app_access_token()
            return self.data.get("app_access_token")

    def _fetch(self, params: Dict[str, str]) -> Tuple[str, str]:
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
        return body["access_token"], body.get("refresh_token", "")


class NullEvent(base.Event):
    pass


class TwitchOAuthWebHandler(base.Handler[NullEvent]):
    # TODO: This is a little hacky, but right now @web.url can only be used on
    #  Connections and Handlers. This *only* needs to be a web endpoint, so we
    #  create an event type that'll never be seen, and "handle" it.
    def __init__(self, twitch_oauth: TwitchOAuth):
        super().__init__()
        self.twitch_oauth = twitch_oauth

    def check(self, event: NullEvent) -> bool:
        return False

    def run(self, event: NullEvent) -> Optional[str]:
        pass

    @web.url("/login")
    def login(self):
        return flask.redirect(self.twitch_oauth.authorize_url())

    @web.url("/oauth/redirect")
    def oauth_redirect(self):
        try:
            state = flask.request.args["state"]
        except KeyError:
            return "Missing state parameter", 400

        try:
            self.twitch_oauth.states.remove(state)
        except KeyError:
            logger.error("Expected states %s / got %s",
                         self.twitch_oauth.states, state)
            return "Wrong state parameter", 403

        try:
            code = flask.request.args["code"]
        except KeyError:
            return "Missing code parameter", 400

        try:
            self.twitch_oauth.finish_authorization(code)
        except base.ServerError:
            # Already logged, in finish_authorization().
            return "Authorization error", 400
        except base.UserError as e:
            return str(e), 400

        return (f"Logged in as {self.twitch_oauth.streamer_username}, thanks! "
                "You can close the tab now.")


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
                "users", [("login", name) for name in to_fetch[i:i + 100]])
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
                  token_type: Literal["user", "app"] = "user",
                  expected_status: int = 200) -> Dict:
        request = requests.Request(
            method="GET",
            url=f"https://api.twitch.tv/helix/{path}",
            params=params)
        return self._request(request, "Bearer", token_type=token_type,
                             expected_status=expected_status)

    def helix_post(self, path: str, json: Dict[str, Any],
                   token_type: Literal["user", "app"] = "user",
                   expected_status: int = 200) -> Dict:
        request = requests.Request(
            method="POST",
            url=f"https://api.twitch.tv/helix/{path}",
            json=json)
        return self._request(request, "Bearer", token_type=token_type,
                             expected_status=expected_status)

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
                 token_type: Literal["user", "app"] = "user",
                 expected_status: int = 200) -> Dict:
        request.headers["Client-ID"] = secret.TWITCH_CLIENT_ID
        if auth_type:
            token = (self.oauth.access_token if token_type == "user"
                     else self.oauth.app_access_token)
            request.headers.update({"Authorization": f"{auth_type} {token}"})
        with requests.Session() as s:
            response = s.send(request.prepare())
        if response.status_code == 401 and auth_type:
            if token_type == "user":
                self.oauth.refresh()
                token = self.oauth.access_token
            else:
                self.oauth.refresh_app_access_token()
                token = self.oauth.app_access_token
            request.headers.update(
                {"Authorization": f"{auth_type} {token}"})
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

    def mod(self, usernames: Union[str, List[str]]) -> None:
        if isinstance(usernames, str):
            usernames = [usernames]
        self._irc_command_as_streamer(
            [f".mod {name}" for name in usernames], "mod_success",
            {"bad_mod_banned", "bad_mod_mod"})

    def unmod(self, usernames: Union[str, List[str]]) -> None:
        if isinstance(usernames, str):
            usernames = [usernames]
        self._irc_command_as_streamer(
            [f".unmod {name}" for name in usernames], "unmod_success",
            {"bad_unmod_mod"})

    def vip(self, usernames: Union[str, List[str]]) -> None:
        if isinstance(usernames, str):
            usernames = [usernames]
        self._irc_command_as_streamer(
            [f".vip {name}" for name in usernames], "vip_success",
            {"bad_vip_grantee_banned", "bad_vip_grantee_already_vip",
             "bad_vip_achievement_incomplete"})

    def unvip(self, usernames: Union[str, List[str]]) -> None:
        if isinstance(usernames, str):
            usernames = [usernames]
        self._irc_command_as_streamer(
            [f".unvip {name}" for name in usernames], "unvip_success",
            {"bad_unvip_grantee_not_vip"})

    def _irc_command_as_streamer(
            self, commands: Union[str, List[str]], success_msg: str,
            failure_msgs: Container[str], retry_on_error: bool = True) -> None:
        if isinstance(commands, str):
            commands = [commands]

        channel = "#" + self.oauth.streamer_username.lower()
        pubnotices = queue.Queue()
        welcome = threading.Event()

        def on_welcome(_c: client.ServerConnection, _e: client.Event) -> None:
            welcome.set()

        def on_pubnotice(
                _: client.ServerConnection, event: client.Event) -> None:
            msg_ids = [i["value"] for i in event.tags if i["key"] == "msg-id"]
            if not msg_ids:
                return
            if len(msg_ids) > 1:
                logger.error("Multiple msg-id tags: %s", event)
                # ... but continue anyway, and just use the first one.
            pubnotices.put(msg_ids[0])

        self.oauth.refresh()
        reactor = client.Reactor()
        connection = reactor.server().connect(
            "irc.chat.twitch.tv", 6667, self.oauth.streamer_username.lower(),
            password=f"oauth:{self.oauth.access_token}")
        connection.add_global_handler("welcome", on_welcome)
        connection.add_global_handler("pubnotice", on_pubnotice)
        reactor.process_once(timeout=5)
        if not welcome.wait(timeout=5):
            connection.disconnect()
            if retry_on_error:
                self._irc_command_as_streamer(
                    commands, success_msg, failure_msgs, retry_on_error=False)
                return
            else:
                raise base.ServerError("WELCOME not received.")
        connection.cap("REQ", "twitch.tv/commands", "twitch.tv/tags")
        connection.cap("END")
        reactor.process_once(timeout=5)
        for command in commands:
            connection.privmsg(channel, command)
            result = ""
            unknown_msgs = []
            deadline = (datetime.datetime.utcnow() +
                        datetime.timedelta(seconds=10))
            while result == "" and datetime.datetime.utcnow() < deadline:
                timeout = deadline - datetime.datetime.utcnow()
                reactor.process_once(timeout=timeout.total_seconds())
                while True:
                    try:
                        msg = pubnotices.get_nowait()
                    except queue.Empty:
                        break
                    if ((msg == success_msg or msg in failure_msgs) and
                            result == ""):
                        result = msg
                    else:
                        unknown_msgs.append(msg)
            if result == success_msg:
                logger.info("%s: success", command)
            elif result:
                logger.error("%s: %s", command, result)
            else:
                if unknown_msgs:
                    logger.error("%s: No response. Unknown pubnotices: %s",
                                 command, unknown_msgs)
                else:
                    logger.error("%s: No response.")
                if retry_on_error:
                    connection.disconnect()
                    self._irc_command_as_streamer(
                        commands, success_msg, failure_msgs,
                        retry_on_error=False)
                    return
        connection.disconnect()


def nonce() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=30))
