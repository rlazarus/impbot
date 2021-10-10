import abc
import inspect
from typing import (Optional, Callable, ClassVar, List, Generic, TypeVar,
                    TYPE_CHECKING, Type, Any)

import attr

from impbot.core import data
from impbot.util import types

if TYPE_CHECKING:
    from impbot.core import web


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


@attr.s(auto_attribs=True)
class Event:
    reply_connection: Optional["ChatConnection"]


@attr.s(auto_attribs=True)
class Message(Event):
    user: User
    text: str


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


class ShuttingDownError(Exception):
    """We abandoned something because the bot is in the process of quitting."""
    pass


EventCallback = Callable[[Event], None]


class Module:
    # Subclasses of Connection or Handler may override url_rules to register URL
    # handlers; this is done automatically by the @web.url decorator. Nothing
    # should add to Module.url_rules directly: it remains empty as a shared
    # default. The same goes for Connection.url_rules and Handler.url_rules.
    url_rules: ClassVar[List["web.UrlRule"]] = []


# The Bot constructor takes a heterogeneous list of Modules and lists of
# Modules, for convenience when Module constructors are interdependent.
# ModuleGroup is a simple alias for a List[Module] with those semantics.
ModuleGroup = List[Module]


class Connection(Module, abc.ABC):
    @abc.abstractmethod
    def run(self, on_event: EventCallback) -> None:
        pass

    @abc.abstractmethod
    def shutdown(self) -> None:
        pass


class ChatConnection(Connection, abc.ABC):
    @abc.abstractmethod
    def say(self, text: str) -> None:
        pass


E = TypeVar("E", bound=Event, contravariant=True)


class EventGeneric(Generic[E]):
    def __init_subclass__(cls, generic_method: str, **kwargs):
        super().__init_subclass__(**kwargs)  # type: ignore
        # EventGeneric is generic in E, but all of the subclasses that actually
        # get initialized have concrete type arguments, so all the instances of
        # each class have the same value of E. But, critically, there's no way
        # to tell mypy that. So, morally, this is Callable[[Any, E], Any].
        cls._generic_method: Callable = getattr(cls, generic_method)

    @classmethod
    def _event_type(cls) -> Type[E]:
        # Because generics are subject to type erasure, we can't just look at
        # the type parameter; that is, at runtime we can't see that it was
        # defined as Handler[Message], so we can't use that to conclude that
        # Message subtypes are okay. Instead we inspect the type annotation of
        # the argument of a generic *method*, which should be the same type.
        params = inspect.signature(cls._generic_method).parameters
        [_, event_param] = params.values()
        return event_param.annotation

    @classmethod
    def typecheck(cls, event: Event) -> bool:
        """
        Returns True if this class's generic methods can accept events of the
        given event's type.

        The default implementation uses the type annotations provided by the
        subclass; subclasses shouldn't need to override it.
        """
        return types.is_instance(event, cls._event_type())


class Handler(Module, abc.ABC, EventGeneric[E], generic_method="check"):
    def __init_subclass__(cls, **kwargs) -> None:
        # generic_method is passed as a kwarg to the class declaration above,
        # but it's also passed explicitly in the super call here. The first is
        # for Handler itself, and the second is for subclasses of Handler (so
        # that they don't all have to specify it), so we need both. That's also
        # why generic_method is a string rather than a callable -- we could pass
        # generic_method=self.check here, but we couldn't do it above. Same is
        # true in Observer.
        super().__init_subclass__(generic_method="check",
                                  **kwargs)  # type: ignore
        if cls._event_type() == inspect.Parameter.empty:
            raise TypeError(
                "Type annotation for check() and run() parameter is required.")
        if (not isinstance(cls._event_type(), type) or
                not issubclass(cls._event_type(), Event)):
            raise TypeError(
                "Type annotation for check() and run() parameter must be Event "
                "or a subclass.")

    def __init__(self) -> None:
        self.data = data.Namespace(
            f"{type(self).__module__}.{type(self).__name__}")

    def startup(self) -> None:
        """
        Called after the bot is initialized but before any events are received.

        Subclasses may override this method to do any setup work that requires
        access to the database. The default implementation does nothing.
        """
        pass

    @abc.abstractmethod
    def check(self, event: E) -> bool:
        pass

    @abc.abstractmethod
    def run(self, event: E) -> Optional[str]:
        pass


class Observer(Module, abc.ABC, EventGeneric[E], generic_method="observe"):
    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(generic_method="observe", **kwargs)
        if cls._event_type() == inspect.Parameter.empty:
            raise TypeError(
                "Type annotation for observe() parameter is required.")
        if not issubclass(cls._event_type(), Event):
            raise TypeError(
                "Type annotation for observe() parameter must be Event or a "
                "subclass.")

    def __init__(self) -> None:
        self.data = data.Namespace(
            f"{type(self).__module__}.{type(self).__name__}")

    @abc.abstractmethod
    def observe(self, event: E) -> None:
        pass
