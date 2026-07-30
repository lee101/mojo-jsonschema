"""Benchmark mojo-jsonschema against upstream jsonschema on identical records."""

from __future__ import annotations

import gc
import math
import os
import platform
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

import jsonschema as upstream  # noqa: E402
import mojojsonschema as mjs  # noqa: E402


FLAT_SCHEMA = {
    "type": "object",
    "required": ["id", "score", "name"],
    "properties": {
        "id": {"type": "integer", "minimum": 0},
        "score": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
            "multipleOf": 0.5,
        },
        "name": {
            "type": "string",
            "minLength": 2,
            "maxLength": 12,
            "pattern": "^[A-Za-z]+$",
        },
        "active": {"type": "boolean"},
    },
    "additionalProperties": False,
}

NESTED_SCHEMA = {
    "type": "object",
    "required": ["id", "payload"],
    "properties": {
        "id": {"type": "integer", "minimum": 0},
        "payload": {
            "type": "object",
            "required": ["samples"],
            "properties": {
                "samples": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {"type": "number", "minimum": 0},
                }
            },
        },
    },
}


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def best_time(fn, repeat=2):
    best = math.inf
    for _ in range(repeat):
        gc.collect()
        started = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - started)
    return best


def flat_rows(count, mixed=False):
    rows = []
    for index in range(count):
        row = {
            "id": index,
            "score": float(index % 101),
            "name": "Alice",
            "active": bool(index & 1),
        }
        if mixed:
            if index % 17 == 0:
                row["score"] = -1.0
            if index % 29 == 0:
                row["name"] = "x1"
            if index % 43 == 0:
                row.pop("id")
        rows.append(row)
    return rows


def nested_rows(count):
    return [
        {"id": index, "payload": {"samples": [1.0, 2.0, 3.0, 4.0]}}
        for index in range(count)
    ]


def benchmark_case(name, schema, rows):
    ours = mjs.Draft202012Validator(schema)
    theirs = upstream.Draft202012Validator(schema)
    ours_fn = lambda: ours.is_valid_many(rows)
    ref_fn = lambda: [theirs.is_valid(row) for row in rows]
    ours_result = ours_fn()
    ref_result = ref_fn()
    if ours_result != ref_result:
        raise AssertionError(f"parity failed in benchmark case {name}")
    mojo_seconds = best_time(ours_fn)
    upstream_seconds = best_time(ref_fn)
    return name, mojo_seconds, upstream_seconds


def main():
    cases = [
        benchmark_case(
            "flat valid records (100k)",
            FLAT_SCHEMA,
            flat_rows(100_000),
        ),
        benchmark_case(
            "flat mixed records (100k)",
            FLAT_SCHEMA,
            flat_rows(100_000, mixed=True),
        ),
        benchmark_case(
            "nested fixed records (20k)",
            NESTED_SCHEMA,
            nested_rows(20_000),
        ),
    ]
    print(f"Machine: {cpu_name()}; {platform.system()} {platform.machine()}")
    print()
    print("| case | mojo-jsonschema | jsonschema 4.x | result |")
    print("| --- | ---: | ---: | ---: |")
    for name, mojo_seconds, upstream_seconds in cases:
        ratio = upstream_seconds / mojo_seconds
        result = (
            f"{ratio:.2f}x faster"
            if ratio >= 1
            else f"{1 / ratio:.2f}x slower"
        )
        print(
            f"| {name} | {mojo_seconds * 1000:.1f} ms | "
            f"{upstream_seconds * 1000:.1f} ms | {result} |"
        )


if __name__ == "__main__":
    main()
