"""Small compatibility helpers used by downstream code."""

from __future__ import annotations


def ensure_list(thing):
    return [thing] if isinstance(thing, str) else thing


def extras_msg(extras):
    extras = sorted(extras)
    verb = "was" if len(extras) == 1 else "were"
    return ", ".join(repr(extra) for extra in extras), verb

