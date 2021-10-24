import datetime
import queue
import threading
import unittest
from typing import Optional, Union, cast
from unittest import mock

import freezegun

from impbot.connections import timer
from impbot.core import bot
from impbot.handlers import lambda_event


class MockThreadingTimer(threading.Timer):
    def __init__(self, queue, time, interval, *args, **kwargs):
        super().__init__(interval, *args, **kwargs)
        self.queue = queue
        self.time = time
        self.end_time = time() + datetime.timedelta(interval)

    def run(self):
        # RepeatingTimer schedules new lambdas on time, without waiting for the run function to
        # complete. When we mock out the actual delay for unit testing, that's basically running in
        # a tight loop, so lambdas stack up faster than they get executed. (Where that actually
        # turns into a problem is, the end_time overflows the maximum date, which is very funny.) We
        # join the queue here to block until the last timer execution has completed before we start
        # the next one.
        self.queue.join()
        if self.end_time > self.time():
            self.time.move_to(self.end_time)
        if not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
        self.finished.set()


class TestTimer(unittest.TestCase):
    def setUp(self):
        start_time = datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self._freeze_time = freezegun.freeze_time(start_time)
        self.time = self._freeze_time.start()
        self.queue: queue.Queue[Union[lambda_event.LambdaEvent, bot.Shutdown]] = queue.Queue()
        self.timer: Optional[timer.Timer] = None
        self.counter = 0

        self.event_thread = threading.Thread(target=self.run_event_thread)
        self.event_thread.start()

        self.timer_conn = timer.TimerConnection()
        self.timer_thread = threading.Thread(target=self.timer_conn.run, args=(self.queue.put,))
        self.timer_thread.start()

    def tearDown(self):
        self.queue.put(bot.Shutdown())
        self.timer_conn.shutdown()
        self.timer_thread.join()
        self.event_thread.join()

        self._freeze_time.stop()

    def new_mock_timer(self, *args, **kwargs):
        return MockThreadingTimer(self.queue, self.time, *args, **kwargs)

    def run_event_thread(self):
        while True:
            event = self.queue.get()
            if isinstance(event, bot.Shutdown):
                self.queue.task_done()
                break
            cast(lambda_event.LambdaEvent, event).run()
            self.queue.task_done()

    def test_single(self):
        run = mock.Mock()

        with mock.patch('threading.Timer', new=self.new_mock_timer):
            self.timer = self.timer_conn.start_once(datetime.timedelta(minutes=1), run)
        self.timer.finished.wait()
        run.assert_called_once()

    def test_repeating(self):
        def side_effect():
            self.counter += 1
            if self.counter == 3:
                self.timer.cancel()

        run = mock.Mock(side_effect=side_effect)

        def start_timer():
            with mock.patch('threading.Timer', new=self.new_mock_timer):
                self.timer = self.timer_conn.start_repeating(datetime.timedelta(minutes=1), run)

        self.queue.put(lambda_event.LambdaEvent(start_timer))
        self.queue.join()
        self.timer.cancelled.wait()
        run.assert_has_calls([mock.call()] * 3)
