import unittest
from typing import Optional

import command


class CommandTest(unittest.TestCase):
    def testNoArgs(self):
        self.assertEqual([], command._args([], run_x, ""))
        self.assertEqual([], command._args([], run_x, "with args"))

    def testOneStringArg(self):
        self.assertEqual(["foo"], command._args([str], run_x, "foo"))
        self.assertEqual(["foo bar"], command._args([str], run_x, "foo bar"))
        self.assertRaises(command.UsageError, command._args, [str], run_x, "")

    def testOneConvertedArg(self):
        self.assertEqual([17], command._args([int], run_x, "17"))
        self.assertRaises(command.UsageError, command._args, [int], run_x, "q")

    def testOneOptionalStringArg(self):
        self.assertEqual(["foo"], command._args([Optional[str]], run_x, "foo"))
        self.assertEqual(["foo bar"],
                         command._args([Optional[str]], run_x, "foo bar"))
        self.assertEqual([None], command._args([Optional[str]], run_x, ""))

    def testSeveralRequired(self):
        # A string in the middle must be exactly one word.
        self.assertEqual([6, "foo", 42.0],
                         command._args([int, str, float], run_x, "6 foo 42"))
        self.assertRaises(command.UsageError, command._args, [int, str, float],
                          run_x, "6 42")
        self.assertRaises(command.UsageError, command._args, [int, str, float],
                          run_x, "6  42")
        self.assertRaises(command.UsageError, command._args, [int, str, float],
                          run_x, "6 foo bar 42")

        # A string at the end must be at least one word.
        self.assertEqual([6, 42.0, "foo"],
                         command._args([int, float, str], run_x, "6 42 foo"))
        self.assertEqual([6, 42.0, "foo bar"],
                         command._args([int, float, str], run_x,
                                       "6 42 foo bar"))
        self.assertRaises(command.UsageError,
                          command._args, [int, float, str], run_x, "6 42")
        self.assertRaises(command.UsageError,
                          command._args, [int, float, str], run_x, "6 42 ")

    def testExceptionText(self):
        self.assertRaisesRegex(command.UsageError, "^Usage: !x <arga> <argb>$",
                               command._args, [str], run_x, "")
        self.assertRaisesRegex(command.UsageError,
                               "^Usage: !x <explicit usage string>$",
                               command._args, [str], run_y, "")


# _args takes a function (and checks that its name starts with "run_") but only
# actually uses it for constructing a UsageError. The function parameters don't
# have to match the types passed to _args.
def run_x(arga: int, argb: str):
    pass


def run_y():
    """!x <explicit usage string>"""
    pass
