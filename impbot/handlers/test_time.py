from unittest import mock

from impbot.core import base
from impbot.handlers import time
from impbot.util import tests_util


class TimeHandlerTest(tests_util.DataHandlerTest):

    def setUp(self):
        super().setUp()

        def get_channel_id(name):
            if name == "username":
                return 1234
            else:
                raise KeyError

        twitch_util = mock.Mock()
        twitch_util.get_channel_id = mock.Mock(side_effect=get_channel_id)
        twitch_util.get_display_name = mock.Mock(return_value="Username")
        chat = mock.Mock()
        chat.all_chatters = mock.Mock(return_value=[])
        self.handler = time.TimeHandler(twitch_util, chat, mock.Mock())

    def tearDown(self):
        self.handler.data.clear_all()
        super().tearDown()

    def test_human_duration(self):
        self.assertEqual(time.human_duration(0), "less than a minute")
        self.assertEqual(time.human_duration(7), "less than a minute")
        self.assertEqual(time.human_duration(60), "1 minute")
        self.assertEqual(time.human_duration(120), "2 minutes")
        self.assertEqual(time.human_duration(183), "3 minutes")
        self.assertEqual(time.human_duration(3600), "1 hour")
        self.assertEqual(time.human_duration(3660), "1 hour and 1 minute")
        self.assertEqual(time.human_duration(3720), "1 hour and 2 minutes")
        self.assertEqual(time.human_duration(36060), "10 hours and 1 minute")
        self.assertEqual(time.human_duration(36600), "10 hours and 10 minutes")

    def test_no_event(self):
        self.handler.data.set_subkey("total_time", "1234", "360")
        self.handler.data.set_subkey("legacy_time", "olduser", "420")
        self.assert_response("!time",
                             "@username You've spent 6 minutes in the chat.")
        self.assert_response("!time username",
                             "@username You've spent 6 minutes in the chat.")
        self.assert_response("!time username",
                             "Username has spent 6 minutes in the chat.",
                             user=base.User("another_user"))
        self.assert_response("!time olduser",
                             "olduser spent 7 minutes in the chat.")

    def test_event(self):
        self.handler.data.set("event_name", "Arbor Day")
        self.handler.data.set_subkey("total_time", "1234", "360")
        self.handler.data.set_subkey("event_time", "1234", "300")
        self.handler.data.set_subkey("legacy_time", "olduser", "420")
        self.assert_response("!time",
                             "@username You've spent 6 minutes in the chat (5 "
                             "minutes during the Arbor Day event).")
        self.assert_response("!time username",
                             "@username You've spent 6 minutes in the chat (5 "
                             "minutes during the Arbor Day event).")
        self.assert_response("!time username",
                             "Username has spent 6 minutes in the chat (5 "
                             "minutes during the Arbor Day event).",
                             user=base.User("another_user"))
        self.assert_response("!time olduser",
                             "olduser spent 7 minutes in the chat.")
