import command
import tests_util


class FooHandler(command.CommandHandler):
    pass


class BarHandler(command.CommandHandler):
    pass


class DataTest(tests_util.DataHandlerTest):
    def test(self):
        foo = FooHandler()
        self.assertFalse(foo.data.exists("testing"))
        self.assertEqual(foo.data.get("testing"), None)
        self.assertEqual(foo.data.get("testing", "default"), "default")
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
        self.assertEqual(bar.data.get("testing"), None)
        foo.data.unset("testing")
        self.assertFalse(foo.data.exists("testing"))
        self.assertEqual(foo.data.get("testing"), None)
        self.assertEqual(foo.data.get("testing", "default"), "default")
        self.assertFalse(foo2.data.exists("testing"))