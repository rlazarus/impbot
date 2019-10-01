from impbot.handlers import command
from impbot.util import tests_util


class FooHandler(command.CommandHandler):
    pass


class BarHandler(command.CommandHandler):
    pass


class DataTest(tests_util.DataHandlerTest):
    def test_keys(self):
        data = FooHandler().data
        self.assertFalse(data.exists("testing"))
        self.assertRaises(KeyError, data.get, "testing")
        self.assertEqual(data.get_all_values(), {})
        data.set("testing", "value")
        self.assertTrue(data.exists("testing"))
        self.assertEqual(data.get("testing"), "value")
        self.assertEqual(data.get_all_values(), {"testing": "value"})
        data.set("twosting", "another value")
        self.assertEqual(data.get_all_values(),
                         {"testing": "value", "twosting": "another value"})
        data.clear_all(except_keys=["testing"])
        self.assertEqual(data.get_all_values(), {"testing": "value"})
        data.clear_all()
        self.assertEqual(data.get_all_values(), {})

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

    def test_subkeys(self):
        data = FooHandler().data
        self.assertFalse(data.exists("key"))
        self.assertRaises(KeyError, data.get, "key")
        self.assertEqual(data.get_all_values(), {})
        data.set_subkey("key", "a", "alpha")
        data.set_subkey("key", "b", "bravo")
        data.set_subkey("key", "c", "charlie")
        self.assertEqual(data.get_dict("key"),
                         {"a": "alpha", "b": "bravo", "c": "charlie"})
        self.assertEqual(data.get("key", "b"), "bravo")
        self.assertTrue(data.exists("key"))
        self.assertTrue(data.exists("key", "a"))
        self.assertFalse(data.exists("key", "d"))
        data.set_subkey("key", "b", "baker")
        self.assertEqual(data.get("key", "b"), "baker")
        self.assertEqual(data.get_dict("key"),
                         {"a": "alpha", "b": "baker", "c": "charlie"})
        data.set("key", {"a": "able", "e": "easy"})
        self.assertEqual(data.get_dict("key"), {"a": "able", "e": "easy"})
        self.assertEqual(data.get("key", "a"), "able")
        self.assertEqual(data.get("key", "e"), "easy")
        self.assertFalse(data.exists("key", "b"))

    def test_empty_dict(self):
        data = FooHandler().data
        self.assertFalse(data.exists("key"))
        self.assertRaises(KeyError, data.get, "key")
        self.assertRaises(KeyError, data.get_dict, "key")

        data.set("key", {})
        self.assertTrue(data.exists("key"))
        self.assertEqual(data.get_dict("key"), {})
        self.assertFalse(data.exists("key", "subkey"))
        self.assertRaises(KeyError, data.get, "key", "subkey")

        data.unset("key")
        self.assertFalse(data.exists("key"))
        self.assertRaises(KeyError, data.get, "key")
        self.assertRaises(KeyError, data.get_dict, "key")

    def test_mismatch(self):
        data = FooHandler().data
        data.set("no_subkeys", "value")
        data.set_subkey("subkeys", "subkey", "value")

        self.assertRaises(TypeError, data.get, "subkeys")
        self.assertRaises(TypeError, data.get, "no_subkeys", "subkey")
        self.assertRaises(TypeError, data.get_dict, "no_subkeys")
        self.assertRaises(TypeError, data.set_subkey, "no_subkeys", "subkey",
                          "value")
        self.assertRaises(TypeError, data.set, "no_subkeys", {})
        self.assertRaises(TypeError, data.set, "subkeys", "value")
        self.assertRaises(TypeError, data.exists, "no_subkeys", "subkey")
