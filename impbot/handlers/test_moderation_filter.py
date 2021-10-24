import datetime
import re
from typing import List, Tuple
from unittest import mock

from impbot.connections import twitch
from impbot.core import data
from impbot.handlers import moderation_filter
from impbot.util import tests_util


class ModerationFilterHandlerTest(tests_util.DataHandlerTest):

    def setUp(self):
        super().setUp()
        handlers = moderation_filter.module_group(
            re.compile('$nomatch'), '', {'allowedurl.fyi'}, {twitch.TwitchUser('alloweduser')})
        self.mod_handler, self.permit_handler = handlers
        self.conn = mock.Mock()

    def tearDown(self):
        d = data.Namespace('impbot.handlers.moderation_filter.ModerationFilterHandler')
        d.unset('permitted')
        d.unset('warning')
        super().tearDown()

    def message(self, text: str, user: twitch.TwitchUser = None, action: bool = False,
                emotes: List[Tuple[str, int, int]] = None) -> twitch.TwitchMessage:
        if not user:
            user = twitch.TwitchUser('user', display_name='User')
        if not emotes:
            emotes = []
        return twitch.TwitchMessage(self.conn, user, text, 'id', None, 12345, action, emotes)

    def assert_allowed(self, text: str, user: twitch.TwitchUser = None, action: bool = False,
                       emotes: List[Tuple[str, int, int]] = None) -> None:
        message = self.message(text, user, action, emotes)
        self.assertFalse(self.mod_handler.check(message))

    def assert_blocked(self, text: str, user: twitch.TwitchUser = None, action: bool = False,
                       emotes: List[Tuple[int, int, int]] = None) -> None:
        message = self.message(text, user, action, emotes)
        self.assertTrue(self.mod_handler.check(message))
        self.mod_handler.run(message)

    def assert_timeout(self, reply_substring: str, timeout_secs: int, text: str,
                       user: twitch.TwitchUser = None, action: bool = False,
                       emotes: List[Tuple[str, int, int]] = None) -> None:
        self.assert_blocked(text, user, action, emotes)
        self.conn.timeout.assert_called_once()
        timeout_user, duration, reply = self.conn.timeout.call_args_list[0].args
        self.assertEqual(timeout_user.name, user.name if user else 'user')
        self.assertEqual(duration, datetime.timedelta(seconds=timeout_secs))
        self.assertIn(reply_substring, reply)
        self.conn.timeout.reset_mock()

    def assert_delete(self, reply_substring: str, text: str, user: twitch.TwitchUser = None,
                      action: bool = False, emotes: List[Tuple[str, int, int]] = None) -> None:
        self.assert_blocked(text, user, action, emotes)
        self.conn.delete.assert_called_once()
        message, reply = self.conn.delete.call_args_list[0].args
        self.assertEqual(message.text, text)
        self.assertEqual(message.user.name, user.name if user else 'user')
        self.assertIn(reply_substring, reply)
        self.conn.delete.reset_mock()

    def test_link(self):
        self.assert_allowed('example dot com')
        self.assert_timeout('post a link', 15, 'example.com')
        self.assert_timeout('post a link', 180, 'a link.org in the middle of a line')
        self.assert_timeout('post a link', 180, 'A SHOUTED LINK.NET')
        self.assert_allowed('shapedlikealink.butwithoutavalidtld')
        self.assert_allowed('alinkexample.combutwithoutspacesaroundit')
        self.assert_allowed('allowedurl.fyi')
        self.assert_allowed('ALLOWEDURL.FYI')

        self.assert_allowed('1.2.3')
        self.assert_timeout('post a link', 180, '1.2.3.4')
        self.assert_allowed('1.2.3.427')

        self.assert_timeout('post a link', 180, '[2607:f8b0:4002:c08::65]')
        self.assert_allowed('2607:f8b0:4002:c08::65')
        self.assert_allowed('[0]')
        self.assert_allowed('[0:1]')
        self.assert_allowed('[0:1:::0]')

    def test_permit(self):
        self.assert_timeout('post a link', 15, 'example.com')
        mod = twitch.TwitchUser('mod', display_name='Mod', is_moderator=True)
        self.assertTrue(self.permit_handler.check(self.message('!permit user', mod)))
        self.assertEqual(self.permit_handler.run(self.message('!permit user', mod)),
                         'user is now permitted to post a link in the next 45 seconds.')
        self.assert_timeout('post a link', 15, 'example.com', twitch.TwitchUser('anotheruser'))
        self.assert_allowed('example.com')
        self.assert_timeout('post a link', 180, 'example.com')

    def test_permit_alwaysallowed(self):
        alloweduser = twitch.TwitchUser('alloweduser')
        self.assert_allowed('example.com', alloweduser)
        mod = twitch.TwitchUser('mod', display_name='Mod', is_moderator=True)
        self.assertTrue(self.permit_handler.check(self.message('!permit alloweduser', mod)))
        self.assertEqual(self.permit_handler.run(self.message('!permit alloweduser', mod)),
                         "@Mod That's okay, alloweduser is always allowed to post links.")

    def test_other_filters(self):
        self.assert_delete('Colored text', 'waves', action=True)
        emotes = [('emote_id', i * 7, i * 7 + 5) for i in range(28)]
        self.assert_delete('Too many emotes', 'VoHiYo ' * 28, emotes=emotes)
        self.assert_delete("don't shout", 'A' * 50)
        self.assert_delete('Too many symbols', '!' * 50)
        self.assert_delete('Too many repeating characters', 'o' * 50)

    def test_mods_can_say_anything(self):
        mod = twitch.TwitchUser('mod', display_name='Mod', is_moderator=True)
        self.assert_allowed('link.com', user=mod)
        self.assert_allowed('colored text', user=mod, action=True)
        emotes = [('emote_id', i * 7, i * 7 + 5) for i in range(28)]
        self.assert_allowed('VoHiYo ' * 28, user=mod, emotes=emotes)
        self.assert_allowed('A' * 50, user=mod)
        self.assert_allowed('!' * 50, user=mod)
        self.assert_allowed('o' * 50, user=mod)

    def test_subs_can_say_most_things(self):
        sub = twitch.TwitchUser('sub', is_subscriber=True)
        self.assert_timeout('post a link', 15, 'link.com', user=sub)
        self.assert_allowed('colored text', user=sub, action=True)
        emotes = [('emote_id', i * 7, i * 7 + 5) for i in range(28)]
        self.assert_allowed('VoHiYo ' * 28, user=sub, emotes=emotes)
        self.assert_allowed('A' * 50, user=sub)
        self.assert_allowed('!' * 50, user=sub)
        self.assert_allowed('o' * 50, user=sub)

    def test_case_insensitive_permit(self):
        self.assert_timeout('post a link', 15, 'https://pcpartpicker.com/list/VpB96R')
        mod = twitch.TwitchUser('mod', display_name='Mod', is_moderator=True)
        self.assertTrue(self.permit_handler.check(self.message('!permit User', mod)))
        self.assertEqual(self.permit_handler.run(self.message('!permit User', mod)),
                         'User is now permitted to post a link in the next 45 seconds.')
        self.assert_allowed('a')
        self.assert_allowed('https://pcpartpicker.com/list/VpB96R')

    def test_permit_with_at_sign(self):
        self.assert_timeout('post a link', 15, 'https://pcpartpicker.com/list/VpB96R')
        mod = twitch.TwitchUser('mod', display_name='Mod', is_moderator=True)
        self.assertTrue(self.permit_handler.check(self.message('!permit @user', mod)))
        self.assertEqual(self.permit_handler.run(self.message('!permit @user', mod)),
                         'user is now permitted to post a link in the next 45 seconds.')
        self.assert_allowed('a')
        self.assert_allowed('https://pcpartpicker.com/list/VpB96R')
