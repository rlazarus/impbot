import hashlib
import logging
import sys
import threading
from typing import Optional, Union, Dict, List

import attr
import flask
import requests

import secret
from impbot.connections import stdio
from impbot.core import base
from impbot.core import bot
from impbot.core import web
from impbot.core.web import WebServerConnection
from impbot.handlers import hello
from impbot.util import twitch_util
from impbot.util.twitch_util import OFFLINE

logger = logging.getLogger(__name__)

UpdateValue = Union[str, int, List[int]]
UpdateEntry = Dict[str, UpdateValue]
UpdateBody = Dict[str, List[UpdateEntry]]


@attr.s(auto_attribs=True)
class TwitchWebhookEvent(base.Event):
    pass


@attr.s(auto_attribs=True)
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


class TwitchWebhookConnection(base.Connection):
    def __init__(self, streamer_username: str) -> None:
        self.user_id = twitch_util.get_channel_id(streamer_username)
        self.on_event: Optional[base.EventCallback] = None  # Set in run().
        self.last_data = twitch_util.get_stream_data(self.user_id)
        self.shutdown_event = threading.Event()

    def say(self, text: str) -> None:
        raise NotImplementedError("TwitchWebhookConnection doesn't have chat"
                                  "functionality -- use TwitchChatConnection.")

    def run(self, on_event: base.EventCallback) -> None:
        self.on_event = on_event
        self._subscribe()
        # We don't need to do anything -- 100% of the work happens in the web
        # handler now. Just wait until it's time to shut down, then return.
        self.shutdown_event.wait()

    def _subscribe(self) -> None:
        # TODO: Check existing subscriptions, skip if we're already subscribed.
        # TODO: Renew subscription as needed.
        # TODO: Unsubscribe on exit.
        topic = f"https://api.twitch.tv/helix/streams?user_id={self.user_id}"
        self.secret = twitch_util.nonce()
        logger.debug(f"Secret: {self.secret}")
        callback_url = flask.url_for("TwitchWebhookConnection.webhook",
                                     _external=True)
        response = requests.post(
            "https://api.twitch.tv/helix/webhooks/hub",
            json={"hub.callback": callback_url,
                  "hub.mode": "subscribe",
                  "hub.topic": topic,
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

        body = flask.request.json
        try:
            self._parse(body)
        except (KeyError, IndexError):
            logger.exception(f"Unexpected body: {body}")
        # Return 200 even if we couldn't parse the message, per the API docs.
        return flask.Response(status=200)

    def _parse(self, body: UpdateBody) -> None:
        """Parses a JSON update and produces zero or more events."""
        if not body["data"]:
            if self.last_data != OFFLINE:
                self.on_event(StreamEndedEvent())
                self.last_data = OFFLINE
            return

        data = body["data"][0]
        if self.last_data == OFFLINE:
            game = twitch_util.game_name(data["game_id"])
            self.on_event(StreamStartedEvent(data["title"], game))
        else:
            if data["title"] != self.last_data["title"]:
                title = data["title"]
                self.on_event(StreamChangedEvent(title=title, game=None))
            if data["game_id"] != self.last_data["game_id"]:
                game = twitch_util.game_name(data["game_id"])
                self.on_event(StreamChangedEvent(title=None, game=game))
        self.last_data = data

    def shutdown(self) -> None:
        self.shutdown_event.set()


if __name__ == "__main__":
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    rootLogger.addHandler(logging.StreamHandler(sys.stdout))

    connections = [
        WebServerConnection("127.0.0.1", 5000),
        TwitchWebhookConnection("Shrdluuu"),
        stdio.StdioConnection()
    ]
    handlers = [
        hello.HelloHandler(),
    ]
    b = bot.Bot("impbot.sqlite", connections, handlers)
    b.main()
