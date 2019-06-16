import itertools
import logging
import queue
from typing import Sequence, Optional, Callable, Union, Dict, Tuple

import flask
from flask import views
from werkzeug import serving

import base
import lambda_event

logger = logging.getLogger(__name__)

# ViewResponse is the union of allowed return types from a view function,
# according to Flask docs. (Returning a WSGI application is also allowed,
# omitted here.)
SimpleViewResponse = Union[flask.Response, str, bytes]
ViewResponse = Union[SimpleViewResponse,
                     Tuple[SimpleViewResponse, int, Dict[str, str]],
                     Tuple[SimpleViewResponse, int],
                     Tuple[SimpleViewResponse, Dict[str, str]]]


class WebServerConnection(base.Connection):
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.on_event: Optional[base.EventCallback] = None

        self.flask = flask.Flask(__name__)
        self.flask.debug = True
        self.flask.use_debugger = True
        self.flask.config["SERVER_NAME"] = f"{host}:{port}"
        self.flask_server = serving.make_server(host, port, self.flask)

    def init_routes(self, connections: Sequence[base.Connection],
                    handlers: Sequence[base.Handler]) -> None:
        for connection in connections:
            for url, view, methods in getattr(connection, "url_rules", []):
                endpoint = f"{type(connection).__name__}.{view.__name__}"
                self.flask.add_url_rule(url, endpoint, view,
                                        methods=methods)

        # For Handlers, arrange to call the view function on the Handler thread
        # (in order to make it easy to share data with other Handler methods).
        # In order to do that, wrap the supplied view in a view class that
        # bundles it into a LambdaEvent, then blocks waiting for the result.
        for handler in handlers:
            for url, view, methods in getattr(handler, "url_rules", []):
                endpoint = f"{type(handler).__name__}.{view.__name__}"
                view_func = _DelegatingView.as_view(endpoint, self, view)
                self.flask.add_url_rule(url, view_func=view_func)

    def say(self, text: str) -> None:
        raise NotImplementedError

    def run(self, on_event: base.EventCallback) -> None:
        self.on_event = on_event
        logger.info(self.flask.url_map)
        self.flask.app_context().push()
        self.flask_server.serve_forever()

    def shutdown(self) -> None:
        self.flask_server.shutdown()


class _DelegatingView(views.View):
    def __init__(self, connection: WebServerConnection,
                 subview: Callable[..., ViewResponse]) -> None:
        self.connection = connection
        self.subview = subview

    def dispatch_request(self, *args, **kwargs) -> ViewResponse:
        q = queue.Queue(maxsize=1)
        self.connection.on_event(lambda_event.LambdaEvent(
            run=lambda: q.put(self._run(*args, **kwargs))))
        result = q.get()
        if isinstance(result, BaseException):
            raise RuntimeError from result
        return result

    def _run(self, *args, **kwargs) -> Union[ViewResponse, BaseException]:
        try:
            return self.subview(*args, **kwargs)
        except Exception as e:
            # If the subview raised an exception, we want to reraise it from
            # dispatch_request, so pass it over there via the queue.
            return e
