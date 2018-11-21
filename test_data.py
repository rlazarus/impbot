import unittest

import command
import data


class FooHandler(command.CommandHandler):
    pass


class BarHandler(command.CommandHandler):
    pass


class DataTest(unittest.TestCase):
    def test(self):
        foo = FooHandler()
        self.assertEqual(data.get(foo, "testing"), None)
        self.assertEqual(data.get(foo, "testing", 42), 42)
        data.set(foo, "testing", "value")
        self.assertEqual(data.get(foo, "testing"), "value")
        foo2 = FooHandler()
        self.assertEqual(data.get(foo2, "testing"), "value")
        bar = BarHandler()
        self.assertEqual(data.get(bar, "testing"), None)
