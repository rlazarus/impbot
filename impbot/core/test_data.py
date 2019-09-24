from impbot.handlers import command
from impbot.util import tests_util


class FooHandler(command.CommandHandler):
    pass


class BarHandler(command.CommandHandler):
    pass


class DataTest(tests_util.DataHandlerTest):
    def test_keys(self):
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
        foo.data.clear_all("%ing")
        self.assertEqual(foo.data.list("ing"), [])

    def test_namespaces(self):
        foo = FooHandler()
        foo.data.set("key", "value")
        foo2 = FooHandler()
        self.assertTrue(foo2.data.exists("key"))
        self.assertEqual(foo2.data.get("key"), "value")
        bar = BarHandler()
        self.assertFalse(bar.data.exists("key"))
        self.assertRaises(KeyError, bar.data.get, "key")
        foo.data.unset("key")
        self.assertFalse(foo.data.exists("key"))
        self.assertRaises(KeyError, foo.data.get, "key")
        self.assertFalse(foo2.data.exists("key"))
