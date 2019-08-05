from typing import Callable

import attr

from impbot.core import base


@attr.s(auto_attribs=True)
class LambdaEvent(base.Event):
    run: Callable[[], None]


class LambdaHandler(base.Handler):
    """
    Occasionally it's handy for a Connection to run some chunk of code on the
    event-handling thread. To do that, wrap it into the run field of a
    LambdaEvent. This handler is installed automatically in the Bot.
    """

    def check(self, event: base.Event) -> bool:
        return isinstance(event, LambdaEvent)

    def run(self, event: LambdaEvent) -> None:
        event.run()
