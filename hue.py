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

ADMINS = {"twoheadedgiant", "shrdluuu"}

cache_cd = cooldown.Cooldown(duration=timedelta(minutes=5))


class HueHandler(command.CommandHandler):

    def __init__(self, hue_username: str):
        super().__init__()
        if not (data.exists("access_token") and data.exists("refresh_token")):
            # TODO: Add a first-time setup flow. For now, they're set manually.
            raise bot.AdminError("access_token and refresh_token not in DB")
        self.username = hue_username
        self.enabled = True

    def run_lightson(self, message: bot.Message) -> Optional[str]:
        if message.username.lower() not in ADMINS:
            return
        self.enabled = True
        return "twoheaDogchamp"

    def run_lightsoff(self, message: bot.Message) -> Optional[str]:
        if message.username.lower() not in ADMINS:
            return
        self.enabled = False
        return "THGSleepy"

    def run_lights(self, message: bot.Message, scene: Optional[str]) -> \
        Optional[str]:
        if not self.enabled:
            return
        if not scene:
            return self._list_scenes()

        scene = _canonicalize(scene)
        if scene == "rainbow":
            return self._colorloop()
        if scene == "off" and message.username.lower() == "jaccabre":
            return "hi Jacca twoheaDogchamp"

        roulette = (scene == "random")
        if roulette:
            scene = random.choice([k for k, v in data.list(" id")])[:-3]

        if not data.exists(f"{scene} id"):
            self._maybe_fill_cache(force=True)
        if not data.exists(f"{scene} id"):
            return self._list_scenes()
        scene_id = data.get(f"{scene} id")
        response = self._action(scene=scene_id)
        if response is not None:
            # It's an error message.
            return response
        if roulette:
            name = data.get(f"{scene} name")
            return f"How about... {name}! twoheaDogchamp"
        # Otherwise, no need to say anything.

    def run_blink(self) -> Optional[str]:
        if not self.enabled:
            return
        return self._action(alert="select")

    def _list_scenes(self) -> str:
        try:
            self._maybe_fill_cache()
        except HueError:
            return "oh heck"
        rows = [v for k, v in data.list(" name")]
        rows.append("Rainbow")
        rows.sort()
        return "Scenes: " + ', '.join(rows)

    def _maybe_fill_cache(self, force: bool = False) -> None:
        if not (cache_cd.fire() or force or not data.list(" id")):
            return

        access_token = data.get("access_token")
        response = requests.get(
            f"https://api.meethue.com/bridge/{self.username}/scenes",
            headers={"Authorization": f"Bearer {access_token}"})

        _log(response)
        if response.status_code != 200:
            raise HueError

        scenes = json.loads(response.text)
        data.clear_all("% name")
        data.clear_all("% id")
        for id, fields in scenes.items():
            full_name = fields["name"]
            if not full_name.lower().startswith("bot "):
                continue
            full_name = full_name[4:]
            canon_name = _canonicalize(full_name)
            data.set(f"{canon_name} name", full_name)
            data.set(f"{canon_name} id", id)

    def _colorloop(self) -> Optional[str]:
        return self._action(effect="colorloop", bri=150)

    def _action(self, **data):
        access_token = data.get("access_token")
        response = requests.put(
            f"https://api.meethue.com/bridge/{self.username}/groups/1/action",
            data=json.dumps(data),
            headers={"Authorization": f"Bearer {access_token}",
                     "Content-Type": "application/json"})
        _log(response)
        if response.status_code != 200:
            return "ah jeez"

    def _oauth_refresh(self) -> None:
        path = "/oauth2/refresh"
        response = requests.post(f"https://api.meethue.com{path}")
        _log(response, normal_status=401)
        auth = response.headers["WWW-Authenticate"]
        realm = re.search('realm="(.*?)"', auth).group(1)
        nonce = re.search('nonce="(.*?)"', auth).group(1)

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
            data={"refresh_token": data.get("refresh_token")})
        _log(response)
        tokens = json.loads(response.text)
        data.set("access_token", tokens["access_token"])
        data.set("refresh_token", tokens["refresh_token"])


def _canonicalize(name: str) -> str:
    return "".join(i for i in name.lower() if i in string.ascii_lowercase)


def _log(response: requests.Response, normal_status: int = 200) -> None:
    if response.status_code == normal_status:
        level = logging.DEBUG
    else:
        level = logging.ERROR
    logging.log(level, response)
    logging.log(level, response.headers)
    logging.log(level, response.text)


def _md5(s: str) -> str:
    m = hashlib.md5()
    m.update(bytes(s, 'utf-8'))
    return m.hexdigest()


class HueError(Exception):
    pass
