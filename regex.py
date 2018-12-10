import re
import sre_compile
from typing import Optional, Dict

import bot
from bot import Message


class RegexHandler(bot.Handler):
    def __init__(self, patterns: Dict[str, str]):
        try:
            self.patterns = {re.compile(k): v for k, v in patterns.items()}
        except sre_compile.error as e:
            raise bot.AdminError(e)
        self._action: Optional[str] = None

    def check(self, message: Message) -> bool:
        for pattern, action in self.patterns.items():
            match = pattern.search(message.text)
            if match:
                self._action = action
                return True
        self._action = None
        return False

    def run(self, message: Message) -> Optional[str]:
        # This is super not thread-safe -- we rely on calling run() exactly once
        # each time check() returns True, with nothing happening in between.
        action = self._action
        self._action = None
        return action
