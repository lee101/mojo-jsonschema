"""FormatChecker with the commonly used built-in JSON Schema formats."""

from __future__ import annotations

import datetime as _datetime
import ipaddress
import re
import uuid

from .exceptions import FormatError


def _email(value):
    return not isinstance(value, str) or "@" in value


def _hostname(value):
    if not isinstance(value, str):
        return True
    if len(value) > 253:
        return False
    return all(
        label
        and len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in value.rstrip(".").split(".")
    )


def _datetime_check(value):
    if not isinstance(value, str):
        return True
    if "T" not in value.upper():
        return False
    try:
        parsed = _datetime.datetime.fromisoformat(
            value.replace("Z", "+00:00").replace("z", "+00:00")
        )
        return parsed.utcoffset() is not None
    except ValueError:
        return False


def _date(value):
    if not isinstance(value, str):
        return True
    try:
        _datetime.date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _time(value):
    if not isinstance(value, str):
        return True
    try:
        _datetime.datetime.strptime(value, "%H:%M:%S")
        return True
    except (TypeError, ValueError):
        return False


def _json_pointer(value):
    return not isinstance(value, str) or (
        value == ""
        or value.startswith("/")
        and all(
            re.fullmatch(r"(?:[^~]|~[01])*", part)
            for part in value.split("/")[1:]
        )
    )


def _ip(value, version):
    if not isinstance(value, str):
        return True
    try:
        return ipaddress.ip_address(value).version == version
    except ValueError:
        return False


def _regex(value):
    if not isinstance(value, str):
        return True
    try:
        re.compile(value)
        return True
    except (TypeError, re.error):
        return False


def _uuid(value):
    if not isinstance(value, str):
        return True
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (AttributeError, ValueError):
        return False


class FormatChecker:
    checkers = {}

    def __init__(self, formats=None):
        selected = self.checkers if formats is None else {
            name: self.checkers[name] for name in formats if name in self.checkers
        }
        self.checkers = dict(selected)

    @classmethod
    def cls_checks(cls, format, raises=()):
        return cls._checks(format, raises)

    @classmethod
    def _checks(cls, format, raises=()):
        def decorator(fn):
            cls.checkers[format] = (fn, raises)
            return fn

        return decorator

    def checks(self, format, raises=()):
        def decorator(fn):
            self.checkers[format] = (fn, raises)
            return fn

        return decorator

    def check(self, instance, format):
        if format not in self.checkers:
            return
        fn, raises = self.checkers[format]
        try:
            valid = fn(instance)
        except raises as error:
            raise FormatError(
                f"{instance!r} is not a {format!r}", cause=error
            ) from error
        if not valid:
            raise FormatError(f"{instance!r} is not a {format!r}")

    def conforms(self, instance, format):
        try:
            self.check(instance, format)
            return True
        except FormatError:
            return False


FormatChecker.checkers.update(
    {
        "email": (_email, ()),
        "idn-email": (_email, ()),
        "hostname": (_hostname, ()),
        "ipv4": (lambda value: _ip(value, 4), ()),
        "ipv6": (lambda value: _ip(value, 6), ()),
        "date-time": (_datetime_check, ()),
        "date": (_date, ()),
        "time": (_time, ()),
        "regex": (_regex, ()),
        "uuid": (_uuid, ()),
        "json-pointer": (_json_pointer, ()),
        "relative-json-pointer": (
            lambda value: not isinstance(value, str)
            or (
                re.fullmatch(
                    r"(?:0|[1-9][0-9]*)(?:#|(?:/(?:[^~]|~[01])*)*)",
                    value,
                )
                is not None
            ),
            (),
        ),
    }
)
