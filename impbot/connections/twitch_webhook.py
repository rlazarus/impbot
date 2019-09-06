import hashlib
import logging
import sys
import threading
from datetime import datetime
from typing import Optional, Union, List, cast

import attr
import flask
import requests
from mypy_extensions import TypedDict

import secret
from impbot.connections import stdio, twitch
from impbot.core import base
from impbot.core import bot
from impbot.core import web
from impbot.core.web import WebServerConnection
from impbot.handlers import hello
from impbot.util import twitch_util
from impbot.util.twitch_util import OFFLINE

logger = logging.getLogger(__name__)

FollowData = TypedDict("FollowData",
                       {"from_id": str, "from_name": str, "to_id": str,
                        "to_name": str, "followed_at": str})
UpdateBody = TypedDict(
    "UpdateBody",
    {"data": Union[List[FollowData], List[twitch_util.StreamData]]})


class TwitchWebhookEvent(base.Event):
    pass


class StreamEndedEvent(TwitchWebhookEvent):
    pass


@attr.s(auto_attribs=True)
class StreamStartedEvent(TwitchWebhookEvent):
    title: str
    game: str


@attr.s(auto_attribs=True)
class StreamChangedEvent(TwitchWebhookEvent):
    title: Optional[str]
    game: Optional[str]


@attr.s(auto_attribs=True)
class NewFollowerEvent(TwitchWebhookEvent):
    follower_name: str
    time: datetime


class TwitchWebhookConnection(base.Connection):
    def __init__(self, reply_conn: base.ChatConnection,
                 streamer_username: str) -> None:
        self.reply_conn = reply_conn
        self.user_id = twitch_util.get_channel_id(streamer_username)
        self.on_event: Optional[base.EventCallback] = None  # Set in run().
        self.last_data = twitch_util.get_stream_data(self.user_id)
        self.shutdown_event = threading.Event()

    def run(self, on_event: base.EventCallback) -> None:
        self.on_event = on_event
        self._subscribe(f"/streams?user_id={self.user_id}")
        self._subscribe(f"/users/follows?first=1&to_id={self.user_id}")
        # We don't need to do anything -- 100% of the work happens in the web
        # handler now. Just wait until it's time to shut down, then return.
        self.shutdown_event.wait()

    def _subscribe(self, topic) -> None:
        # TODO: Check existing subscriptions, skip if we're already subscribed.
        # TODO: Renew subscription as needed.
        # TODO: Unsubscribe on exit.
        self.secret = twitch_util.nonce()
        logger.debug(f"Secret: {self.secret}")
        callback_url = flask.url_for("TwitchWebhookConnection.webhook",
                                     _external=True)
        response = requests.post(
            "https://api.twitch.tv/helix/webhooks/hub",
            json={"hub.callback": callback_url,
                  "hub.mode": "subscribe",
                  "hub.topic": f"https://api.twitch.tv/helix{topic}",
                  "hub.lease_seconds": 60 * 60 * 24 * 7,
                  "hub.secret": self.secret,
                  },
            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
        if response.status_code != 202:
            logger.error(response.status_code)
            logger.error(response.headers)
            logger.error(response.text)
            raise base.ServerError(response)

    @web.url("/twitch_webhook", methods=["GET", "POST"])
    def webhook(self) -> Union[str, flask.Response]:
        if flask.request.method == "GET":
            logger.debug(f"GET {flask.request.url}")
            logger.debug(flask.request.headers)
            logger.debug(flask.request.data)

            # Subscription request acknowledgement.
            if "hub.challenge" in flask.request.args:
                # Success!
                return flask.request.args["hub.challenge"]
            else:
                # Failure.
                # TODO: The API docs don't have an example of a rejection notice
                #       and I couldn't manage to trigger one, so this is a
                #       guess.
                raise base.ServerError(f"Webhook subscription failed.")

        logger.debug(flask.request.headers)
        logger.debug(flask.request.json)

        # TODO: The signature doesn't match. Does request.data come back empty
        #       if request.json has already been accessed? If so, only go
        #       through request.data and call json.loads ourselves (since we
        #       need the SHA-256 of the original bytes). We'll know if "Body
        #       length: 0" is logged.
        # TODO: Once that's debugged, ignore messages with the wrong secret.
        sha256 = hashlib.sha256()
        sha256.update(self.secret.encode())
        sha256.update(flask.request.data)
        expected_signature = sha256.hexdigest()
        logger.debug(f"Expected signature: {expected_signature}")
        logger.debug(f"Body length: {len(flask.request.data)}")

        topic = _topic(flask.request.headers["Link"])
        body = flask.request.json
        try:
            self._parse(topic, body)
        except (KeyError, IndexError):
            logger.exception(f"Unexpected body: {body}")
        # Return 200 even if we couldn't parse the message, per the API docs.
        return flask.Response(status=200)

    def _parse(self, topic: str, body: UpdateBody) -> None:
        # Safe to cast away the Optional because on_event is set first in run().
        # (Calls to _parse come from the web server, not from this connection
        # -- but requests won't come until after we subscribe in run(), so
        # there's still no race in practice.)
        self.on_event = cast(base.EventCallback, self.on_event)
        """Parses a JSON update and produces zero or more events."""
        if "/streams" in topic:
            if not body["data"]:
                if self.last_data != OFFLINE:
                    self.on_event(StreamEndedEvent(self.reply_conn))
                    self.last_data = OFFLINE
                return

            data = body["data"][0]
            data = cast(twitch_util.OnlineStreamData, data)
            if self.last_data == OFFLINE:
                game = twitch_util.game_name(int(data["game_id"]))
                self.on_event(StreamStartedEvent(
                    self.reply_conn, data["title"], game))
            else:
                if data["title"] != self.last_data["title"]:
                    title = data["title"]
                    self.on_event(StreamChangedEvent(
                        self.reply_conn, title=title, game=None))
                if data["game_id"] != self.last_data["game_id"]:
                    game = twitch_util.game_name(int(data["game_id"]))
                    self.on_event(StreamChangedEvent(
                        self.reply_conn, title=None, game=game))
            self.last_data = data
        elif "/follows" in topic:
            data = body["data"][0]
            data = cast(FollowData, data)
            time = datetime.strptime(data["followed_at"], "%Y-%m-%dT%H:%M:%S%z")
            self.on_event(NewFollowerEvent(
                self.reply_conn, data["from_name"], time))

    def shutdown(self) -> None:
        self.shutdown_event.set()


if __name__ == "__main__":
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    rootLogger.addHandler(logging.StreamHandler(sys.stdout))

    chat = twitch.TwitchChatConnection("BotAltBTW", secret.BOTALTBTW_OAUTH,
                                       "Shrdluuu", [])
    connections = [
        WebServerConnection("127.0.0.1", 5000),
        chat,
        TwitchWebhookConnection(chat, "Shrdluuu"),
        stdio.StdioConnection()
    ]
    handlers = [
        hello.HelloHandler(),
    ]
    b = bot.Bot("impbot.sqlite", connections, handlers)
    b.main()


def _topic(link_header: str) -> str:
    """Parses an HTTP Link: header and returns the message topic."""
    # Example header:
    # Link: <https://api.twitch.tv/helix/webhooks/hub>; rel="hub", <https://api.twitch.tv/helix/streams?user_id=1234>; rel="self"
    links = link_header.split(", ")
    for link in links:
        url, rel = link.split("; ", 1)
        if rel == 'rel="self"':
            return url[1:-1]  # Strip off <>.
    raise base.ServerError(f'No rel="self": {link_header}')
