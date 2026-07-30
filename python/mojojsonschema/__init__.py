"""JSON Schema validation with a Mojo-accelerated batch path."""

from __future__ import annotations

from ._format import FormatChecker
from ._types import TypeChecker
from .exceptions import SchemaError, ValidationError, best_match
from .validators import (
    Draft4Validator,
    Draft6Validator,
    Draft7Validator,
    Draft201909Validator,
    Draft202012Validator,
    validator_for,
)


def validate(instance, schema, cls=None, *args, **kwargs):
    if cls is None:
        cls = validator_for(schema)
    cls.check_schema(schema)
    validator = cls(schema, *args, **kwargs)
    error = best_match(validator.iter_errors(instance))
    if error is not None:
        raise error


def validate_many(instances, schema, cls=None, *args, **kwargs):
    if cls is None:
        cls = validator_for(schema)
    cls.check_schema(schema)
    return cls(schema, *args, **kwargs).is_valid_many(instances)


__all__ = [
    "Draft4Validator",
    "Draft6Validator",
    "Draft7Validator",
    "Draft201909Validator",
    "Draft202012Validator",
    "FormatChecker",
    "SchemaError",
    "TypeChecker",
    "ValidationError",
    "validate",
    "validate_many",
]
