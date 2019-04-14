import collections
import re
import sre_compile
from typing import Optional, Mapping

import bot


class RegexHandler(bot.Handler):
    def __init__(self, patterns: Mapping[str, str]) -> None:
        super().__init__()
        try:
            # Store the patterns in an OrderedDict so that if the input was
            # ordered, that order is preserved. If a line matches more than one
            # pattern, the first one wins.
            self.patterns = collections.OrderedDict(
                (re.compile(k), v) for k, v in patterns.items())
        except sre_compile.error as e:
            raise bot.AdminError(e)
        self._action: Optional[str] = None

    def check(self, message: bot.Message) -> bool:
        for pattern, action in self.patterns.items():
            match = pattern.search(message.text)
            if match:
                self._action = action
                return True
        self._action = None
        return False

    def run(self, message: bot.Message) -> Optional[str]:
        # This is super not thread-safe -- we rely on calling run() exactly once
        # each time check() returns True, with nothing happening in between.
        action = self._action
        self._action = None
        return action
