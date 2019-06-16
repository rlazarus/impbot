import logging
import queue
import sys
import threading
from typing import Optional, Dict, Sequence

import base
import data
import lambda_event
import web

logger = logging.getLogger(__name__)


class Shutdown(base.Event):
    pass


class Bot:
    def __init__(self, db: Optional[str],
                 connections: Sequence[base.Connection],
                 handlers: Sequence[base.Handler]) -> None:
        self.connections = connections

        # Check for duplicate commands.
        commands: Dict[str, base.Handler] = {}
        for handler in handlers:
            for command in getattr(handler, "commands", []):
                if command in commands:
                    raise ValueError(f"Both {type(commands[command])} and "
                                     f"{type(handler)} register '{command}'.")
                commands[command] = handler

        if db is not None:
            data.startup(db)

        self.handlers = [lambda_event.LambdaHandler()]
        self.handlers.extend(handlers)
        self._queue = queue.Queue()

        ws = [c for c in connections if isinstance(c, web.WebServerConnection)]
        if ws:
            self.web = ws[0]
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
            if not handler.check(event):
                continue
            try:
                response = handler.run(event)
                if response:
                    event.reply(response)
            except base.UserError as e:
                event.reply(str(e))
            except (base.AdminError, base.ServerError) as e:
                # TODO: Add some kind of direct alerting to the admins, maybe
                #  via DMs.
                logging.exception(e)
                event.reply("Uh oh!")
            return

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
