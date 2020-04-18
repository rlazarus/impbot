import logging
from typing import cast, Optional

from impbot.core import base

default_logger = logging.getLogger(__name__)


class LoggingObserver(base.Observer[base.Event]):
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        super().__init__()
        self.logger = logger if logger else default_logger

    def observe(self, event: base.Event) -> None:
        if isinstance(event, base.Message):
            event = cast(base.Message, event)
            connection = type(event.reply_connection).__name__
            if connection.endswith("Connection"):
                connection = connection[:-len("Connection")]
            if connection.endswith("Chat"):
                connection = connection[:-len("Chat")]
            self.logger.info(f"[{connection}] <{event.user}> {event.text}")
            return
        self.logger.info(event)
