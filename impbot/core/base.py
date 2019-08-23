import abc
import inspect
from typing import (Optional, Callable, ClassVar, List, Tuple, Dict, Any, Union,
                    Generic, TypeVar)

import attr
import flask

from impbot.core import data
from impbot.util import types


@attr.s(auto_attribs=True, frozen=True)
class User:
    """
    Represents a chat user. This is a value type: there may be more than one
    instance referring to the same user, and those instances are equal.

    For any given chat service, the name field should map 1:1 to a specific
    user identity. Each chat service should extend User with a distinct class,
    so that name collisions across separate services still result in unequal
    User objects.

    Subclasses may include fields other than name. If they constitute metadata,
    rather than part of the identity (e.g. display name or moderator status),
    they should be added with attr.ib(cmp=False) to exclude them from
    comparisons. As a result, it may be convenient to give them Optional types,
    where None means "unknown," and set them when handling events but leave them
    empty when creating a User for the purpose of representing or storing an
    identity.
    """
    name: str
    admin: Optional[bool] = attr.ib(cmp=False, default=None)

    @property
    def moderator(self) -> Optional[bool]:
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

# ViewResponse is the union of allowed return types from a web view function,
# according to Flask docs. (Returning a WSGI application is also allowed,
# omitted here.)
SimpleViewResponse = Union[flask.Response, str, bytes]
ViewResponse = Union[SimpleViewResponse,
                     Tuple[SimpleViewResponse, int, Dict[str, str]],
                     Tuple[SimpleViewResponse, int],
                     Tuple[SimpleViewResponse, Dict[str, str]]]
ViewFunc = Callable[..., ViewResponse]
UrlRule = Tuple[str, ViewFunc, Dict[str, Any]]


class Connection(abc.ABC):
    # Subclasses of Connection may override url_rules to register URL handlers;
    # this is done automatically by the @web.url decorator. Nothing should add
    # to Connection.url_rules directly: it remains empty as a shared default.
    url_rules: ClassVar[List[UrlRule]] = []

    @abc.abstractmethod
    def say(self, text: str) -> None:
        pass

    @abc.abstractmethod
    def run(self, on_event: EventCallback) -> None:
        pass

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass


E = TypeVar('E', bound=Event, contravariant=True)


class Handler(abc.ABC, Generic[E]):
    # As at Connection.url_rules, Handler subclasses may override this (@web.url
    # does so automatically) but should not edit the shared default.
    url_rules: ClassVar[List[UrlRule]] = []

    def __init__(self) -> None:
        self.data = data.Namespace(type(self).__name__)

    @abc.abstractmethod
    def check(self, event: E) -> bool:
        pass

    @abc.abstractmethod
    def run(self, event: E) -> Optional[str]:
        pass

    def typecheck(self, event: Event):
        """
        Returns True if this Handler can accept events of this event's type.
        """
        # Because generics are subject to type erasure, we can't just look at
        # the type parameter; that is, at runtime we can't see that it was
        # defined as Handler[Message], so we can't use that to conclude that
        # Message subtypes are okay. Instead we inspect the type annotation of
        # the check method's argument, which should be the same type.
        # TODO: This assumes the type hint is present -- if it's not, we should
        #       die on startup, rather than when we go to look at it.
        params = inspect.signature(self.check).parameters
        [event_param] = params.values()
        return types.is_instance(event, event_param.annotation)
