import re
import sre_compile

import attr

from impbot.core import base
from impbot.handlers.regex import RegexHandler


class CustomRegexHandler(RegexHandler):

    def __init__(self) -> None:
        # Initialize with an empty dict, but fill it in startup().
        super().__init__({})

    def startup(self) -> None:
        try:
            for key, value in self.data.list(" pattern"):
                id = key[:-len(" pattern")]
                response = self.data.get(f"{id} response")
                self.patterns[re.compile(value)] = response
        except sre_compile.error as e:
            raise base.AdminError(e)

    def add_pattern(self, pattern: str, response: str) -> None:
        # TODO: Expose this (and edit, delete) in the web UI.
        try:
            id = int(self.data.get("next_id"))
        except KeyError:
            id = 0
        self.data.set("next_id", str(id + 1))
        self.data.set(f"{id} pattern", pattern)
        self.data.set(f"{id} response", response)
