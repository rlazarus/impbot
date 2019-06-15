import itertools
import logging
from typing import Sequence

import flask
from werkzeug import serving

import bot


logger = logging.getLogger(__name__)


class WebServerConnection(bot.Connection):
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

        self.flask = flask.Flask(__name__)
        self.flask.debug = True
        self.flask.use_debugger = True
        self.flask.config["SERVER_NAME"] = f"{host}:{port}"
        self.flask_server = serving.make_server(host, port, self.flask)

    def init_routes(self, connections: Sequence[bot.Connection],
                    handlers: Sequence[bot.Handler]) -> None:
        # TODO: Wrap the view functions in something that arranges for the given
        #       view to be called on the event thread.
        for i in itertools.chain(connections, handlers):
            for url, view, methods in getattr(i, "url_rules", []):
                endpoint = f"{type(i).__name__}.{view.__name__}"
                self.flask.add_url_rule(url, endpoint, view,
                                        methods=methods)

    def say(self, text: str) -> None:
        raise NotImplementedError

    def run(self, on_event: bot.EventCallback) -> None:
        logger.info(self.flask.url_map)
        self.flask.app_context().push()
        self.flask_server.serve_forever()

    def shutdown(self) -> None:
        self.flask_server.shutdown()