import datetime
import logging
import threading
import time
from typing import Optional

import attr
import obswebsocket
import websocket
from obswebsocket import requests, events, exceptions

from impbot.core import base

logger = logging.getLogger(__name__)


class ObsEvent(base.Event):
    pass


@attr.s(auto_attribs=True)
class ObsMessage(ObsEvent):
    obs_message: obswebsocket.base_classes.Baseevents


class ObsConnected(ObsEvent):
    pass


class ObsDisconnected(ObsEvent):
    pass


class ObsConnection(base.Connection):
    def __init__(self, host: str, port: int, password: str) -> None:
        super().__init__()
        self.shutdown_event = threading.Event()
        self.obsws = ReconnectingObsws(self.shutdown_event, host, port,
                                       password)
        self.ping_thread = threading.Thread(target=self.ping,
                                            name='ObsConnection-ping')

    def run(self, on_event: base.EventCallback) -> None:
        self.obsws.set_callback(on_event)
        try:
            self.obsws.connect()
        except base.ShuttingDownError:
            return
        self.obsws.call(requests.SetHeartbeat(True))
        self.ping_thread.start()
        self.shutdown_event.wait()

    def shutdown(self) -> None:
        self.shutdown_event.set()
        self.obsws.disconnect()

    def ping(self) -> None:
        # Sometimes we won't notice the connection is lost until we try to send
        # something and it fails. If we ever go more than a couple of seconds
        # without receiving anything, send a status request and ignore the
        # result.
        while not self.shutdown_event.is_set():
            time.sleep(1)
            if (self.obsws.is_connected() and
                    datetime.datetime.now() - self.obsws.last_received >
                    datetime.timedelta(seconds=2)):
                self.obsws.call(requests.GetStreamingStatus())


class ReconnectingObsws(obswebsocket.obsws):
    """
    obswebsocket is designed for ephemeral uses: it connects once, eventually
    disconnects, and then you're expected to create a new one. Instead we want
    a long-lived object that reconnects as necessary.
    """

    def __init__(self, shutdown_event: threading.Event, host='localhost',
                 port=4444, password=''):
        super().__init__(host, port, password)
        self.shutdown_event = shutdown_event
        self.on_event: Optional[base.EventCallback] = None
        self.last_received = datetime.datetime.now()

    def _on_obs_event(self, e: events.Baseevents) -> None:
        self.last_received = datetime.datetime.now()
        self.on_event(ObsMessage(None, e))

    def call(self, obj: requests.Baserequests) -> requests.Baserequests:
        while True:
            try:
                result = super().call(obj)
                self.last_received = datetime.datetime.now()
                return result
            except (ConnectionError, exceptions.MessageTimeout):
                self.reconnect()

    def set_callback(self, on_event: base.EventCallback):
        self.on_event = on_event
        self.register(self._on_obs_event)

    def connect(self, host: Optional[str] = None, port: Optional[int] = None):
        while True:
            if self.shutdown_event.is_set():
                raise base.ShuttingDownError("")
            try:
                super().connect(host, port)
                self.on_event(ObsConnected(None))
            except (obswebsocket.exceptions.ConnectionFailure,
                    websocket.WebSocketAddressException) as e:
                logger.error(f"Couldn't connect, retrying in 5 seconds: {e}")
                time.sleep(5)
            else:
                return

    def disconnect(self):
        # Disconnect, then immediately start trying to reconnect.
        super().disconnect()
        self.on_event(ObsDisconnected(None))
        if not self.shutdown_event.is_set():
            self.connect()

    def reconnect(self):
        self.connect()

    def is_connected(self) -> bool:
        return self.ws is not None and self.ws.connected
