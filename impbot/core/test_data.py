from impbot.handlers import command
from impbot.util import tests_util


class FooHandler(command.CommandHandler):
    pass


class BarHandler(command.CommandHandler):
    pass


class DataTest(tests_util.DataHandlerTest):
    def test(self):
        foo = FooHandler()
        self.assertFalse(foo.data.exists("testing"))
        self.assertRaises(KeyError, foo.data.get, "testing")
        self.assertEqual(foo.data.list("ing"), [])
        foo.data.set("testing", "value")
        self.assertTrue(foo.data.exists("testing"))
        self.assertEqual(foo.data.get("testing"), "value")
        self.assertEqual(foo.data.list("ing"), [("testing", "value")])
        foo.data.set("twosting", "another value")
        self.assertEqual(set(foo.data.list("ing")),
                         {("testing", "value"), ("twosting", "another value")})
        foo2 = FooHandler()
        self.assertTrue(foo2.data.exists("testing"))
        self.assertEqual(foo2.data.get("testing"), "value")
        bar = BarHandler()
        self.assertFalse(bar.data.exists("testing"))
        self.assertRaises(KeyError, bar.data.get, "testing")
        foo.data.unset("testing")
        self.assertFalse(foo.data.exists("testing"))
        self.assertRaises(KeyError, foo.data.get, "testing")
        self.assertFalse(foo2.data.exists("testing"))