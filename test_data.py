import command
import data
import tests_util


class FooHandler(command.CommandHandler):
    pass


class BarHandler(command.CommandHandler):
    pass


class DataTest(tests_util.DataTest):
    def test(self):
        foo = FooHandler()
        self.assertFalse(data.exists(foo, "testing"))
        self.assertEqual(data.get(foo, "testing"), None)
        self.assertEqual(data.get(foo, "testing", "default"), "default")
        data.set(foo, "testing", "value")
        self.assertTrue(data.exists(foo, "testing"))
        self.assertEqual(data.get(foo, "testing"), "value")
        foo2 = FooHandler()
        self.assertTrue(data.exists(foo2, "testing"))
        self.assertEqual(data.get(foo2, "testing"), "value")
        bar = BarHandler()
        self.assertFalse(data.exists(bar, "testing"))
        self.assertEqual(data.get(bar, "testing"), None)
        data.unset(foo, "testing")
        self.assertFalse(data.exists(foo, "testing"))
        self.assertFalse(data.exists(foo2, "testing"))
        self.assertEqual(data.get(foo, "testing"), None)
        self.assertEqual(data.get(foo, "testing", "default"), "default")
