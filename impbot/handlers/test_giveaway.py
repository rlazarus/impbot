import unittest
from unittest import mock

from impbot.core import base
from impbot.handlers import giveaway
from impbot.util import tests_util
from impbot.connections import twitch


class GiveawayHandlerTest(tests_util.DataHandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = giveaway.GiveawayHandler()
    
    def _message(self, input: str, username: str, highlight: bool):
        return twitch.TwitchMessage(
            None, twitch.TwitchUser(username, None, username.title()), input,
            "aaa-123", "highlighted-message" if highlight else None)

    def test(self):
        self.assertFalse(self.handler.check(
            self._message("enter", "user", False)))
        self.assertFalse(self.handler.check(
            self._message("hi", "user", True)))
        message = self._message("I would like to ENTER please", "user", True)
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), "@User You've entered the giveaway, good luck!")
        
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), "@User You've entered 2 times now!")
        
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), "@User You've entered 3 times now!")
        
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), "@User You've entered 4 times now -- that's the maximum, good luck!")

        message = self._message("enter me too", "anotheruser", True)
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), "@Anotheruser You've entered the giveaway, good luck!")

        self.assertEqual(self.handler._get_all_entries(),
                         "1. anotheruser\n2. user\n3. user\n4. user\n5. user")
