import logging
import os
import queue
import sys
import threading
from logging import handlers
from typing import Optional, Dict, Sequence, List, Any

import attr

from impbot.core import base
from impbot.core import data
from impbot.core import web
from impbot.handlers import lambda_event

logger = logging.getLogger(__name__)


def init_logging(path: str) -> None:
    # Configure the root logger, not the "impbot" logger, so as to also divert
    # library output to the same place.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        fmt="{asctime} {name} {filename}:{lineno} {levelname}: {message}",
        style="{")
    formatter.default_msec_format = "%s.%03d"

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    os.makedirs(path, exist_ok=True)
    path = os.path.join(path, "impbot.log")
    file_handler = handlers.TimedRotatingFileHandler(path, "midnight")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


@attr.s
class Shutdown(base.Event):
    reply_connection: None = attr.ib(default=None, init=False)


class Bot:
    def __init__(self, db: Optional[str],
                 connections: Sequence[base.Connection],
                 handlers: Sequence[base.Handler[Any]]) -> None:
        self.connections = connections

        # Check for duplicate commands.
        commands: Dict[str, base.Handler[Any]] = {}
        for handler in handlers:
            for command in getattr(handler, "commands", []):
                if command in commands:
                    raise ValueError(f"Both {type(commands[command])} and "
                                     f"{type(handler)} register '{command}'.")
                commands[command] = handler

        if db is not None:
            data.startup(db)
            bot_data = data.Namespace("impbot.core.bot.Bot")
            db_version = int(bot_data.get("schema_version"))
            if db_version != data.SCHEMA_VERSION:
                logger.critical(
                    f"Impbot is at schema version {data.SCHEMA_VERSION}, "
                    f"database is at {db_version}")
                sys.exit(1)

        self.handlers: List[base.Handler[Any]] = [lambda_event.LambdaHandler()]
        self.handlers.extend(handlers)
        self._queue: queue.Queue[base.Event] = queue.Queue()

        ws = [c for c in connections if isinstance(c, web.WebServerConnection)]
        if ws:
            self.web: Optional[web.WebServerConnection] = ws[0]
            self.web.init_routes(self.connections, self.handlers)
        else:
            self.web = None

        # Initialize the handler thread here, but we'll start it in main().
        self._handler_thread = threading.Thread(
            name="Event handler", target=self.handle_queue)

    def process(self, event: base.Event) -> None:
        self._queue.put(event)

    def handle_queue(self) -> None:
        if self.web:
            self.web.flask.app_context().push()
        for handler in self.handlers:
            handler.startup()
        while True:
            event = self._queue.get()
            if isinstance(event, Shutdown):
                self._queue.task_done()
                break
            self.handle(event)
            self._queue.task_done()

        data.shutdown()

    def handle(self, event: base.Event) -> None:
        for handler in self.handlers:
            if not handler.typecheck(event):
                continue
            if not handler.check(event):
                continue
            try:
                response = handler.run(event)
                if response:
                    self.reply(event, response)
            except base.UserError as e:
                self.reply(event, str(e))
            except (base.AdminError, base.ServerError) as e:
                # TODO: Add some kind of direct alerting to the admins, maybe
                #  via DMs.
                logging.exception(e)
                self.reply(event, "Uh oh!")
            return

    def reply(self, event: base.Event, response: str):
        if event.reply_connection is None:
            raise ValueError(
                f"{type(event).__name__} event can't take a chat response")
        event.reply_connection.say(response)

    def run_connection(self, connection: base.Connection):
        if self.web:
            self.web.flask.app_context().push()
        connection.run(self.process)

    def main(self) -> None:
        logger.info("Starting...")
        self._handler_thread.start()
        conn_threads = []
        for connection in self.connections:
            t = threading.Thread(name=type(connection).__name__,
                                 target=self.run_connection, args=[connection])
            t.start()
            conn_threads.append(t)

        try:
            logger.info("Ready.")
            self._handler_thread.join()
        except KeyboardInterrupt:
            logger.info("Exiting...")
            self._queue.put(Shutdown())
            self._handler_thread.join()

        for connection in self.connections:
            connection.shutdown()
        graceful_exit = True
        for thread in conn_threads:
            thread.join(timeout=10.0)
            if thread.is_alive():
                graceful_exit = False
        if not graceful_exit:
            sys.exit(1)
