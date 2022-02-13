import datetime
import hashlib
import logging
import random
import re
import string
from datetime import timedelta
from pprint import pprint
from typing import Optional, Set, Tuple, Union
from urllib import parse

import flask
import requests

import secret
from impbot.connections import twitch_event, twitch_eventsub
from impbot.core import base, web
from impbot.core import data
from impbot.handlers import command
from impbot.util import cooldown, twitch_util

logger = logging.getLogger(__name__)
cache_cd = cooldown.Cooldown(duration=timedelta(minutes=5))

# Keys associated with scenes don't contain underscores, so using this key guarantees there isn't a
# conflict.
CONFIG_KEY = '_config'


class HueClient:
    def __init__(self):
        self.data = data.Namespace('impbot.handlers.hue.HueClient')

    def startup(self) -> None:
        if not all(self.data.exists(CONFIG_KEY, subkey)
                   for subkey in ('access_token', 'refresh_token', 'username')):
            logger.critical(
                'Hue access_token, refresh_token, and username not in DB. Please log in with: %s',
                flask.url_for('HueOAuthWebHandler.oauth_login'))

    @property
    def enabled(self) -> bool:
        """
        This property is a shortcut to shared storage only -- it doesn't enable or disable any of
        the other methods.
        """
        return self.data.get(CONFIG_KEY, 'enabled', default='False') == 'True'

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.data.set_subkey(CONFIG_KEY, 'enabled', str(value))

    def list_scenes(self) -> str:
        self._maybe_fill_cache()
        names = [v['name'] for k, v in self.data.get_all_dicts().items() if k != CONFIG_KEY]
        names.append('Rainbow')
        names.sort()
        return 'Scenes: ' + ', '.join(names)

    def random_scene(self) -> str:
        ids = [v['id'] for k, v in self.data.get_all_dicts().items() if k != CONFIG_KEY]
        return random.choice(ids)

    def set_scene(self, scene: str) -> Optional[str]:
        if not self.data.exists(scene):
            self._maybe_fill_cache(force=True)
        if not self.data.exists(scene):
            return self.list_scenes()
        scene_id = self.data.get(scene, 'id')
        self._action(scene=scene_id)
        return None

    def colorloop(self) -> None:
        self._action(effect='colorloop', bri=150)

    def blink(self) -> None:
        self._action(alert='select')

    def _action(self, **body) -> None:
        username = self.data.get(CONFIG_KEY, 'username')
        response = requests.put(f'https://api.meethue.com/bridge/{username}/groups/1/action',
                                json=body,
                                headers={'Authorization': f'Bearer {self._access_token()}',
                                         'Content-Type': 'application/json'})
        _log(response)
        if response.status_code != 200:
            raise HueError

    def _maybe_fill_cache(self, force: bool = False) -> None:
        any_scenes = any(key != CONFIG_KEY for key in self.data.get_all_dicts())
        if not (cache_cd.fire() or force or not any_scenes):
            return

        username = self.data.get(CONFIG_KEY, 'username')
        response = requests.get(f'https://api.meethue.com/bridge/{username}/scenes',
                                headers={'Authorization': f'Bearer {self._access_token()}'})

        _log(response)
        if response.status_code != 200:
            raise HueError

        scenes = response.json()
        self.data.clear_all(except_keys=[CONFIG_KEY])
        for id, fields in scenes.items():
            full_name = fields['name']
            if not full_name.lower().startswith('bot '):
                continue
            full_name = full_name[4:]
            canon_name = _canonicalize(full_name)
            self.data.set(canon_name, {'name': full_name, 'id': id})

    def _access_token(self) -> str:
        # First, refresh if necessary.
        try:
            expiration_timestamp = float(self.data.get(CONFIG_KEY, 'access_token_expires'))
        except KeyError:
            expired = True
        else:
            expiration = datetime.datetime.fromtimestamp(expiration_timestamp, datetime.timezone.utc)
            expired = expiration <= datetime.datetime.now(datetime.timezone.utc)
        if expired:
            self._oauth_refresh()

        return self.data.get(CONFIG_KEY, 'access_token')

    def _oauth_refresh(self, code: Optional[str] = None) -> None:
        """
        For the initial authorization flow, `code` is the authorization code passed via redirect by
        /v2/oauth2/authorize. After that, to refresh using the refresh token already in the DB,
        use the default `code=None`.
        """
        path = '/v2/oauth2/token'
        if code is not None:
            form_data = {
                'grant_type': 'authorization_code',
                'code': code
            }
        else:
            form_data = {
                'grant_type': 'refresh_token',
                'refresh_token': self.data.get(CONFIG_KEY, 'refresh_token')
            }
        response = requests.post(f'https://api.meethue.com{path}', data=form_data)
        _log(response, normal_status=401)
        auth = response.headers['WWW-Authenticate']
        realm_match = re.search('realm="(.*?)"', auth)
        nonce_match = re.search('nonce="(.*?)"', auth)
        if not realm_match or not nonce_match:
            logger.error(f'Bad OAuth refresh response: {response}')
            raise HueError
        realm = realm_match.group(1)
        nonce = nonce_match.group(1)

        h1 = _md5(f'{secret.HUE_CLIENT_ID}:{realm}:{secret.HUE_CLIENT_SECRET}')
        h2 = _md5(f'POST:{path}')
        digest_response = _md5(f'{h1}:{nonce}:{h2}')

        headers = {
            'Authorization':
                f'Digest username="{secret.HUE_CLIENT_ID}", realm="{realm}", '
                f'nonce="{nonce}", uri="{path}", response="{digest_response}"'
        }
        response = requests.post(f'https://api.meethue.com{path}', headers=headers, data=form_data)
        _log(response)
        tokens = response.json()
        self.data.set_subkey(CONFIG_KEY, 'access_token', tokens['access_token'])
        self.data.set_subkey(CONFIG_KEY, 'refresh_token', tokens['refresh_token'])
        ttl = datetime.timedelta(seconds=float(tokens['access_token_expires_in']))
        expiration = datetime.datetime.now(datetime.timezone.utc) + ttl
        self.data.set_subkey(CONFIG_KEY, 'access_token_expires', str(expiration.timestamp()))


class HueOAuthWebHandler(base.Handler[twitch_util.NullEvent]):
    # See the comment at twitch_util.TwitchOAuthWebHandler for why there's a NullEvent there.

    def __init__(self, hue_client: HueClient) -> None:
        super().__init__()
        self.states: Set[str] = set()
        self.hue_client = hue_client

    def check(self, event: twitch_util.NullEvent) -> bool:
        return False

    def run(self, event: twitch_util.NullEvent) -> Optional[str]:
        pass

    @web.url('/oauth/login/hue')
    def oauth_login(self):
        state = twitch_util.nonce()
        self.states.add(state)
        query = parse.urlencode({
            'client_id': secret.HUE_CLIENT_ID,
            'response_type': 'code',
            'state': state,
            # 'redirect_uri': flask.url_for('HueOAuthWebHandler.oauth_redirect', _external=True),
            # 'deviceid': '####',
            # 'devicename': '####',
        })
        return flask.redirect(f'https://api.meethue.com/v2/oauth2/authorize?{query}')

    @web.url('/oauth/redirect/hue')
    def oauth_redirect(self):
        logger.debug('OAuth redirect args: %s', pprint(flask.request.args))
        try:
            state = flask.request.args['state']
        except KeyError:
            return 'Missing state parameter', 400

        try:
            self.states.remove(state)
        except KeyError:
            logger.error('Expected states %s / got %s', self.states, state)
            return 'Wrong state parameter', 403

        try:
            code = flask.request.args['code']
        except KeyError:
            return 'Missing code parameter', 400

        self.hue_client._oauth_refresh(code=code)

        response = requests.put(
            'https://api.meethue.com/route/api/0/config',
            headers={'Authorization': f'Bearer {self.hue_client._access_token()}'},
            json={'linkbutton': True})
        request = response.request
        logger.debug('%s %s %s %s', request.method, request.url, request.body, request.headers)
        logger.debug('%d %s', response.status_code, response.text)

        response = requests.post(
            'https://api.meethue.com/route/api',
            headers={'Authorization': f'Bearer {self.hue_client._access_token()}'},
            json={'devicetype': 'impbot'})
        request = response.request
        logger.debug('%s %s %s %s', request.method, request.url, request.body, request.headers)
        json = response.json()
        logger.debug('%d %s', response.status_code, json)
        username = json[0]['success']['username']
        logger.debug('username: %s', username)
        self.data.set_subkey(CONFIG_KEY, 'username', username)

        return 'Logged in with your Hue account, thanks! You can close the tab now.'


class HueHandler(command.CommandHandler):
    def __init__(self, hue_client: HueClient) -> None:
        super().__init__()
        self.hue_client = hue_client

    def startup(self) -> None:
        self.hue_client.startup()

    def run_lightson(self, message: base.Message) -> Optional[str]:
        if not message.user.admin:
            return None
        self.hue_client.enabled = True
        return 'PogChamp'

    def run_lightsoff(self, message: base.Message) -> Optional[str]:
        if not message.user.admin:
            return None
        self.hue_client.enabled = False
        return '\U0001f44b'  # Waving Hand emoji

    def run_lights(self, scene: Optional[str]) -> Optional[str]:
        if not self.hue_client.enabled:
            return None
        if not scene:
            return self.hue_client.list_scenes()

        scene = _canonicalize(scene)
        if scene == 'rainbow':
            self.hue_client.colorloop()
            return None

        roulette = (scene == 'random')
        if roulette:
            scene = self.hue_client.random_scene()

        response = self.hue_client.set_scene(scene)
        if response is not None:
            # It's an error message.
            return response
        if roulette:
            name = self.data.get(scene, 'name')
            return f'How about... {name}! PogChamp'
        # Otherwise, no need to say anything.
        return None

    def run_blink(self) -> None:
        if not self.hue_client.enabled:
            return
        self.hue_client.blink()


class TwitchEventBlinkHandler(base.Handler[twitch_event.TwitchEvent]):
    def __init__(self, hue_client: HueClient) -> None:
        super().__init__()
        self.hue_client = hue_client

    def check(self, event: twitch_event.TwitchEvent) -> bool:
        return not isinstance(event, twitch_event.ModAction)

    def run(self, event: twitch_event.TwitchEvent) -> None:
        if self.hue_client.enabled:
            self.hue_client.blink()


class TwitchEnableDisableHandler(base.Handler[twitch_eventsub.TwitchEventSubEvent]):
    def __init__(self, hue_client: HueClient) -> None:
        super().__init__()
        self.hue_client = hue_client

    def check(self, event: twitch_eventsub.TwitchEventSubEvent) -> bool:
        return True

    def run(self, event: twitch_eventsub.TwitchEventSubEvent) -> Optional[str]:
        if isinstance(event, twitch_eventsub.StreamStartedEvent):
            if self.hue_client.enabled:
                return None
            self.hue_client.enabled = True
            return 'PogChamp PogChamp'

        if isinstance(event, twitch_eventsub.StreamEndedEvent):
            if not self.hue_client.enabled:
                return None
            self.hue_client.enabled = False
            return '\U0001f44b \U0001f44b'  # Waving Hand emoji

        if isinstance(event, twitch_eventsub.NewFollowerEvent):
            if self.hue_client.enabled:
                self.hue_client.blink()
            return None

        # Ignore StreamChangedEvents.
        return None


def _canonicalize(name: str) -> str:
    return ''.join(i for i in name.lower() if i in string.ascii_lowercase)


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
