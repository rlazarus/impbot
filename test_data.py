import unittest

import command
import data
import tests_util


class FooHandler(command.CommandHandler):
    pass


class BarHandler(command.CommandHandler):
    pass


class DataTest(tests_util.DataHandlerTest):
    def test(self):
        foo = FooHandler()
        self.handler = foo
        self.assertFalse(data.exists("testing"))
        self.assertEqual(data.get("testing"), None)
        self.assertEqual(data.get("testing", "default"), "default")
        self.assertEqual(data.list("ing"), [])
        data.set("testing", "value")
        self.assertTrue(data.exists("testing"))
        self.assertEqual(data.get("testing"), "value")
        self.assertEqual(data.list("ing"), [("testing", "value")])
        data.set("twosting", "another value")
        self.assertEqual(set(data.list("ing")),
                         {("testing", "value"), ("twosting", "another value")})
        foo2 = FooHandler()
        self.handler = foo2
        self.assertTrue(data.exists("testing"))
        self.assertEqual(data.get("testing"), "value")
        bar = BarHandler()
        self.handler = bar
        self.assertFalse(data.exists("testing"))
        self.assertEqual(data.get("testing"), None)
        self.handler = foo
        data.unset("testing")
        self.assertFalse(data.exists("testing"))
        self.assertEqual(data.get("testing"), None)
        self.assertEqual(data.get("testing", "default"), "default")
        self.handler = foo2
        self.assertFalse(data.exists("testing"))

# This doesn't extend DataHandlerTest so that _handler_classname isn't patched
# out.
class HandlerClassnameTest(unittest.TestCase):
    def test_handler(self):
        self.assertRaises(ValueError, data._handler_classname)
        class BazHandler(command.CommandHandler):
            def run_test(self):
                return data._handler_classname()
        self.assertEqual(BazHandler().run_test(), "BazHandler")

        def outer_callable():
            return BazHandler().run_test()
        self.assertEqual(outer_callable(), "BazHandler")

        def inner_callable():
            return data._handler_classname()

        class QuxHandler(command.CommandHandler):
            def run_test(self):
                return inner_callable()
        self.assertEqual(QuxHandler().run_test(), "QuxHandler")
