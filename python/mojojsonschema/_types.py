"""JSON type checking and the public TypeChecker API."""

from __future__ import annotations

import numbers

from .exceptions import UndefinedTypeCheck


def _is_integer(instance):
    return (
        isinstance(instance, int)
        and not isinstance(instance, bool)
        or isinstance(instance, float)
        and instance.is_integer()
    )


DEFAULT_CHECKS = {
    "null": lambda checker, value: value is None,
    "boolean": lambda checker, value: isinstance(value, bool),
    "object": lambda checker, value: isinstance(value, dict),
    "array": lambda checker, value: isinstance(value, list),
    "number": lambda checker, value: isinstance(value, numbers.Number)
    and not isinstance(value, bool),
    "integer": lambda checker, value: _is_integer(value),
    "string": lambda checker, value: isinstance(value, str),
}


class TypeChecker:
    def __init__(self, type_checkers=None):
        self._type_checkers = dict(type_checkers or DEFAULT_CHECKS)

    def is_type(self, instance, type):
        try:
            fn = self._type_checkers[type]
        except KeyError:
            raise UndefinedTypeCheck(type) from None
        return fn(self, instance)

    def redefine(self, type, fn):
        return self.redefine_many({type: fn})

    def redefine_many(self, definitions):
        return TypeChecker({**self._type_checkers, **definitions})

    def remove(self, *types):
        checks = dict(self._type_checkers)
        for type in types:
            if type not in checks:
                raise UndefinedTypeCheck(type)
            del checks[type]
        return TypeChecker(checks)

    def __repr__(self):
        return f"<TypeChecker types={sorted(self._type_checkers)!r}>"


draft202012_type_checker = TypeChecker()
draft4_type_checker = draft202012_type_checker.redefine(
    "integer",
    lambda checker, value: isinstance(value, int) and not isinstance(value, bool),
)
