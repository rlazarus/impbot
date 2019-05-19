import hashlib
import logging
import sys
from typing import Optional, Dict, Union

import attr
import flask
import requests
from werkzeug import serving

import bot
import hello
import secret
import stdio
import twitch_util

logger = logging.getLogger(__name__)

StreamData = Dict[str, Union[str, int]]
OFFLINE: StreamData = dict()


@attr.s(auto_attribs=True)
class TwitchWebhookEvent(bot.Event):
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


class TwitchWebhookConnection(bot.Connection):
    def __init__(self, streamer_username: str, host: str, port: int) -> None:
        self.user_id = twitch_util.get_channel_id(streamer_username)
        self.on_event: bot.EventCallback = None  # Set in run().
        self.last_data: StreamData = _stream_data(self.user_id)
        # TODO: Move this out to Bot, there should only be one of it.
        self.flask = flask.Flask(__name__)
        self.flask.config["SERVER_NAME"] = f"{host}:{port}"
        self.flask_server = serving.make_server(host, port, self.flask)

    def say(self, text: str) -> None:
        raise NotImplementedError("TwitchWebhookConnection doesn't have chat"
                                  "functionality -- use TwitchChatConnection.")

    def run(self, on_event: bot.EventCallback) -> None:
        self.on_event = on_event
        self.flask.add_url_rule("/twitch_webhook", "webhook", self._webhook,
                                methods=["GET", "POST"])

        # Technically this is a little racy, since the Flask server might not be
        # listening for an acknowledgement by the time Twitch tries to send it.
        # But that's okay -- in practice it does start up in time, and if not,
        # Twitch will retry.
        self._subscribe()

        self.flask.app_context().push()
        self.flask_server.serve_forever()

    def _subscribe(self) -> None:
        # TODO: Check existing subscriptions, skip if we're already subscribed.
        # TODO: Renew subscription as needed.
        # TODO: Unsubscribe on exit.
        topic = f"https://api.twitch.tv/helix/streams?user_id={self.user_id}"
        self.secret = twitch_util.nonce()
        logger.debug(f"Secret: {self.secret}")
        with self.flask.app_context():
            callback_url = flask.url_for("webhook", _external=True)
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
            raise bot.ServerError(response)

    def _webhook(self) -> Union[str, flask.Response]:
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
                raise bot.ServerError(f"Webhook subscription failed.")

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
        if 'data' not in body:
            # This should be a bot.ServerError, but Twitch expects us to return
            # 200 OK no matter what.
            # TODO: Consider separating the parsing out of the Flask handler, so
            #       that we can do both.
            logger.error("Unexpected body")
        if not body["data"]:
            if self.last_data != OFFLINE:
                self.on_event(StreamEndedEvent())
                self.last_data = OFFLINE
            return flask.Response(status=200)
        data = body["data"][0]
        if self.last_data == OFFLINE:
            game = _game_name(data["game_id"])
            self.on_event(StreamStartedEvent(data["title"], game))
        else:
            if data["title"] != self.last_data["title"]:
                title = data["title"]
                self.on_event(StreamChangedEvent(title=title, game=None))
            if data["game_id"] != self.last_data["game_id"]:
                game = _game_name(data["game_id"])
                self.on_event(StreamChangedEvent(title=None, game=game))
        self.last_data = data
        return flask.Response(status=200)

    def shutdown(self) -> None:
        self.flask_server.shutdown()


def _stream_data(user_id: int) -> StreamData:
    response = requests.get("https://api.twitch.tv/helix/streams",
                            params={"user_id": user_id},
                            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
    if response.status_code != 200:
        raise bot.ServerError(response)
    body = response.json()
    if not body["data"]:
        return OFFLINE
    return body["data"][0]


def _game_name(game_id: int) -> str:
    response = requests.get("https://api.twitch.tv/helix/games",
                            params={"id": game_id},
                            headers={"Client-ID": secret.TWITCH_CLIENT_ID})
    if response.status_code != 200:
        raise bot.ServerError(response)
    body = response.json()
    if not body["data"]:
        raise bot.ServerError(f"No Game with ID {game_id}")
    return body["data"][0]["name"]


if __name__ == "__main__":
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    rootLogger.addHandler(logging.StreamHandler(sys.stdout))

    connections = [
        TwitchWebhookConnection("Shrdluuu", "127.0.0.1", 5000),
        stdio.StdioConnection()
    ]
    handlers = [
        hello.HelloHandler(),
    ]
    b = bot.Bot("impbot.sqlite", connections, handlers)
    b.main()
