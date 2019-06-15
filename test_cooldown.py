import datetime
import unittest

import base
import cooldown
import freezegun


class CooldownTest(unittest.TestCase):
    def setUp(self):
        start_time = datetime.datetime(2018, 1, 1, 12, 0, 0,
                                       tzinfo=datetime.timezone.utc)
        self._freeze_time = freezegun.freeze_time(start_time)
        self.time = self._freeze_time.start()

    def tearDown(self):
        self._freeze_time.stop()

    def testSimple(self):
        cd = cooldown.Cooldown(datetime.timedelta(minutes=1))
        self.assertTrue(cd.peek())
        self.assertTrue(cd.fire())
        self.assertFalse(cd.peek())
        self.time.tick(59)
        self.assertFalse(cd.peek())
        self.assertFalse(cd.fire())
        self.assertFalse(cd.peek())
        self.time.tick(1)
        self.assertTrue(cd.peek())
        self.assertTrue(cd.fire())
        self.assertFalse(cd.peek())

    def testCompound(self):
        cds = cooldown.GlobalAndUserCooldowns(datetime.timedelta(minutes=1),
                                              datetime.timedelta(minutes=5))
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertTrue(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(59)
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.assertFalse(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(1)
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertFalse(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertTrue(cds.fire(base.User('bob')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(4 * 60)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(60)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))

    def testCompoundGlobalOnly(self):
        cds = cooldown.GlobalAndUserCooldowns(datetime.timedelta(minutes=1),
                                              None)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertTrue(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(59)
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.assertFalse(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(1)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertTrue(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(4 * 60)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.time.tick(60)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))

    def testCompoundUserOnly(self):
        cds = cooldown.GlobalAndUserCooldowns(None,
                                              datetime.timedelta(minutes=5))
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertTrue(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.time.tick(59)
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertFalse(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.time.tick(1)
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertFalse(cds.fire(base.User('alice')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
        self.assertTrue(cds.fire(base.User('bob')))
        self.assertFalse(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(4 * 60)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertFalse(cds.peek(base.User('bob')))
        self.time.tick(60)
        self.assertTrue(cds.peek(base.User('alice')))
        self.assertTrue(cds.peek(base.User('bob')))
