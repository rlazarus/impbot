import functools
import logging
import queue
import sys
from os import path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Type, Union, cast

import flask
from flask import views
from werkzeug import serving

from impbot.core import base
from impbot.handlers import lambda_event

logger = logging.getLogger(__name__)


class WebServerConnection(base.Connection):
    def __init__(self, bind_host: str, bind_port: int, url_host: str) -> None:
        """
        `bind_host` and `bind_port` are the address to actually bind a network socket to, while
        `url_host` is the user-facing host used in URLs.

        For example, if running behind a local proxy, bind_host might be 127.0.0.1 and bind_port
        might be a high-numbered port, whereas url_host would be the user-facing domain name (and
        implicit port 80/443, served by the proxy).
        """
        self.on_event: Optional[base.EventCallback] = None
        templates = path.join(sys.path[0], 'templates')
        self.flask = flask.Flask(__name__, template_folder=templates)
        self.flask.config['SERVER_NAME'] = url_host
        self.flask_server = serving.make_server(bind_host, bind_port, self.flask)

    def init_routes(self, connections: Sequence[base.Connection],
                    handlers: Sequence[base.Handler[Any]]) -> None:
        for connection in connections:
            for url, view_func, options in connection.url_rules:
                endpoint = f'{type(connection).__name__}.{view_func.__name__}'
                # The class's url_rules stores the unbound method (because the @url decorator kicks
                # in before the instance is created) so bind it to the instance now.
                view_func = functools.partial(view_func, connection)
                self.flask.add_url_rule(url, endpoint, view_func, **options)

        # For Handlers, arrange to call the view function on the Handler thread (in order to make it
        # easy to share data with other Handler methods). In order to do that, wrap the supplied
        # view in a view class that bundles it into a LambdaEvent, then blocks waiting for the
        # result.
        for handler in handlers:
            for url, view_func, options in handler.url_rules:
                endpoint = f'{type(handler).__name__}.{view_func.__name__}'
                view_func = functools.partial(view_func, handler)
                view_func = _DelegatingView.as_view(endpoint, self, view_func)
                self.flask.add_url_rule(url, view_func=view_func, **options)

    def run(self, on_event: base.EventCallback) -> None:
        self.on_event = on_event
        self.flask.app_context().push()
        self.flask_server.serve_forever()

    def shutdown(self) -> None:
        self.flask_server.shutdown()


# ViewResponse is the union of allowed return types from a view function, according to Flask docs.
# (Returning a WSGI application is also allowed, omitted here.)
SimpleViewResponse = Union[flask.Response, str, bytes]
ViewResponse = Union[SimpleViewResponse,
                     Tuple[SimpleViewResponse, int, Dict[str, str]],
                     Tuple[SimpleViewResponse, int],
                     Tuple[SimpleViewResponse, Dict[str, str]]]
ViewFunc = Callable[..., ViewResponse]
UrlRule = Tuple[str, ViewFunc, Dict[str, Any]]


class _DelegatingView(views.View):
    """
    A Flask View that wraps another View and runs it on the bot's event thread.

    When a _DelegatingView receives a request, it places a LambdaEvent on the main event queue. Over
    on the event thread, the event dispatcher will call that event's lambda, which passes the
    request to the subview. (Meanwhile, the _DelegatingView's thread is blocked.)

    When the subview finishes and returns a response, the lambda hands that response back to the
    WebServerConnection thread via a single-use queue. This unblocks the _DelegatingView, and it
    returns the same response.
    """

    def __init__(self, connection: WebServerConnection, subview: ViewFunc) -> None:
        self.connection = connection
        self.subview = subview

    def dispatch_request(self, *args: Any, **kwargs: Any) -> ViewResponse:
        q: queue.Queue[Union[ViewResponse, Exception]] = queue.Queue(maxsize=1)

        @flask.copy_current_request_context
        def run():
            try:
                q.put(self.subview(*args, **kwargs))
            except Exception as e:
                # If the subview raised an exception, we want to reraise it from dispatch_request,
                # so pass it over there via the queue.
                q.put(e)

        event = lambda_event.LambdaEvent(run)
        # We can cast away the Optional from on_event because it's set in the connection's run(),
        # before the Flask server is started.
        cast(base.EventCallback, self.connection.on_event)(event)
        result = q.get()
        if isinstance(result, Exception):
            raise RuntimeError from result
        return result


def url(url: str, **options):
    """
    Decorator that turns a Connection or Handler method into a web view.

    The args are as Flask's app.route decorator.
    """
    return functools.partial(_UrlDecorator, url, options)


class _UrlDecorator:
    def __init__(self, url: str, options: Dict[str, Any], func: ViewFunc):
        self.url = url
        self.options = options
        self.func = func

    def __set_name__(self, owner: Type[base.Module], name: str):
        # We want to modify owner's url_rules, not the one inherited from Connection or Handler.
        if 'url_rules' not in owner.__dict__:
            owner.url_rules = []
        owner.url_rules.append((self.url, self.func, self.options))
        setattr(owner, name, self.func)
