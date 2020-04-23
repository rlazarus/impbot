import datetime
import logging
import threading
from typing import Set, Optional, Dict, cast

from obswebsocket import events, requests

from impbot.connections import obs
from impbot.connections.obs import ObsMessage, ObsConnected
from impbot.core import base

# Give a warning after the mic is maybe-accidentally muted for this long.
INTERVAL = datetime.timedelta(minutes=1)
logger = logging.getLogger(__name__)


# TODO: Decompose this into three handlers for Connected, Disconnected, and
#  ObsMessage. At least the first two could be observers instead.
class MuteHandler(base.Handler[obs.ObsEvent]):
    def __init__(self, streamer_name: str, mic_source: str,
                 mutable_scene_items: Set[str], obs_conn: obs.ObsConnection,
                 chat_conn: base.ChatConnection):
        super().__init__()
        self.streamer_name = streamer_name
        self.mic_source = mic_source
        self.mutable_scene_items = mutable_scene_items
        self.obsws = obs_conn.obsws
        self.chat_conn = chat_conn
        self.muted: bool = False
        self.mutable_items_visible: Dict[str, bool] = {}
        self.alert_lock = threading.Lock()
        self.alert_timer: Optional[threading.Timer] = None
        # This is set True when we announce the mic is muted, and set False
        # again when the mic unmutes or stream ends (but not on any other state
        # change). It keeps us from announcing twice on a single muted mic.
        self.has_announced = False

    def check(self, event: obs.ObsEvent) -> bool:
        if (isinstance(event, obs.ObsConnected) or
                isinstance(event, obs.ObsDisconnected)):
            return True
        event = cast(obs.ObsMessage, event)
        message = event.obs_message
        if isinstance(message, events.SourceMuteStateChanged):
            return message.getSourcename() == self.mic_source
        if isinstance(message, events.SceneItemVisibilityChanged):
            return message.getItemName() in self.mutable_scene_items
        if isinstance(message, events.StreamStopping):
            return True
        return False

    def run(self, event: obs.ObsEvent) -> None:
        if isinstance(event, ObsConnected):
            scene = self.obsws.call(requests.GetCurrentScene())
            for s in scene.getSources():
                if s["name"] in self.mutable_scene_items:
                    self.mutable_items_visible[s["name"]] = s["render"]
            # Any item not in the current scene, we'll consider not visible.
            for i in self.mutable_scene_items:
                self.mutable_items_visible.setdefault(i, False)

            mute_status = self.obsws.call(requests.GetMute(self.mic_source))
            self.muted = mute_status.getMuted()

            logger.info(f"Starting: {self.muted}, {self.mutable_items_visible}")
            return

        if isinstance(event, obs.ObsDisconnected):
            self.cancel_timer()
            return

        event = cast(ObsMessage, event)
        msg = event.obs_message
        if isinstance(msg, events.SourceMuteStateChanged):
            self.muted = msg.getMuted()
            if self.accidentally_muted():
                self.start_timer()
            else:
                self.cancel_timer()
                self.has_announced = False
        elif isinstance(msg, events.SceneItemVisibilityChanged):
            self.mutable_items_visible[msg.getItemName()] = msg.getItemVisible()
            if self.accidentally_muted():
                self.start_timer()
            else:
                self.cancel_timer()
        elif isinstance(msg, events.StreamStopping):
            self.cancel_timer()

    def accidentally_muted(self) -> bool:
        return self.muted and not any(self.mutable_items_visible.values())

    def start_timer(self) -> None:
        with self.alert_lock:
            if self.alert_timer:
                logger.info("Timer already started.")
                return
            logger.info("Timer starting!")
            self.alert_timer = threading.Timer(INTERVAL.total_seconds(),
                                               self.alert_now)
            self.alert_timer.start()

    def cancel_timer(self) -> None:
        with self.alert_lock:
            if not self.alert_timer:
                logger.info("No timer.")
                return
            logger.info("Timer canceling!")
            self.alert_timer.cancel()
            self.alert_timer = None

    def alert_now(self) -> None:
        with self.alert_lock:
            if self.has_announced:
                logger.info("Already announced!")
            if self.accidentally_muted() and not self.has_announced:
                logger.info("Announcing!")
                self.chat_conn.say(
                    f"@{self.streamer_name} HEY STREAMER YOU'RE MUTED <3")
                self.has_announced = True
            self.alert_timer = None
