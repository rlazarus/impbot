import unittest
from typing import Optional, Union, List, Callable

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

    def testTrailingOptionals(self):
        self.assertEqual([6, None, None],
                         command._args([int, Optional[int], Optional[str]],
                                       run_x, "6"))
        self.assertEqual([6, 12, None],
                         command._args([int, Optional[int], Optional[str]],
                                       run_x, "6 12"))
        self.assertEqual([6, 12, "foo"],
                         command._args([int, Optional[int], Optional[str]],
                                       run_x, "6 12 foo"))
        self.assertEqual([6, 12, "foo bar"],
                         command._args([int, Optional[int], Optional[str]],
                                       run_x, "6 12 foo bar"))
        self.assertRaises(command.UsageError, command._args,
                          [int, Optional[int], Optional[str]], run_x, "6 foo")

    def testUnionFallback(self):
        self.assertEqual([16], command._args([Union[int, str]], run_x, "16"))
        self.assertEqual(["two"], command._args([Union[int, str]], run_x, "two"))
        self.assertRaises(command.UsageError, command._args, [Union[int, str]],
                          run_x, "")
        self.assertRaises(command.UsageError, command._args,
                          [Union[int, float]], run_x, "two")

    def testExceptionText(self):
        self.assertRaisesRegex(command.UsageError, r"^Usage: !x <arga> <argb>$",
                               command._args, [str], run_x, "")
        self.assertRaisesRegex(command.UsageError,
                               r"^Usage: !y <arga> \[<argb>\] \[<argc>\]$",
                               command._args, [str], run_y, "")
        self.assertRaisesRegex(command.UsageError,
                               r"^Usage: !z <explicit usage string>$",
                               command._args, [str], run_z, "")

    def testIsOptional(self):
        self.assertTrue(command._is_optional(Optional[str]))
        self.assertTrue(command._is_optional(Union[str, None]))
        self.assertTrue(command._is_optional(Union[None, str]))
        self.assertTrue(command._is_optional(Union[str, int, None]))
        self.assertFalse(command._is_optional(str))
        self.assertFalse(command._is_optional(List[str]))
        self.assertFalse(command._is_optional(Callable[[Optional[str]], str]))


# _args takes a function (and checks that its name starts with "run_") but only
# actually uses it for constructing a UsageError. The function parameters don't
# have to match the types passed to _args.
def run_x(arga: int, argb: str):
    pass

def run_y(arga: int, argb: Optional[str], argc: Optional[int]):
    pass

def run_z():
    """!z <explicit usage string>"""
    pass
