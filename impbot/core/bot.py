import faulthandler
import logging
import os
import queue
import sys
import threading
import time
from logging import handlers
from typing import Any, Dict, List, Optional, Sequence, TypeVar, Union

import attr

from impbot.core import base
from impbot.core import data
from impbot.core import web
from impbot.handlers import lambda_event

logger = logging.getLogger(__name__)


def init_logging(path: str) -> None:
    # Configure the root logger, not the "impbot" logger, so as to also divert library output to the
    # same place.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        fmt='{asctime} {name} {filename}:{lineno} {levelname}: {message}', style='{')
    formatter.default_msec_format = '%s.%03d'

    stdout_handler = logging.StreamHandler(sys.stdout)
    # Skip the timestamps on stdout, since we normally run as a systemd unit and journalctl adds
    # timestamps of its own.
    stdout_handler.setFormatter(
        logging.Formatter(fmt='{name} {filename}:{lineno} {levelname}: {message}', style='{'))
    stdout_handler.setLevel(logging.INFO)
    root_logger.addHandler(stdout_handler)

    os.makedirs(path, exist_ok=True)
    info_path = os.path.join(path, 'impbot.log')
    file_handler = handlers.TimedRotatingFileHandler(info_path, 'midnight')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    debug_path = os.path.join(path, 'impbot-debug.log')
    debug_handler = handlers.TimedRotatingFileHandler(debug_path, 'midnight')
    debug_handler.setFormatter(formatter)
    root_logger.addHandler(debug_handler)


@attr.s
class Shutdown(base.Event):
    reply_connection: None = attr.ib(default=None, init=False)


class Bot:
    def __init__(
            self, db: Optional[str], modules: List[Union[base.Module, base.ModuleGroup]]) -> None:
        modules = _flatten(modules)

        connections = []
        observers = []
        handlers = []
        for m in modules:
            if isinstance(m, base.Connection):
                connections.append(m)
            if isinstance(m, base.Observer):
                observers.append(m)
            if isinstance(m, base.Handler):
                handlers.append(m)
            if not isinstance(m, (base.Connection, base.Observer, base.Handler)):
                raise TypeError(f'{type(m).__name__} is not a Connection, Observer, or Handler.')

        self.connections = connections
        self.observers = observers

        # Check for duplicate commands.
        commands: Dict[str, base.Handler[Any]] = {}
        for handler in handlers:
            for command in getattr(handler, 'commands', []):
                if command in commands:
                    raise ValueError(
                        f"Both {type(commands[command])} and {type(handler)} register '{command}'.")
                commands[command] = handler

        if db is not None:
            data.startup(db)
            bot_data = data.Namespace('impbot.core.bot.Bot')
            db_version = int(bot_data.get('schema_version'))
            if db_version != data.SCHEMA_VERSION:
                logger.critical(f'Impbot is at schema version {data.SCHEMA_VERSION}, database is '
                                f'at {db_version}')
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
        self._handler_thread = threading.Thread(name='Event handler', target=self.handle_queue)

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
        for observer in self.observers:
            if observer.typecheck(event):
                observer.observe(event)
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
                # TODO: Add some kind of direct alerting to the admins, maybe via DMs.
                logger.exception(e)
                self.reply(event, 'Uh oh!')
            return

    def reply(self, event: base.Event, response: str):
        if event.reply_connection is None:
            raise ValueError(f"{type(event).__name__} event can't take a chat response")
        event.reply_connection.say(response)

    def run_connection(self, connection: base.Connection):
        if self.web:
            self.web.flask.app_context().push()
        connection.run(self.process)

    def main(self) -> None:
        logger.info('Starting...')
        self._handler_thread.start()
        conn_threads = []
        for connection in self.connections:
            t = threading.Thread(name=type(connection).__name__, target=self.run_connection,
                                 args=[connection])
            t.start()
            conn_threads.append(t)

        try:
            logger.info('Ready.')
            self._handler_thread.join()
        except KeyboardInterrupt:
            logger.info('Exiting...')
            threading.Thread(
                name='log_running_threads', target=log_running_threads, daemon=True).start()
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


T = TypeVar('T')


def _flatten(input: Sequence[Union[T, Sequence[T]]]) -> List[T]:
    output = []
    for i in input:
        if isinstance(i, list):
            output.extend(_flatten(i))
        else:
            output.append(i)
    return output


def log_running_threads() -> None:
    # If we can't exit, list the threads that are holding us open. *This* thread runs as a daemon,
    # so it won't block the exit itself.
    last = ''
    while True:
        time.sleep(10)
        threads = ','.join(thread.name for thread in threading.enumerate() if not thread.daemon)
        if threads != last:
            logger.error('Still running nondaemon threads: %s', threads)
            with open('impbot-traceback.log', 'a') as f:
                faulthandler.dump_traceback(file=f)
            logger.error('Tracebacks dumped to impbot-traceback.log')
            last = threads
