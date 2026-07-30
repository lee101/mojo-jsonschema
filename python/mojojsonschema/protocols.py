"""Typing protocol matching jsonschema.protocols.Validator."""

from __future__ import annotations

from typing import Protocol


class Validator(Protocol):
    schema: object

    def iter_errors(self, instance, _schema=None): ...
    def validate(self, *args, **kwargs): ...
    def is_valid(self, instance, _schema=None): ...

