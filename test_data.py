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
        self.assertFalse(data.exists(foo, "testing"))
        self.assertEqual(data.get(foo, "testing"), None)
        self.assertEqual(data.get(foo, "testing", "default"), "default")
        data.set(foo, "testing", "value")
        self.assertTrue(data.exists(foo, "testing"))
        self.assertEqual(data.get(foo, "testing"), "value")
        foo2 = FooHandler()
        self.handler = foo2
        self.assertTrue(data.exists(foo2, "testing"))
        self.assertEqual(data.get(foo2, "testing"), "value")
        bar = BarHandler()
        self.handler = bar
        self.assertFalse(data.exists(bar, "testing"))
        self.assertEqual(data.get(bar, "testing"), None)
        self.handler = foo
        data.unset(foo, "testing")
        self.assertFalse(data.exists(foo, "testing"))
        self.assertEqual(data.get(foo, "testing"), None)
        self.assertEqual(data.get(foo, "testing", "default"), "default")
        self.handler = foo2
        self.assertFalse(data.exists(foo2, "testing"))

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
