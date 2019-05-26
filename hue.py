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

import bot
import command
import cooldown
import data
import secret
import twitch
import twitch_event
import twitch_webhook

logger = logging.getLogger(__name__)

cache_cd = cooldown.Cooldown(duration=timedelta(minutes=5))


class HueHandler(command.CommandHandler):
    def __init__(self, hue_username: str) -> None:
        super().__init__()
        self.hue_client = HueClient(hue_username)
        # TODO: Move "enabled" into the DB, so it persists across restarts.
        self.enabled = True

    def run_lightson(self, message: bot.Message) -> Optional[str]:
        if not message.user.admin:
            return
        self.enabled = True
        return "twoheaDogchamp"

    def run_lightsoff(self, message: bot.Message) -> Optional[str]:
        if not message.user.admin:
            return
        self.enabled = False
        return "THGSleepy"

    def run_lights(self, message: bot.Message, scene: Optional[str]) -> \
            Optional[str]:
        if not self.enabled:
            return
        if not scene:
            return self.hue_client.list_scenes()

        scene = _canonicalize(scene)
        if scene == "rainbow":
            return self.hue_client.colorloop()
        if scene == "off" and message.user == twitch.TwitchUser("jaccabre"):
            return "hi Jacca twoheaDogchamp"

        roulette = (scene == "random")
        if roulette:
            scene = self.hue_client.random_scene()

        response = self.hue_client.set_scene(scene)
        if response is not None:
            # It's an error message.
            return response
        if roulette:
            name = self.data.get(f"{scene} name")
            return f"How about... {name}! twoheaDogchamp"
        # Otherwise, no need to say anything.

    def run_blink(self) -> Optional[str]:
        if not self.enabled:
            return
        return self.hue_client.blink()


class TwitchEventBlinkHandler(bot.Handler):
    def __init__(self, hue_handler: HueHandler) -> None:
        # TODO: Break the dependency on HueHandler -- right now HueHandler
        #   instantiates the HueClient, but both handlers should depend directly
        #   on HueClient instead.
        super().__init__()
        self.hue_handler = hue_handler

    def check(self, event: bot.Event) -> bool:
        return (isinstance(event, twitch_event.TwitchEvent) and
                self.hue_handler.enabled)

    def run(self, event: bot.Event) -> None:
        self.hue_handler.hue_client.blink()


class TwitchEnableDisableHandler(bot.Handler):
    def __init__(self, hue_handler: HueHandler,
                 chat_conn: twitch.TwitchChatConnection) -> None:
        super().__init__()
        self.hue_handler = hue_handler
        self.chat_conn = chat_conn

    def check(self, event: bot.Event) -> bool:
        return isinstance(event, twitch_webhook.TwitchWebhookEvent)

    def run(self, event: bot.Event) -> None:
        # TODO: Refactor so the replies here can be returned instead of having
        #   a reference to a TwitchChatConnection, then dedupe with HueHandler's
        #   enable and disable.
        if isinstance(event, twitch_webhook.StreamStartedEvent):
            self.hue_handler.enabled = True
            self.chat_conn.say("twoheaDogchamp twoheaDogchamp")

        if isinstance(event, twitch_webhook.StreamEndedEvent):
            self.hue_handler.enabled = False
            self.chat_conn.say("THGSleepy THGSleepy")


class HueClient:
    def __init__(self, username: str):
        # TODO: The data is still in a HueHandler namespace from when this code
        #   was part of that class. Migrate it in the DB to a new namespace
        #   HueClient.
        self.data = data.Namespace("HueHandler")
        self.username = username

    def list_scenes(self) -> str:
        try:
            self._maybe_fill_cache()
        except HueError:
            return "oh heck"
        rows = [v for k, v in self.data.list(" name")]
        rows.append("Rainbow")
        rows.sort()
        return "Scenes: " + ', '.join(rows)

    def random_scene(self) -> str:
        return random.choice([k for k, v in self.data.list(" id")])[:-3]

    def set_scene(self, scene: str) -> Optional[str]:
        if not self.data.exists(f"{scene} id"):
            try:
                self._maybe_fill_cache(force=True)
            except HueError:
                return "oof yikes"
        if not self.data.exists(f"{scene} id"):
            return self.list_scenes()
        scene_id = self.data.get(f"{scene} id")
        return self._action(scene=scene_id)

    def colorloop(self) -> Optional[str]:
        return self._action(effect="colorloop", bri=150)

    def blink(self) -> Optional[str]:
        return self._action(alert="select")

    def _action(self, **body):
        response = requests.put(
            f"https://api.meethue.com/bridge/{self.username}/groups/1/action",
            data=json.dumps(body),
            headers={"Authorization": f"Bearer {self._access_token()}",
                     "Content-Type": "application/json"})
        _log(response)
        if response.status_code != 200:
            return "ah jeez"

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
            raise bot.AdminError("access_token and refresh_token not in DB")

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


class HueError(Exception):
    pass
