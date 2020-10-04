import datetime
import threading
from abc import ABCMeta, abstractmethod
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

    def start_once(self, interval: datetime.timedelta,
                   run: Callable[[], None]) -> "SingleTimer":
        timer = SingleTimer(self, interval, run)
        self.timers.append(timer)
        return timer

    def start_repeating(self, interval: datetime.timedelta,
                        run: Callable[[], None]) -> "RepeatingTimer":
        timer = RepeatingTimer(self, interval, run)
        self.timers.append(timer)
        return timer

    def remove(self, timer: "Timer") -> None:
        try:
            self.timers.remove(timer)
        except ValueError:
            # Very occasionally, a timer gets double-removed due to a race
            # condition. That's actually fine, so eating the ValueError here
            # makes remove() idempotent.
            pass


class Timer(metaclass=ABCMeta):

    def __init__(self, timer_conn: TimerConnection,
                 interval: datetime.timedelta, run: Callable[[], None]):
        self.run = run
        self.timer_conn = timer_conn
        self.end_time = datetime.datetime.now() + interval
        self.timer: Optional[threading.Timer] = None
        self.cancelled = threading.Event()

    def start_timer(self) -> None:
        interval = (self.end_time - datetime.datetime.now()).total_seconds()
        self.timer = threading.Timer(interval, self.run_as_lambda)
        self.timer.start()

    def cancel(self) -> None:
        self.timer.cancel()
        self.timer_conn.remove(self)
        self.cancelled.set()

    @abstractmethod
    def run_as_lambda(self):
        pass

    @abstractmethod
    def active(self):
        pass


class SingleTimer(Timer):

    def __init__(self, timer_conn: TimerConnection,
                 interval: datetime.timedelta, run: Callable[[], None]):
        super().__init__(timer_conn, interval, run)
        self.finished = threading.Event()
        self.start_timer()

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

        self.timer_conn.on_event(lambda_event.LambdaEvent(run))

    def extend(self, extend_interval: datetime.timedelta) -> None:
        self.end_time += extend_interval

    def active(self) -> bool:
        return not self.cancelled.is_set() and not self.finished.is_set()


class RepeatingTimer(Timer):
    def __init__(self, timer_conn: TimerConnection,
                 interval: datetime.timedelta, run: Callable[[], None]):
        super().__init__(timer_conn, interval, run)
        self.interval = interval
        self.start_timer()

    def run_as_lambda(self) -> None:
        def run() -> None:
            # This runs on the event thread. Double-check the cancel flag, in
            # case we got canceled while this was queued.
            if self.cancelled.is_set():
                return
            self.run()

        # This runs on the timer thread, so it isn't delayed by running the
        # actual lambda. Enqueue the lambda, then immediately repeat if
        # appropriate.
        self.timer_conn.on_event(lambda_event.LambdaEvent(run))
        if not self.cancelled.is_set():
            self.end_time += self.interval
            self.start_timer()

    def active(self) -> bool:
        return not self.cancelled.is_set()
