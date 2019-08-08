import unittest

from impbot.connections import twitch_webhook


class TestTwitchWebhookConnection(unittest.TestCase):
    def test_topic(self):
        link = (
            '<https://api.twitch.tv/helix/webhooks/hub>; rel="hub", '
            '<https://api.twitch.tv/helix/streams?user_id=1234>; rel="self"')
        self.assertEqual(
            "https://api.twitch.tv/helix/streams?user_id=1234",
            twitch_webhook._topic(link))
