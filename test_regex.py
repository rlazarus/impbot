from collections import OrderedDict
import unittest

import base
import regex
import tests_util


class TestRegexSimple(tests_util.HandlerTest):
    def setUp(self):
        super().setUp()
        self.handler = regex.RegexHandler({'bleep': 'bloop'})

    def test_simple(self):
        self.assert_no_trigger('just a regular old message')
        self.assert_response('bleep', 'bloop')
        self.assert_response('a message with bleep and other text', 'bloop')


class TestRegexInteresting(tests_util.HandlerTest):
    def setUp(self):
        super().setUp()
        self.handler = regex.RegexHandler({'blee+p': 'bloop'})

    def test_simple(self):
        self.assert_no_trigger('blep')
        self.assert_response('bleep', 'bloop')
        self.assert_response('a message with bleeeeeep and other text', 'bloop')


class TestBrokenRegex(unittest.TestCase):
    def test_broken(self):
        self.assertRaises(base.AdminError, regex.RegexHandler, {'(': ''})


class TestPatternOrder(tests_util.HandlerTest):
    def setUp(self):
        super().setUp()
        self.handler = regex.RegexHandler(
            OrderedDict([('pattern', 'first'), ('pattern()', 'second')]))

    def test_order(self):
        self.assert_response('a line with the pattern', 'first')
