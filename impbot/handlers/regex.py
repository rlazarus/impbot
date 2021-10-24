import re
import sre_compile
from typing import Mapping, Optional

from impbot.core import base


class RegexHandler(base.Handler[base.Message]):
    def __init__(self, patterns: Mapping[str, str]) -> None:
        super().__init__()
        try:
            self.patterns = {re.compile(k): v for k, v in patterns.items()}
        except sre_compile.error as e:
            raise base.AdminError(e)
        self._response: Optional[str] = None

    def check(self, message: base.Message) -> bool:
        for pattern, response in self.patterns.items():
            match = pattern.search(message.text)
            if match:
                self._response = response
                return True
        self._response = None
        return False

    def run(self, message: base.Message) -> Optional[str]:
        # This is super not thread-safe -- we rely on calling run() exactly once each time check()
        # returns True, with nothing happening in between.
        response = self._response
        self._response = None
        return response
