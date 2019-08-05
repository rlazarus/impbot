import datetime
import hashlib
import json
import logging
import random
import re
import string
from datetime import timedelta
from typing import Optional

import requests

import secret
from impbot.connections import twitch
from impbot.connections import twitch_event
from impbot.connections import twitch_webhook
from impbot.core import base
from impbot.core import data
from impbot.handlers import command
from impbot.util import cooldown

logger = logging.getLogger(__name__)

cache_cd = cooldown.Cooldown(duration=timedelta(minutes=5))


class HueClient:
    def __init__(self, username: str):
        self.data = data.Namespace("HueClient")
        self.username = username

    @property
    def enabled(self) -> bool:
        """
        This property is a shortcut to shared storage only -- it doesn't enable
        or disable any of the other methods.
        """
        return self.data.get("enabled") == "True"

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.data.set("enabled", str(value))

    def list_scenes(self) -> str:
        self._maybe_fill_cache()
        rows = [v for k, v in self.data.list(" name")]
        rows.append("Rainbow")
        rows.sort()
        return "Scenes: " + ', '.join(rows)

    def random_scene(self) -> str:
        return random.choice([k for k, v in self.data.list(" id")])[:-3]

    def set_scene(self, scene: str) -> Optional[str]:
        if not self.data.exists(f"{scene} id"):
            self._maybe_fill_cache(force=True)
        if not self.data.exists(f"{scene} id"):
            return self.list_scenes()
        scene_id = self.data.get(f"{scene} id")
        self._action(scene=scene_id)
        return None

    def colorloop(self) -> None:
        self._action(effect="colorloop", bri=150)

    def blink(self) -> None:
        self._action(alert="select")

    def _action(self, **body) -> None:
        response = requests.put(
            f"https://api.meethue.com/bridge/{self.username}/groups/1/action",
            data=json.dumps(body),
            headers={"Authorization": f"Bearer {self._access_token()}",
                     "Content-Type": "application/json"})
        _log(response)
        if response.status_code != 200:
            raise HueError

    def _maybe_fill_cache(self, force: bool = False) -> None:
        if not (cache_cd.fire() or force or not self.data.list(" id")):
            return

        response = requests.get(
            f"https://api.meethue.com/bridge/{self.username}/scenes",
            headers={"Authorization": f"Bearer {self._access_token()}"})

        _log(response)
        if response.status_code != 200:
            raise HueError

        scenes = json.loads(response.text)
        self.data.clear_all("% name")
        self.data.clear_all("% id")
        for id, fields in scenes.items():
            full_name = fields["name"]
            if not full_name.lower().startswith("bot "):
                continue
            full_name = full_name[4:]
            canon_name = _canonicalize(full_name)
            self.data.set(f"{canon_name} name", full_name)
            self.data.set(f"{canon_name} id", id)

    def _access_token(self) -> str:
        # TODO: Move this back into __init__ once data is available there.
        if not (self.data.exists("access_token") and
                self.data.exists("refresh_token")):
            # TODO: Add a first-time setup flow. For now, they're set manually.
            raise base.AdminError("access_token and refresh_token not in DB")

        # First, refresh if necessary.
        expiration_timestamp = float(self.data.get("access_token_expires", "0"))
        expiration = datetime.datetime.fromtimestamp(
            expiration_timestamp, datetime.timezone.utc)
        if expiration <= datetime.datetime.now(datetime.timezone.utc):
            self._oauth_refresh()

        return self.data.get("access_token")

    def _oauth_refresh(self) -> None:
        path = "/oauth2/refresh"
        response = requests.post(f"https://api.meethue.com{path}")
        _log(response, normal_status=401)
        auth = response.headers["WWW-Authenticate"]
        realm_match = re.search('realm="(.*?)"', auth)
        nonce_match = re.search('nonce="(.*?)"', auth)
        if not realm_match or not nonce_match:
            logger.error(f"Bad OAuth refresh response: {response}")
            raise HueError
        realm = realm_match.group(1)
        nonce = nonce_match.group(1)

        h1 = _md5(f"{secret.HUE_CLIENT_ID}:{realm}:{secret.HUE_CLIENT_SECRET}")
        h2 = _md5(f"POST:{path}")
        digest_response = _md5(f"{h1}:{nonce}:{h2}")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization":
                f'Digest username="{secret.HUE_CLIENT_ID}", realm="{realm}", '
                f'nonce="{nonce}", uri="{path}", response="{digest_response}"'
        }
        response = requests.post(
            f"https://api.meethue.com{path}",
            headers=headers,
            params={"grant_type": "refresh_token"},
            data={"refresh_token": self.data.get("refresh_token")})
        _log(response)
        tokens = json.loads(response.text)
        self.data.set("access_token", tokens["access_token"])
        self.data.set("refresh_token", tokens["refresh_token"])
        ttl = datetime.timedelta(
            seconds=float(tokens["access_token_expires_in"]))
        expiration = datetime.datetime.now(datetime.timezone.utc) + ttl
        self.data.set("access_token_expires", str(expiration.timestamp()))


class HueHandler(command.CommandHandler):
    def __init__(self, hue_client: HueClient) -> None:
        super().__init__()
        self.hue_client = hue_client

    def run_lightson(self, message: base.Message) -> Optional[str]:
        if not message.user.admin:
            return None
        self.hue_client.enabled = True
        return "PogChamp"

    def run_lightsoff(self, message: base.Message) -> Optional[str]:
        if not message.user.admin:
            return None
        self.hue_client.enabled = False
        return "\U0001f44b"  # Waving Hand emoji

    def run_lights(self, scene: Optional[str]) -> Optional[str]:
        if not self.hue_client.enabled:
            return None
        if not scene:
            return self.hue_client.list_scenes()

        scene = _canonicalize(scene)
        if scene == "rainbow":
            self.hue_client.colorloop()
            return None

        roulette = (scene == "random")
        if roulette:
            scene = self.hue_client.random_scene()

        response = self.hue_client.set_scene(scene)
        if response is not None:
            # It's an error message.
            return response
        if roulette:
            name = self.data.get(f"{scene} name")
            return f"How about... {name}! PogChamp"
        # Otherwise, no need to say anything.
        return None

    def run_blink(self) -> None:
        if not self.hue_client.enabled:
            return
        self.hue_client.blink()


class TwitchEventBlinkHandler(base.Handler):
    def __init__(self, hue_client: HueClient) -> None:
        super().__init__()
        self.hue_client = hue_client

    def check(self, event: base.Event) -> bool:
        return isinstance(event, twitch_event.TwitchEvent)

    def run(self, event: base.Event) -> None:
        if self.hue_client.enabled:
            self.hue_client.blink()


class TwitchEnableDisableHandler(base.Handler):
    def __init__(self, hue_client: HueClient,
                 chat_conn: twitch.TwitchChatConnection) -> None:
        super().__init__()
        self.hue_client = hue_client
        self.chat_conn = chat_conn

    def check(self, event: base.Event) -> bool:
        return isinstance(event, twitch_webhook.TwitchWebhookEvent)

    def run(self, event: base.Event) -> None:
        # TODO: Refactor so the replies here can be returned instead of having
        #   a reference to a TwitchChatConnection.
        if isinstance(event, twitch_webhook.StreamStartedEvent):
            self.hue_client.enabled = True
            self.chat_conn.say("PogChamp PogChamp")

        if isinstance(event, twitch_webhook.StreamEndedEvent):
            self.hue_client.enabled = False
            self.chat_conn.say("\U0001f44b \U0001f44b")  # Waving Hand emoji


def _canonicalize(name: str) -> str:
    return "".join(i for i in name.lower() if i in string.ascii_lowercase)


def _log(response: requests.Response, normal_status: int = 200) -> None:
    if response.status_code == normal_status:
        level = logging.DEBUG
    else:
        level = logging.ERROR
    logger.log(level, response)
    logger.log(level, response.headers)
    logger.log(level, response.text)


def _md5(s: str) -> str:
    m = hashlib.md5()
    m.update(bytes(s, 'utf-8'))
    return m.hexdigest()


class HueError(base.ServerError):
    pass