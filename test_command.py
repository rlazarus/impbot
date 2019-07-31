import unittest
from typing import Optional, Union, List, Callable

import command


class CommandTest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.x = command.Command("x", run_x)
        self.y = command.Command("y", run_y)
        self.z = command.Command("z", run_z)

    def testNoArgs(self):
        self.assertEqual([], command._args([], self.x, ""))
        self.assertEqual([], command._args([], self.x, "with args"))

    def testOneStringArg(self):
        self.assertEqual(["foo"], command._args([str], self.x, "foo"))
        self.assertEqual(["foo bar"], command._args([str], self.x, "foo bar"))
        self.assertRaises(command.UsageError, command._args, [str], self.x, "")

    def testOneConvertedArg(self):
        self.assertEqual([17], command._args([int], self.x, "17"))
        self.assertRaises(command.UsageError, command._args, [int], self.x, "q")

    def testOneOptionalStringArg(self):
        self.assertEqual(["foo"], command._args([Optional[str]], self.x, "foo"))
        self.assertEqual(["foo bar"],
                         command._args([Optional[str]], self.x, "foo bar"))
        self.assertEqual([None], command._args([Optional[str]], self.x, ""))

    def testSeveralRequired(self):
        # A string in the middle must be exactly one word.
        self.assertEqual([6, "foo", 42.0],
                         command._args([int, str, float], self.x, "6 foo 42"))
        self.assertRaises(command.UsageError, command._args, [int, str, float],
                          self.x, "6 42")
        self.assertRaises(command.UsageError, command._args, [int, str, float],
                          self.x, "6  42")
        self.assertRaises(command.UsageError, command._args, [int, str, float],
                          self.x, "6 foo bar 42")

        # A string at the end must be at least one word.
        self.assertEqual([6, 42.0, "foo"],
                         command._args([int, float, str], self.x, "6 42 foo"))
        self.assertEqual([6, 42.0, "foo bar"],
                         command._args([int, float, str], self.x,
                                       "6 42 foo bar"))
        self.assertRaises(command.UsageError,
                          command._args, [int, float, str], self.x, "6 42")
        self.assertRaises(command.UsageError,
                          command._args, [int, float, str], self.x, "6 42 ")

    def testTrailingOptionals(self):
        self.assertEqual([6, None, None],
                         command._args([int, Optional[int], Optional[str]],
                                       self.x, "6"))
        self.assertEqual([6, 12, None],
                         command._args([int, Optional[int], Optional[str]],
                                       self.x, "6 12"))
        self.assertEqual([6, 12, "foo"],
                         command._args([int, Optional[int], Optional[str]],
                                       self.x, "6 12 foo"))
        self.assertEqual([6, 12, "foo bar"],
                         command._args([int, Optional[int], Optional[str]],
                                       self.x, "6 12 foo bar"))
        self.assertRaises(command.UsageError, command._args,
                          [int, Optional[int], Optional[str]], self.x, "6 foo")

    def testUnionFallback(self):
        self.assertEqual([16], command._args([Union[int, str]], self.x, "16"))
        self.assertEqual(["two"], command._args([Union[int, str]], self.x, "two"))
        self.assertRaises(command.UsageError, command._args, [Union[int, str]],
                          self.x, "")
        self.assertRaises(command.UsageError, command._args,
                          [Union[int, float]], self.x, "two")

    def testExceptionText(self):
        self.assertRaisesRegex(command.UsageError, r"^Usage: !x <arga> <argb>$",
                               command._args, [str], self.x, "")
        self.assertRaisesRegex(command.UsageError,
                               r"^Usage: !y <arga> \[<argb>\] \[<argc>\]$",
                               command._args, [str], self.y, "")
        self.assertRaisesRegex(command.UsageError,
                               r"^Usage: !z <explicit usage string>$",
                               command._args, [str], self.z, "")

    def testIsOptional(self):
        self.assertTrue(command._is_optional(Optional[str]))
        self.assertTrue(command._is_optional(Union[str, None]))
        self.assertTrue(command._is_optional(Union[None, str]))
        self.assertTrue(command._is_optional(Union[str, int, None]))
        self.assertFalse(command._is_optional(str))
        self.assertFalse(command._is_optional(List[str]))
        self.assertFalse(command._is_optional(Callable[[Optional[str]], str]))


def run_x(arga: int, argb: str):
    pass


def run_y(arga: int, argb: Optional[str], argc: Optional[int]):
    pass


def run_z():
    """!z <explicit usage string>"""
    pass
