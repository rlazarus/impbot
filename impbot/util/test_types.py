import unittest
from typing import Optional, Union, List, Callable, Any

from impbot.util import types


class MyTestCase(unittest.TestCase):
    def testIsOptional(self):
        self.assertTrue(types.is_optional(Optional[str]))
        self.assertTrue(types.is_optional(Union[str, None]))
        self.assertTrue(types.is_optional(Union[None, str]))
        self.assertTrue(types.is_optional(Union[str, int, None]))
        self.assertFalse(types.is_optional(str))
        self.assertFalse(types.is_optional(List[str]))
        self.assertFalse(types.is_optional(Callable[[Optional[str]], str]))

    def testIsInstance(self):
        self.assertTrue(types.is_instance(5, int))
        self.assertTrue(types.is_instance(5, Optional[int]))
        self.assertTrue(types.is_instance(5, Union[int, str]))
        self.assertFalse(types.is_instance('five', int))
        self.assertFalse(types.is_instance('five', Optional[int]))
        self.assertTrue(types.is_instance('five', Union[int, str]))
        self.assertFalse(types.is_instance('five', Union[int, float]))
        self.assertTrue(types.is_instance(5, Any))
        self.assertTrue(types.is_instance(object(), Any))
        self.assertTrue(types.is_instance(None, type(None)))
        self.assertTrue(types.is_instance(None, Optional[int]))
        self.assertFalse(types.is_instance(None, int))


if __name__ == '__main__':
    unittest.main()
