import functools
import logging
import queue
from typing import Sequence, Optional, Union, Dict, Any, Type, cast

import flask
from flask import views
from werkzeug import serving

from impbot.core import base
from impbot.handlers import lambda_event

logger = logging.getLogger(__name__)


class WebServerConnection(base.Connection):
    def __init__(self, host: str, port: int) -> None:
        self.on_event: Optional[base.EventCallback] = None
        self.flask = flask.Flask(__name__)
        self.flask.config["SERVER_NAME"] = f"{host}:{port}"
        self.flask_server = serving.make_server(host, port, self.flask)

    def init_routes(self, connections: Sequence[base.Connection],
                    handlers: Sequence[base.Handler]) -> None:
        for connection in connections:
            for url, view_func, options in connection.url_rules:
                endpoint = f"{type(connection).__name__}.{view_func.__name__}"
                # The class's url_rules stores the unbound method (because the
                # @url decorator kicks in before the instance is created) so
                # bind it to the instance now.
                view_func = functools.partial(view_func, connection)
                self.flask.add_url_rule(url, endpoint, view_func, **options)

        # For Handlers, arrange to call the view function on the Handler thread
        # (in order to make it easy to share data with other Handler methods).
        # In order to do that, wrap the supplied view in a view class that
        # bundles it into a LambdaEvent, then blocks waiting for the result.
        for handler in handlers:
            for url, view_func, options in handler.url_rules:
                endpoint = f"{type(handler).__name__}.{view_func.__name__}"
                view_func = functools.partial(view_func, handler)
                view_func = _DelegatingView.as_view(endpoint, self, view_func)
                self.flask.add_url_rule(url, view_func=view_func, **options)

    def say(self, text: str) -> None:
        raise NotImplementedError

    def run(self, on_event: base.EventCallback) -> None:
        self.on_event = on_event
        self.flask.app_context().push()
        self.flask_server.serve_forever()

    def shutdown(self) -> None:
        self.flask_server.shutdown()


class _DelegatingView(views.View):
    """
    A Flask View that wraps another View and runs it on the bot's event thread.

    When a _DelegatingView receives a request, it places a LambdaEvent on the
    main event queue. Over on the event thread, the event dispatcher will call
    that event's lambda, which passes the request to the subview. (Meanwhile,
    the _DelegatingView's thread is blocked.)

    When the subview finishes and returns a response, the lambda hands that
    response back to the WebServerConnection thread via a single-use queue. This
    unblocks the _DelegatingView, and it returns the same response.
    """

    def __init__(self, connection: WebServerConnection,
                 subview: base.ViewFunc) -> None:
        self.connection = connection
        self.subview = subview

    def dispatch_request(self, *args: Any, **kwargs: Any) -> base.ViewResponse:
        q: queue.Queue[Union[base.ViewResponse, Exception]] = queue.Queue(
            maxsize=1)
        event = lambda_event.LambdaEvent(lambda: self._run(q, *args, **kwargs))
        # We can cast away the Optional from on_event because it's set in the
        # connection's run(), before the Flask server is started.
        cast(base.EventCallback, self.connection.on_event)(event)
        result = q.get()
        if isinstance(result, Exception):
            raise RuntimeError from result
        return result

    def _run(self, q: queue.Queue, *args: Any, **kwargs: Any) -> None:
        try:
            q.put(self.subview(*args, **kwargs))
        except Exception as e:
            # If the subview raised an exception, we want to reraise it from
            # dispatch_request, so pass it over there via the queue.
            q.put(e)


def url(url: str, **options):
    """
    Decorator that turns a Connection or Handler method into a web view.

    The args are as Flask's app.route decorator.
    """
    return functools.partial(_UrlDecorator, url, options)


class _UrlDecorator:
    def __init__(self, url: str, options: Dict[str, Any], func: base.ViewFunc):
        self.url = url
        self.options = options
        self.func = func

    def __set_name__(self, owner: Type[Union[base.Connection, base.Handler]],
                     name: str):
        # We want to modify owner's url_rules, not the one inherited from
        # Connection or Handler.
        if "url_rules" not in owner.__dict__:
            owner.url_rules = []
        owner.url_rules.append((self.url, self.func, self.options))
        setattr(owner, name, self.func)
