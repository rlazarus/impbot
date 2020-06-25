import datetime
import threading
from typing import Callable, List, Optional

from impbot.core import base
from impbot.core.base import EventCallback
from impbot.handlers import lambda_event


class TimerConnection(base.Connection):
    def __init__(self):
        self.on_event: Optional[EventCallback] = None
        self.timers: List[Timer] = []
        self.shutdown_event = threading.Event()

    def run(self, on_event: EventCallback) -> None:
        self.on_event = on_event
        self.shutdown_event.wait()

    def shutdown(self) -> None:
        self.shutdown_event.set()
        for timer in self.timers:
            timer.cancel()

    def start(self, interval: datetime.timedelta, run: Callable[[], None],
              repeat: bool = False) -> "Timer":
        timer = Timer(self, interval, run, repeat)
        self.timers.append(timer)
        return timer

    def remove(self, timer: "Timer") -> None:
        self.timers.remove(timer)


class Timer:
    def __init__(self, timer_conn: TimerConnection,
                 interval: datetime.timedelta, run: Callable[[], None],
                 repeat: bool = False):
        self.interval = interval
        self.run = run
        self.repeat = repeat
        self.timer_conn = timer_conn
        self.timer: Optional[threading.Timer] = None
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.start_timer()

    def start_timer(self) -> None:
        self.timer = threading.Timer(self.interval.total_seconds(),
                                     self.run_as_lambda)
        self.timer.start()

    def run_as_lambda(self) -> None:
        def run() -> None:
            self.run()
            self.finished.set()
        self.timer_conn.on_event(lambda_event.LambdaEvent(run))
        if self.repeat and not self.cancelled.is_set():
            self.start_timer()
        else:
            self.timer_conn.remove(self)

    def cancel(self) -> None:
        self.timer.cancel()
        self.timer_conn.remove(self)
        self.cancelled.set()

    def active(self) -> bool:
        return not self.cancelled.is_set() and not self.finished.is_set()