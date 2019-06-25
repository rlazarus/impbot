from abc import ABC, abstractmethod
from typing import Optional, Callable

import attr

import data


@attr.s(auto_attribs=True, frozen=True)
class User:
    """
    Represents a chat user. This is a value type: there may be more than one
    instance referring to the same user, and those instances are equal.

    For any given chat service, the name field should map 1:1 to a specific
    user identity. Each chat service should extend User with a distinct class,
    so that name collisions across separate services still result in unequal
    User objects.

    Subclasses may include fields other than name -- if they constitute metadata
    rather than part of the identity (e.g. display name or moderator status),
    they should be added with attr.ib(cmp=False) to exclude them from
    comparisons. As a result, it may be convenient to give them Optional types,
    where None means "unknown," and set them when handling events but leave them
    empty when creating a TwitchUser for the purpose of representing or storing
    an identity.
    """
    name: str
    admin: Optional[bool] = attr.ib(cmp=False, default=None)

    @property
    def moderator(self) -> bool:
        return False

    def __str__(self) -> str:
        """
        User.__str__ is always a display name suitable for using in a sentence.

        str(user1) == str(user2) does NOT imply user1 == user2, since two users
        may have the same name on different chat services, i.e. different
        subclasses of User.
        """
        return self.name


class Event:
    def reply(self, text: str) -> None:
        raise NotImplementedError


@attr.s(auto_attribs=True)
class Message(Event):
    user: User
    text: str
    reply: Callable[[str], None]


class UserError(Exception):
    """A user typed something wrong.

    This isn't really an exceptional condition, but it's convenient to have a
    quick escape route from the handler's control flow.
    """
    pass


class AdminError(Exception):
    """Something went wrong with the bot's settings.

    For now, this always crashes the bot.
    TODO: If it happens after we start up successfully, alert the bot's admins
    but do our best to carry on.
    """
    pass


class ServerError(Exception):
    """A server we're connected to did something unexpected.

    The difference between this and AdminError is that an AdminError can be
    resolved by fixing the bot's configuration. If the server sends us an
    "incorrect password" error, that's an AdminError, but if it hangs up on us
    that's a ServerError.
    """
    pass


EventCallback = Callable[[Event], None]


class Connection(ABC):
    @abstractmethod
    def say(self, text: str) -> None:
        pass

    @abstractmethod
    def run(self, on_event: EventCallback) -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class Handler(ABC):
    def __init__(self) -> None:
        self.data = data.Namespace(type(self).__name__)

    @abstractmethod
    def check(self, event: Event) -> bool:
        pass

    @abstractmethod
    def run(self, event: Event) -> Optional[str]:
        pass