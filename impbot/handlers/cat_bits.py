import logging
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from obswebsocket import requests

from impbot.connections import obs
from impbot.connections.twitch_event import Bits
from impbot.core import base

logger = logging.getLogger(__name__)

CAT_SCENE = '666 Cat Cam'
MESSAGE_RE = re.compile(r'\b(cat|summon|content|kitten|kitty|floof|fluff)')
CAT_CAMS = {'cat tree cam', 'close tree cam', 'filing cabinet cam', 'under desk cam'}


class CatBitsHandler(base.Handler[Bits]):
    def __init__(self, obs_conn: obs.ObsConnection) -> None:
        super().__init__()
        self.obsws = obs_conn.obsws
        self.end_thread: Optional[threading.Thread] = None
        self.end_time: Optional[datetime] = None
        self.return_scene: Optional[str] = None

    def check(self, event: Bits) -> bool:
        if not MESSAGE_RE.search(event.chat_message.lower()):
            logger.info(f"Chat message {event.chat_message!r} doesn't match, skipping.")
            return False
        if event.bits_used < 100:
            logger.info(f'{event.bits_used} bits < 100, skipping.')
            return False
        return True

    def run(self, event: Bits) -> None:
        duration = timedelta(seconds=(event.bits_used / 10))
        if self.end_thread:
            self.end_time += duration
            logger.info(f'Already have a thread, extending to {self.end_time}')
            return
        scene = self.obsws.call(requests.GetCurrentScene())
        logger.debug(scene)
        if scene.getName() == CAT_SCENE:
            # We're in the cat scene already, but not because of this handler -- streamer probably
            # pressed the button, so we don't want to cancel it.
            logger.info('Already in cat scene, stopping.')
            return
        if not any(s['name'].lower() in CAT_CAMS and s['render'] for s in scene.getSources()):
            logger.info('No cat cams visible, stopping.')
            return

        response = self.obsws.call(requests.SetCurrentScene(CAT_SCENE))
        logger.debug(response)

        self.return_scene = scene.getName()
        self.end_time = datetime.utcnow() + duration
        self.end_thread = threading.Thread(
            target=self.do_end_thread, name='CatBitsHandler end_thread')
        self.end_thread.start()

    def do_end_thread(self) -> None:
        # Loop around the sleep, in case the end time is extended while we're sleeping.
        while datetime.utcnow() < self.end_time:
            time.sleep((self.end_time - datetime.utcnow()).total_seconds())
        scene = self.obsws.call(requests.GetCurrentScene())
        logger.info(scene)
        if scene.getName() != CAT_SCENE:
            logger.info('end: Already out of cat scene, stopping.')
            return
        response = self.obsws.call(requests.SetCurrentScene(self.return_scene))
        logger.debug(response)
        self.end_thread = None
        self.end_time = None
        self.return_scene = None
