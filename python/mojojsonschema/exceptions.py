"""Exception types compatible with jsonschema's public error interface."""

from __future__ import annotations

from collections import deque


class _Error(Exception):
    def __init__(
        self,
        message,
        validator=None,
        path=(),
        cause=None,
        context=(),
        validator_value=None,
        instance=None,
        schema=None,
        schema_path=(),
        parent=None,
        type_checker=None,
    ):
        super().__init__(message)
        self.message = message
        self.validator = validator
        self.validator_value = validator_value
        self.instance = instance
        self.schema = schema
        self.path = deque(path)
        self.relative_path = self.path
        self.schema_path = deque(schema_path)
        self.relative_schema_path = self.schema_path
        self.context = list(context)
        self.cause = cause
        self.parent = parent
        self.type_checker = type_checker
        for error in self.context:
            error.parent = self

    @property
    def absolute_path(self):
        if self.parent is None:
            return self.path
        return deque((*self.parent.absolute_path, *self.path))

    @property
    def absolute_schema_path(self):
        if self.parent is None:
            return self.schema_path
        return deque((*self.parent.absolute_schema_path, *self.schema_path))

    @property
    def json_path(self):
        result = "$"
        for item in self.absolute_path:
            if isinstance(item, int):
                result += f"[{item}]"
            elif isinstance(item, str) and item.isidentifier():
                result += f".{item}"
            else:
                result += f"[{item!r}]"
        return result

    def __str__(self):
        return self.message


class ValidationError(_Error):
    pass


class SchemaError(_Error):
    pass


class RefResolutionError(Exception):
    pass


class FormatError(Exception):
    def __init__(self, message, cause=None):
        super().__init__(message)
        self.cause = cause


class UndefinedTypeCheck(Exception):
    pass


class UnknownType(Exception):
    pass


def relevance(error):
    return (-len(error.path), error.validator not in {"anyOf", "oneOf"})


def by_relevance(weak=frozenset({"anyOf", "oneOf"}), strong=frozenset()):
    def key(error):
        return (
            -len(error.path),
            error.validator not in weak,
            error.validator in strong,
            not error.context,
        )

    return key


def best_match(errors, key=relevance):
    errors = list(errors)
    if not errors:
        return None
    best = max(errors, key=key)
    while best.context:
        next_best = max(best.context, key=key)
        if key(next_best) == key(best):
            break
        best = next_best
    return best


class ErrorTree:
    def __init__(self, errors=()):
        self.errors = {}
        self._contents = {}
        for error in errors:
            container = self
            for element in error.path:
                container = container[element]
            container.errors[error.validator] = error

    def __contains__(self, index):
        return index in self._contents

    def __getitem__(self, index):
        return self._contents.setdefault(index, ErrorTree())

    def __setitem__(self, index, value):
        self._contents[index] = value

    def __iter__(self):
        return iter(self._contents)

    @property
    def total_errors(self):
        return len(self.errors) + sum(
            child.total_errors for child in self._contents.values()
        )

