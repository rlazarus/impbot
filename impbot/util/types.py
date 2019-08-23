from typing import Any, Type, cast, Union, _GenericAlias


def is_optional(t: Type) -> bool:
    """Returns True if `t` is an Optional type."""
    # Optional[T] is just sugar for Union[T, None], so really what we want to
    # know is, is the given type a Union that has None as one of its members?
    # Unfortunately some of this is still undocumented as of 3.7, so this may
    # need to be updated for future versions.
    #
    # The most elegant implementation would be "return isinstance(None, t)" but
    # subscripted generics like Union don't work with isinstance.
    if not is_instance(t, _GenericAlias):
        return False
    t = cast(_GenericAlias, t)
    return t.__origin__ == Union and type(None) in t.__args__


def is_instance(obj: Any, t: Type):
    """Generalized, type-hint-friendly form of the builtin isinstance.

    In addition to the types supported by isinstance, this function supports
    Any, Optional, and Union.
    """
    if t == Any:
        return True
    if obj is None:
        return t is type(None) or is_optional(t)
    if not isinstance(t, _GenericAlias):
        return isinstance(obj, t)
    t = cast(_GenericAlias, t)
    if t.__origin__ == Union:  # This also comes true if t is an Optional.
        return any(is_instance(obj, i) for i in t.__args__)
    # TODO: There's no reason this couldn't support other generic types, but it
    #       would require specific semantics for each (e.g. obj is only an
    #       instance of List[T] if it's a list *and* each of the elements is an
    #       instance of T. Similarly Dict[KT, VT] requires testing each key and
    #       each value. None of that is implemented just because it hasn't been
    #       needed in impbot.
    raise TypeError(f"{t}: is_instance doesn't support {t.__origin__.__name__}")
