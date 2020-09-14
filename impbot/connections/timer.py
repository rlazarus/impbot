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
        self.run = run
        self.repeat = repeat
        self.timer_conn = timer_conn
        self.interval = interval  # Used to extend, when repeat == True.
        self.end_time = datetime.datetime.now() + interval
        self.timer: Optional[threading.Timer] = None
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.start_timer()

    def start_timer(self) -> None:
        interval = (self.end_time - datetime.datetime.now()).total_seconds()
        self.timer = threading.Timer(interval, self.run_as_lambda)
        self.timer.start()

    def run_as_lambda(self) -> None:
        def run() -> None:
            # This runs on the event thread. Double-check the cancel flag, in
            # case we got canceled while this was queued.
            if self.cancelled.is_set():
                return
            if self.end_time > datetime.datetime.now():
                # The time has been extended, so wait again.
                self.start_timer()
                return
            self.timer_conn.remove(self)
            try:
                self.run()
            finally:
                self.finished.set()

        # This runs on the timer thread, so it isn't delayed by running the
        # actual lambda. Enqueue the lambda, then immediately repeat if
        # appropriate.
        self.timer_conn.on_event(lambda_event.LambdaEvent(run))
        if self.repeat and not self.cancelled.is_set():
            self.extend(self.interval)
            self.start_timer()

    def cancel(self) -> None:
        self.timer.cancel()
        self.timer_conn.remove(self)
        self.cancelled.set()

    def extend(self, extend_interval: datetime.timedelta) -> None:
        self.end_time += extend_interval

    def active(self) -> bool:
        return not self.cancelled.is_set() and not self.finished.is_set()
