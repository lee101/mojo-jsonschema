"""Columnar encoder for the native object validator."""

from __future__ import annotations

from array import array
import math
import re

from ._lib import PARALLEL_THRESHOLD, enable_parallel_runtime, lib

TYPE_BITS = {
    "null": 1,
    "boolean": 2,
    "integer": 4,
    "number": 8,
    "string": 16,
    "array": 32,
    "object": 64,
}

ANNOTATION_KEYS = {
    "title",
    "description",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "$comment",
}

SCALAR_KEYS = {
    "type",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "format",
} | ANNOTATION_KEYS

OBJECT_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "minProperties",
    "maxProperties",
} | ANNOTATION_KEYS

ARRAY_KEYS = {
    "type",
    "items",
    "minItems",
    "maxItems",
} | ANNOTATION_KEYS

ROOT_KEYS = OBJECT_KEYS | {"$schema", "$id"}
MAX_FIXED_ITEMS = 16
_MISSING = object()


def _address(values):
    if values.itemsize != 8:
        raise RuntimeError("native validation requires 64-bit array elements")
    return values.buffer_info()[0]


def _native_float(value):
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError
    if isinstance(value, int) and abs(value) > 2**53:
        raise ValueError
    return converted


def _tag(value):
    if value is None:
        return 1
    if isinstance(value, bool):
        return 2
    if isinstance(value, int):
        return 12
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError
        return 12 if value.is_integer() else 8
    if isinstance(value, str):
        return 16
    if isinstance(value, list):
        return 32
    if isinstance(value, dict):
        return 64
    return -1


def _extract(row, path):
    value = row
    for part in path:
        if isinstance(part, str):
            if not isinstance(value, dict) or part not in value:
                return _MISSING
        elif not isinstance(value, list) or part >= len(value):
            return _MISSING
        value = value[part]
    return value


class FlatSchema:
    def __init__(self, schema, format_checker=None):
        self.schema = schema
        self.format_checker = format_checker
        self.paths = []
        self.patterns = []
        self.formats = []
        self.object_checks = []
        self.rules = tuple(
            array(code) for code in ("q", "q", "q", "q", "d", "d", "d")
        )
        if not self._compile_object(schema, (), root=True):
            raise ValueError

    def _append_rule(self, path, subschema, required):
        types = subschema.get("type")
        if isinstance(types, str):
            types = [types]
        if not isinstance(types or [], list) or any(
            type_name not in TYPE_BITS for type_name in types or ()
        ):
            return False

        mask = 0
        for type_name in types or ():
            mask |= TYPE_BITS[type_name]
            if type_name == "number":
                mask |= TYPE_BITS["integer"]

        rule = 128 if required else 0
        lo = hi = multiple = 0.0
        min_len = max_len = 0
        if "minimum" in subschema:
            rule |= 1
            lo = _native_float(subschema["minimum"])
        if "maximum" in subschema:
            rule |= 2
            hi = _native_float(subschema["maximum"])
        if "exclusiveMinimum" in subschema:
            rule |= 4
            lo = _native_float(subschema["exclusiveMinimum"])
        if "exclusiveMaximum" in subschema:
            rule |= 8
            hi = _native_float(subschema["exclusiveMaximum"])
        if "multipleOf" in subschema:
            rule |= 16
            multiple = _native_float(subschema["multipleOf"])
        if "minLength" in subschema or "minItems" in subschema:
            rule |= 32
            min_len = subschema.get("minLength", subschema.get("minItems"))
        if "maxLength" in subschema or "maxItems" in subschema:
            rule |= 64
            max_len = subschema.get("maxLength", subschema.get("maxItems"))

        index = len(self.paths)
        self.paths.append(path)
        if "pattern" in subschema:
            self.patterns.append((index, re.compile(subschema["pattern"])))
        if "format" in subschema and self.format_checker is not None:
            self.formats.append((index, subschema["format"]))

        values = (mask, rule, min_len, max_len, lo, hi, multiple)
        for buffer, value in zip(self.rules, values):
            buffer.append(value)
        return True

    def _compile_schema(self, path, subschema, required):
        if not isinstance(subschema, dict):
            return False
        keys = set(subschema)
        type_value = subschema.get("type")
        is_object = "properties" in subschema or type_value == "object"
        is_array = "items" in subschema or type_value == "array"

        if is_object:
            if type_value != "object" or keys - OBJECT_KEYS or not required:
                return False
            if not self._append_rule(path, subschema, required):
                return False
            return self._compile_object(subschema, path)

        if is_array:
            if (
                type_value != "array"
                or keys - ARRAY_KEYS
                or not self._append_rule(path, subschema, required)
            ):
                return False
            if "items" not in subschema:
                return True
            minimum = subschema.get("minItems")
            maximum = subschema.get("maxItems")
            if (
                not required
                or minimum != maximum
                or not isinstance(minimum, int)
                or isinstance(minimum, bool)
                or not 0 <= minimum <= MAX_FIXED_ITEMS
            ):
                return False
            return all(
                self._compile_schema((*path, index), subschema["items"], True)
                for index in range(minimum)
            )

        return not keys - SCALAR_KEYS and self._append_rule(
            path, subschema, required
        )

    def _compile_object(self, schema, path, root=False):
        if not isinstance(schema, dict):
            return False
        allowed_keys = ROOT_KEYS if root else OBJECT_KEYS
        properties = schema.get("properties")
        required = schema.get("required", [])
        additional = schema.get("additionalProperties", True)
        if (
            set(schema) - allowed_keys
            or not isinstance(properties, dict)
            or (root and not properties)
            or not isinstance(required, list)
            or any(not isinstance(name, str) for name in required)
            or not isinstance(additional, bool)
        ):
            return False

        allowed = frozenset(properties)
        self.object_checks.append(
            (
                path,
                allowed,
                additional,
                schema.get("minProperties"),
                schema.get("maxProperties"),
            )
        )
        required_set = set(required)
        return all(
            self._compile_schema(
                (*path, name), subschema, name in required_set
            )
            for name, subschema in properties.items()
        )

    @classmethod
    def compile(cls, schema, format_checker=None):
        if (
            not isinstance(schema, dict)
            or schema.get("type") not in (None, "object")
        ):
            return None
        try:
            return cls(schema, format_checker)
        except (KeyError, OverflowError, TypeError, ValueError, re.error):
            return None

    def validate(self, instances):
        rows = instances if isinstance(instances, list) else list(instances)
        nrows = len(rows)
        if nrows == 0:
            return []
        if any(not isinstance(row, dict) for row in rows):
            return None

        size = nrows * len(self.paths)
        tags = array("q", [0]) * size
        numbers = array("d", [0.0]) * size
        lengths = array("q", [0]) * size
        try:
            for prop_index, path in enumerate(self.paths):
                base = prop_index * nrows
                for row_index, row in enumerate(rows):
                    value = _extract(row, path)
                    if value is _MISSING:
                        continue
                    tag = _tag(value)
                    if tag < 0:
                        return None
                    if isinstance(value, int) and abs(value) > 2**53:
                        return None
                    index = base + row_index
                    tags[index] = tag
                    if isinstance(value, (int, float)) and not isinstance(
                        value, bool
                    ):
                        numbers[index] = float(value)
                    elif isinstance(value, (str, list)):
                        lengths[index] = len(value)
        except (OverflowError, ValueError):
            return None

        valid = array("q", [0]) * nrows
        use_parallel = nrows >= PARALLEL_THRESHOLD and enable_parallel_runtime()
        status = lib().mjs_validate_flat(
            _address(tags),
            _address(numbers),
            _address(lengths),
            _address(valid),
            *(_address(values) for values in self.rules),
            nrows,
            len(self.paths),
            use_parallel,
        )
        if status != 0:
            raise RuntimeError(f"Mojo validation kernel failed with status {status}")

        for row_index, row in enumerate(rows):
            if not valid[row_index]:
                continue
            for path, allowed, additional, minimum, maximum in self.object_checks:
                value = _extract(row, path)
                if not isinstance(value, dict):
                    continue
                if not additional and not value.keys() <= allowed:
                    valid[row_index] = 0
                    break
                if minimum is not None and len(value) < minimum:
                    valid[row_index] = 0
                    break
                if maximum is not None and len(value) > maximum:
                    valid[row_index] = 0
                    break
            if not valid[row_index]:
                continue
            for prop_index, pattern in self.patterns:
                value = _extract(row, self.paths[prop_index])
                if isinstance(value, str) and pattern.search(value) is None:
                    valid[row_index] = 0
                    break
            if not valid[row_index]:
                continue
            for prop_index, format_name in self.formats:
                value = _extract(row, self.paths[prop_index])
                if value is not _MISSING and not self.format_checker.conforms(
                    value, format_name
                ):
                    valid[row_index] = 0
                    break
        return [bool(value) for value in valid]
