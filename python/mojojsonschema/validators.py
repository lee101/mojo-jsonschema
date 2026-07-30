"""Validator classes with jsonschema-compatible names and call patterns."""

from __future__ import annotations

from fractions import Fraction
import re

from ._batch import FlatSchema
from ._types import draft4_type_checker, draft202012_type_checker
from .exceptions import (
    FormatError,
    RefResolutionError,
    SchemaError,
    UndefinedTypeCheck,
    ValidationError,
)

_TYPE_NAMES = frozenset(
    {"null", "boolean", "object", "array", "number", "integer", "string"}
)


def _equal(left, right):
    if isinstance(left, bool) != isinstance(right, bool):
        if isinstance(left, (bool, int, float)) and isinstance(
            right, (bool, int, float)
        ):
            return False
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _equal(left[key], right[key]) for key in left
        )
    return left == right


def _unique(values):
    return not any(
        _equal(values[left], values[right])
        for left in range(len(values))
        for right in range(left)
    )


def _quoted(value):
    return repr(value)


def _resolve_pointer(document, reference):
    if reference == "#":
        return document
    if not reference.startswith("#"):
        raise RefResolutionError(
            f"Only local references are supported, not {reference!r}"
        )
    fragment = reference[1:]
    if fragment and not fragment.startswith("/"):
        anchor = fragment
        stack = [document]
        while stack:
            candidate = stack.pop()
            if isinstance(candidate, dict):
                if candidate.get("$anchor") == anchor:
                    return candidate
                stack.extend(candidate.values())
            elif isinstance(candidate, list):
                stack.extend(candidate)
        raise RefResolutionError(f"Unresolvable anchor: {reference!r}")
    value = document
    if fragment:
        for raw in fragment[1:].split("/"):
            token = raw.replace("~1", "/").replace("~0", "~")
            try:
                value = value[int(token)] if isinstance(value, list) else value[token]
            except (KeyError, IndexError, ValueError, TypeError) as error:
                raise RefResolutionError(
                    f"Unresolvable JSON pointer: {reference!r}"
                ) from error
    return value


def _schema_error(message, schema, path=(), validator=None, value=None):
    return SchemaError(
        message,
        validator=validator,
        validator_value=value,
        instance=schema,
        schema={},
        path=path,
        schema_path=path,
    )


def _check_schema(schema, path=()):
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise _schema_error(
            f"{schema!r} is not of type 'object', 'boolean'", schema, path
        )
    for keyword, value in schema.items():
        current = (*path, keyword)
        if keyword == "type":
            types = [value] if isinstance(value, str) else value
            if (
                not isinstance(types, list)
                or not types
                or any(type_name not in _TYPE_NAMES for type_name in types)
                or len(set(types)) != len(types)
            ):
                raise _schema_error(
                    f"{value!r} is not a valid JSON Schema type",
                    schema,
                    current,
                    keyword,
                    value,
                )
        elif keyword in {
            "properties",
            "patternProperties",
            "$defs",
            "definitions",
            "dependentSchemas",
        }:
            if not isinstance(value, dict):
                raise _schema_error(
                    f"{value!r} is not of type 'object'",
                    schema,
                    current,
                    keyword,
                    value,
                )
            for name, subschema in value.items():
                _check_schema(subschema, (*current, name))
        elif keyword in {
            "additionalProperties",
            "additionalItems",
            "contains",
            "items",
            "not",
            "if",
            "then",
            "else",
            "propertyNames",
        }:
            if keyword == "items" and isinstance(value, list):
                for index, subschema in enumerate(value):
                    _check_schema(subschema, (*current, index))
            else:
                _check_schema(value, current)
        elif keyword == "prefixItems" or keyword in {"allOf", "anyOf", "oneOf"}:
            if not isinstance(value, list) or (
                keyword != "prefixItems" and not value
            ):
                raise _schema_error(
                    f"{value!r} is not a non-empty array of schemas",
                    schema,
                    current,
                    keyword,
                    value,
                )
            for index, subschema in enumerate(value):
                _check_schema(subschema, (*current, index))
        elif keyword in {"required"}:
            if (
                not isinstance(value, list)
                or any(not isinstance(item, str) for item in value)
                or len(set(value)) != len(value)
            ):
                raise _schema_error(
                    f"{value!r} is not an array of unique strings",
                    schema,
                    current,
                    keyword,
                    value,
                )
        elif keyword == "dependentRequired":
            if not isinstance(value, dict) or any(
                not isinstance(deps, list)
                or any(not isinstance(dep, str) for dep in deps)
                or len(set(deps)) != len(deps)
                for deps in value.values()
            ):
                raise _schema_error(
                    f"{value!r} is not an object of string arrays",
                    schema,
                    current,
                    keyword,
                    value,
                )
        elif keyword in {
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "minProperties",
            "maxProperties",
            "minContains",
            "maxContains",
        }:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise _schema_error(
                    f"{value!r} is not a non-negative integer",
                    schema,
                    current,
                    keyword,
                    value,
                )
        elif keyword in {
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
        }:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise _schema_error(
                    f"{value!r} is not a number",
                    schema,
                    current,
                    keyword,
                    value,
                )
        elif keyword == "multipleOf":
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value <= 0
            ):
                raise _schema_error(
                    f"{value!r} is not greater than 0",
                    schema,
                    current,
                    keyword,
                    value,
                )
        elif keyword == "pattern":
            try:
                re.compile(value)
            except (TypeError, re.error) as error:
                raise _schema_error(
                    f"{value!r} is not a valid regular expression",
                    schema,
                    current,
                    keyword,
                    value,
                ) from error


def _check_schema_draft4(schema, path=()):
    if isinstance(schema, bool) or not isinstance(schema, dict):
        raise _schema_error(f"{schema!r} is not of type 'object'", schema, path)
    for keyword, value in schema.items():
        current = (*path, keyword)
        if keyword in {"exclusiveMinimum", "exclusiveMaximum"}:
            if not isinstance(value, bool):
                raise _schema_error(
                    f"{value!r} is not of type 'boolean'",
                    schema,
                    current,
                    keyword,
                    value,
                )
            continue
        if keyword == "required" and value == []:
            raise _schema_error(
                "[] should be non-empty",
                schema,
                current,
                "minItems",
                value,
            )
        if keyword in {
            "properties",
            "patternProperties",
            "definitions",
        } and isinstance(value, dict):
            for name, subschema in value.items():
                _check_schema_draft4(subschema, (*current, name))
            continue
        if keyword in {
            "additionalProperties",
            "additionalItems",
            "not",
        }:
            if isinstance(value, dict):
                _check_schema_draft4(value, current)
            continue
        if keyword == "items":
            schemas = value if isinstance(value, list) else [value]
            for index, subschema in enumerate(schemas):
                _check_schema_draft4(
                    subschema,
                    (*current, index) if isinstance(value, list) else current,
                )
            continue
        if keyword in {"allOf", "anyOf", "oneOf"}:
            for index, subschema in enumerate(value):
                _check_schema_draft4(subschema, (*current, index))
            continue
    normalized = _normalize_draft4(schema)
    _check_schema(normalized, path)


def _normalize_draft4(schema):
    result = {}
    for key, value in schema.items():
        if key in {"exclusiveMinimum", "exclusiveMaximum"}:
            continue
        if key in {"properties", "patternProperties", "definitions"} and isinstance(
            value, dict
        ):
            result[key] = {
                name: _normalize_draft4(subschema)
                for name, subschema in value.items()
                if isinstance(subschema, dict)
            }
        elif key in {"additionalProperties", "additionalItems", "not"} and isinstance(
            value, dict
        ):
            result[key] = _normalize_draft4(value)
        elif key == "items" and isinstance(value, dict):
            result[key] = _normalize_draft4(value)
        elif key == "items" and isinstance(value, list):
            result[key] = [
                _normalize_draft4(subschema) for subschema in value
            ]
        elif key in {"allOf", "anyOf", "oneOf"} and isinstance(value, list):
            result[key] = [
                _normalize_draft4(subschema) for subschema in value
            ]
        else:
            result[key] = value
    return result


class _Validator:
    META_SCHEMA = {"$schema": ""}
    TYPE_CHECKER = draft202012_type_checker
    FORMAT_CHECKER = None
    VALIDATORS = {}
    ID_OF = staticmethod(lambda schema: schema.get("$id", "") if isinstance(schema, dict) else "")
    _draft = "2020-12"

    def __init__(
        self,
        schema,
        resolver=None,
        format_checker=None,
        *,
        registry=None,
        _resolver=None,
    ):
        self.schema = schema
        self._root_schema = schema
        self.resolver = resolver
        self.format_checker = format_checker
        self.registry = registry
        self._resolver = _resolver
        self._batch_schema = None

    @classmethod
    def check_schema(cls, schema, format_checker=None):
        _check_schema(schema)

    def evolve(self, **changes):
        options = {
            "schema": self.schema,
            "resolver": self.resolver,
            "format_checker": self.format_checker,
            "registry": self.registry,
            "_resolver": self._resolver,
        }
        options.update(changes)
        return self.__class__(**options)

    def is_type(self, instance, type):
        return self.TYPE_CHECKER.is_type(instance, type)

    def _error(
        self,
        message,
        validator,
        validator_value,
        instance,
        schema,
        path,
        schema_path,
        context=(),
        cause=None,
    ):
        return ValidationError(
            message,
            validator=validator,
            validator_value=validator_value,
            instance=instance,
            schema=schema,
            path=path,
            schema_path=schema_path,
            context=context,
            cause=cause,
            type_checker=self.TYPE_CHECKER,
        )

    def _valid(self, instance, schema):
        return next(self._iter(instance, schema, (), ()), None) is None

    def _iter(self, instance, schema, path, schema_path):
        if schema is False:
            yield self._error(
                f"False schema does not allow {_quoted(instance)}",
                None,
                None,
                instance,
                schema,
                path,
                schema_path,
            )
            return
        if schema is True:
            return

        if "$ref" in schema:
            reference = schema["$ref"]
            target = _resolve_pointer(self._root_schema, reference)
            yield from self._iter(
                instance, target, path, (*schema_path, "$ref")
            )
            if self._draft in {"3", "4", "6", "7"}:
                return

        for keyword, value in schema.items():
            if keyword == "$ref":
                continue
            key_path = (*schema_path, keyword)

            if keyword == "type":
                types = [value] if isinstance(value, str) else value
                try:
                    valid_type = any(self.is_type(instance, type) for type in types)
                except UndefinedTypeCheck:
                    valid_type = False
                if not valid_type:
                    names = (
                        repr(value)
                        if isinstance(value, str)
                        else ", ".join(repr(type) for type in value)
                    )
                    yield self._error(
                        f"{_quoted(instance)} is not of type {names}",
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                    )

            elif keyword == "enum" and not any(
                _equal(instance, option) for option in value
            ):
                yield self._error(
                    f"{_quoted(instance)} is not one of {value!r}",
                    keyword,
                    value,
                    instance,
                    schema,
                    path,
                    key_path,
                )

            elif keyword == "const" and self._draft != "4" and not _equal(
                instance, value
            ):
                yield self._error(
                    f"{value!r} was expected",
                    keyword,
                    value,
                    instance,
                    schema,
                    path,
                    key_path,
                )

            elif keyword in {
                "minimum",
                "maximum",
                "exclusiveMinimum",
                "exclusiveMaximum",
                "multipleOf",
            } and self.is_type(instance, "number"):
                failed = False
                message = ""
                if keyword == "minimum":
                    exclusive = self._draft == "4" and schema.get(
                        "exclusiveMinimum"
                    ) is True
                    failed = instance <= value if exclusive else instance < value
                    relation = "less than or equal to" if exclusive else "less than"
                    message = f"{instance!r} is {relation} the minimum of {value!r}"
                elif keyword == "maximum":
                    exclusive = self._draft == "4" and schema.get(
                        "exclusiveMaximum"
                    ) is True
                    failed = instance >= value if exclusive else instance > value
                    relation = (
                        "greater than or equal to" if exclusive else "greater than"
                    )
                    message = f"{instance!r} is {relation} the maximum of {value!r}"
                elif keyword == "exclusiveMinimum" and self._draft != "4":
                    failed = instance <= value
                    message = (
                        f"{instance!r} is less than or equal to the minimum of {value!r}"
                    )
                elif keyword == "exclusiveMaximum" and self._draft != "4":
                    failed = instance >= value
                    message = (
                        f"{instance!r} is greater than or equal to the maximum of {value!r}"
                    )
                elif keyword == "multipleOf":
                    if isinstance(value, float):
                        quotient = instance / value
                        try:
                            failed = int(quotient) != quotient
                        except (OverflowError, ValueError):
                            failed = (
                                Fraction(instance) / Fraction(value)
                            ).denominator != 1
                    else:
                        failed = bool(instance % value)
                    message = f"{instance!r} is not a multiple of {value!r}"
                if failed:
                    yield self._error(
                        message,
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                    )

            elif (
                keyword in {"minLength", "maxLength", "pattern"}
                and self.is_type(instance, "string")
                or keyword == "format"
            ):
                failed = False
                cause = None
                if keyword == "minLength":
                    failed = len(instance) < value
                    message = f"{instance!r} is too short"
                elif keyword == "maxLength":
                    failed = len(instance) > value
                    message = f"{instance!r} is too long"
                elif keyword == "pattern":
                    failed = re.search(value, instance) is None
                    message = f"{instance!r} does not match {value!r}"
                else:
                    if self.format_checker is not None:
                        try:
                            self.format_checker.check(instance, value)
                        except FormatError as error:
                            failed = True
                            cause = error.cause
                    message = f"{instance!r} is not a {value!r}"
                if failed:
                    yield self._error(
                        message,
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                        cause=cause,
                    )

            elif keyword in {
                "minItems",
                "maxItems",
                "uniqueItems",
                "prefixItems",
                "items",
                "additionalItems",
                "contains",
            } and self.is_type(instance, "array"):
                if keyword == "minItems" and len(instance) < value:
                    yield self._error(
                        f"{instance!r} is too short",
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                    )
                elif keyword == "maxItems" and len(instance) > value:
                    yield self._error(
                        f"{instance!r} is too long",
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                    )
                elif keyword == "uniqueItems" and value and not _unique(instance):
                    yield self._error(
                        f"{instance!r} has non-unique elements",
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                    )
                elif keyword == "prefixItems" and self._draft == "2020-12":
                    for index, subschema in enumerate(value):
                        if index >= len(instance):
                            break
                        yield from self._iter(
                            instance[index],
                            subschema,
                            (*path, index),
                            (*key_path, index),
                        )
                elif keyword == "items":
                    if self._draft == "2020-12":
                        start = len(schema.get("prefixItems", ()))
                        if isinstance(value, (dict, bool)):
                            for index in range(start, len(instance)):
                                yield from self._iter(
                                    instance[index],
                                    value,
                                    (*path, index),
                                    key_path,
                                )
                    elif isinstance(value, list):
                        for index, subschema in enumerate(value):
                            if index >= len(instance):
                                break
                            yield from self._iter(
                                instance[index],
                                subschema,
                                (*path, index),
                                (*key_path, index),
                            )
                    else:
                        for index, item in enumerate(instance):
                            yield from self._iter(
                                item, value, (*path, index), key_path
                            )
                elif (
                    keyword == "additionalItems"
                    and self._draft != "2020-12"
                    and isinstance(schema.get("items"), list)
                ):
                    start = len(schema["items"])
                    if value is False and len(instance) > start:
                        extras = instance[start:]
                        yield self._error(
                            f"Additional items are not allowed ({extras!r} were unexpected)",
                            keyword,
                            value,
                            instance,
                            schema,
                            path,
                            key_path,
                        )
                    elif value is not True:
                        for index in range(start, len(instance)):
                            yield from self._iter(
                                instance[index],
                                value,
                                (*path, index),
                                key_path,
                            )
                elif keyword == "contains":
                    matches = sum(self._valid(item, value) for item in instance)
                    minimum = (
                        schema.get("minContains", 1)
                        if self._draft in {"2020-12", "2019-09"}
                        else 1
                    )
                    maximum = (
                        schema.get("maxContains")
                        if self._draft in {"2020-12", "2019-09"}
                        else None
                    )
                    if matches < minimum or (
                        maximum is not None and matches > maximum
                    ):
                        failure_keyword = (
                            "maxContains"
                            if maximum is not None and matches > maximum
                            else "contains"
                            if minimum == 1
                            else "minContains"
                        )
                        if maximum is not None and matches > maximum:
                            message = (
                                f"Too many items match the given schema "
                                f"(expected at most {maximum})"
                            )
                        elif minimum == 1:
                            message = (
                                f"{instance!r} does not contain items matching "
                                "the given schema"
                            )
                        else:
                            message = (
                                f"Too few items match the given schema "
                                f"(expected at least {minimum} but only {matches} matched)"
                            )
                        yield self._error(
                            message,
                            failure_keyword,
                            schema.get(failure_keyword, value),
                            instance,
                            schema,
                            path,
                            key_path,
                        )

            elif keyword in {
                "minProperties",
                "maxProperties",
                "required",
                "properties",
                "patternProperties",
                "additionalProperties",
                "propertyNames",
                "dependentRequired",
                "dependentSchemas",
                "dependencies",
            } and self.is_type(instance, "object"):
                if keyword == "minProperties" and len(instance) < value:
                    yield self._error(
                        f"{instance!r} does not have enough properties",
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                    )
                elif keyword == "maxProperties" and len(instance) > value:
                    yield self._error(
                        f"{instance!r} has too many properties",
                        keyword,
                        value,
                        instance,
                        schema,
                        path,
                        key_path,
                    )
                elif keyword == "required":
                    for name in value:
                        if name not in instance:
                            yield self._error(
                                f"{name!r} is a required property",
                                keyword,
                                value,
                                instance,
                                schema,
                                path,
                                key_path,
                            )
                elif keyword == "properties":
                    for name, subschema in value.items():
                        if name in instance:
                            yield from self._iter(
                                instance[name],
                                subschema,
                                (*path, name),
                                (*key_path, name),
                            )
                elif keyword == "patternProperties":
                    for pattern, subschema in value.items():
                        for name, child in instance.items():
                            if re.search(pattern, name):
                                yield from self._iter(
                                    child,
                                    subschema,
                                    (*path, name),
                                    (*key_path, pattern),
                                )
                elif keyword == "additionalProperties":
                    properties = set(schema.get("properties", ()))
                    patterns = tuple(schema.get("patternProperties", ()))
                    extras = [
                        name
                        for name in instance
                        if name not in properties
                        and not any(re.search(pattern, name) for pattern in patterns)
                    ]
                    if value is False and extras:
                        unexpected = ", ".join(repr(name) for name in sorted(extras))
                        yield self._error(
                            f"Additional properties are not allowed ({unexpected} unexpected)",
                            keyword,
                            value,
                            instance,
                            schema,
                            path,
                            key_path,
                        )
                    elif value is not True:
                        for name in extras:
                            yield from self._iter(
                                instance[name],
                                value,
                                (*path, name),
                                key_path,
                            )
                elif keyword == "propertyNames":
                    for name in instance:
                        yield from self._iter(
                            name, value, path, key_path
                        )
                elif keyword == "dependentRequired":
                    for trigger, dependencies in value.items():
                        if trigger in instance:
                            for dependency in dependencies:
                                if dependency not in instance:
                                    yield self._error(
                                        f"{dependency!r} is a dependency of {trigger!r}",
                                        keyword,
                                        value,
                                        instance,
                                        schema,
                                        path,
                                        key_path,
                                    )
                elif keyword == "dependentSchemas":
                    for trigger, subschema in value.items():
                        if trigger in instance:
                            yield from self._iter(
                                instance,
                                subschema,
                                path,
                                (*key_path, trigger),
                            )
                elif keyword == "dependencies" and self._draft in {"4", "6", "7"}:
                    for trigger, dependency in value.items():
                        if trigger not in instance:
                            continue
                        if isinstance(dependency, list):
                            for name in dependency:
                                if name not in instance:
                                    yield self._error(
                                        f"{name!r} is a dependency of {trigger!r}",
                                        keyword,
                                        dependency,
                                        instance,
                                        schema,
                                        path,
                                        (*key_path, trigger),
                                    )
                        else:
                            yield from self._iter(
                                instance,
                                dependency,
                                path,
                                (*key_path, trigger),
                            )

            elif keyword in {"allOf", "anyOf", "oneOf"}:
                if keyword == "allOf":
                    for index, subschema in enumerate(value):
                        yield from self._iter(
                            instance,
                            subschema,
                            path,
                            (*key_path, index),
                        )
                else:
                    branch_errors = []
                    valid_branches = []
                    for index, subschema in enumerate(value):
                        errors = list(
                            self._iter(
                                instance,
                                subschema,
                                (),
                                (index,),
                            )
                        )
                        if errors:
                            branch_errors.extend(errors)
                        else:
                            valid_branches.append(subschema)
                    failed = (
                        not valid_branches
                        if keyword == "anyOf"
                        else len(valid_branches) != 1
                    )
                    if failed:
                        if not valid_branches:
                            message = (
                                f"{instance!r} is not valid under any of the given schemas"
                            )
                            context = branch_errors
                        else:
                            message = (
                                f"{instance!r} is valid under each of "
                                f"{valid_branches!r}"
                            )
                            context = ()
                        yield self._error(
                            message,
                            keyword,
                            value,
                            instance,
                            schema,
                            path,
                            key_path,
                            context=context,
                        )

            elif keyword == "not" and self._valid(instance, value):
                yield self._error(
                    f"{instance!r} should not be valid under {value!r}",
                    keyword,
                    value,
                    instance,
                    schema,
                    path,
                    key_path,
                )

            elif keyword == "if":
                branch = schema.get("then") if self._valid(instance, value) else schema.get("else")
                branch_name = "then" if self._valid(instance, value) else "else"
                if branch is not None:
                    yield from self._iter(
                        instance,
                        branch,
                        path,
                        (*schema_path, branch_name),
                    )

    def iter_errors(self, instance, _schema=None):
        schema = self.schema if _schema is None else _schema
        old_root = self._root_schema
        if _schema is None:
            self._root_schema = self.schema
        try:
            yield from self._iter(instance, schema, (), ())
        finally:
            self._root_schema = old_root

    def validate(self, *args, **kwargs):
        error = next(self.iter_errors(*args, **kwargs), None)
        if error is not None:
            raise error

    def is_valid(self, instance, _schema=None):
        return next(self.iter_errors(instance, _schema), None) is None

    def descend(
        self,
        instance,
        schema,
        path=None,
        schema_path=None,
        resolver=None,
    ):
        yield from self._iter(
            instance,
            schema,
            () if path is None else (path,),
            () if schema_path is None else (schema_path,),
        )

    def is_valid_many(self, instances):
        rows = instances if isinstance(instances, list) else list(instances)
        if self._batch_schema is None:
            self._batch_schema = (
                FlatSchema.compile(self.schema, self.format_checker) or False
                if self._draft == "2020-12"
                else False
            )
        if self._batch_schema:
            result = self._batch_schema.validate(rows)
            if result is not None:
                return result
        return [self.is_valid(instance) for instance in rows]

    def iter_errors_many(self, instances):
        rows = list(instances)
        validity = self.is_valid_many(rows)
        for index, (instance, valid) in enumerate(zip(rows, validity)):
            if not valid:
                for error in self.iter_errors(instance):
                    yield index, error


class Draft202012Validator(_Validator):
    _draft = "2020-12"
    META_SCHEMA = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://json-schema.org/draft/2020-12/schema",
    }


class Draft201909Validator(Draft202012Validator):
    _draft = "2019-09"
    META_SCHEMA = {
        "$schema": "https://json-schema.org/draft/2019-09/schema",
        "$id": "https://json-schema.org/draft/2019-09/schema",
    }


class Draft7Validator(_Validator):
    _draft = "7"
    META_SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "http://json-schema.org/draft-07/schema#",
    }


class Draft6Validator(Draft7Validator):
    _draft = "6"
    META_SCHEMA = {
        "$schema": "http://json-schema.org/draft-06/schema#",
        "$id": "http://json-schema.org/draft-06/schema#",
    }


class Draft4Validator(Draft7Validator):
    _draft = "4"
    TYPE_CHECKER = draft4_type_checker
    META_SCHEMA = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "id": "http://json-schema.org/draft-04/schema#",
    }

    @classmethod
    def check_schema(cls, schema, format_checker=None):
        if isinstance(schema, bool):
            raise _schema_error(
                f"{schema!r} is not of type 'object'", schema
            )
        _check_schema_draft4(schema)


_VALIDATORS = {
    "https://json-schema.org/draft/2020-12/schema": Draft202012Validator,
    "https://json-schema.org/draft/2019-09/schema": Draft201909Validator,
    "http://json-schema.org/draft-07/schema#": Draft7Validator,
    "http://json-schema.org/draft-06/schema#": Draft6Validator,
    "http://json-schema.org/draft-04/schema#": Draft4Validator,
}


def validator_for(schema, default=Draft202012Validator):
    if isinstance(schema, dict):
        identifier = schema.get("$schema")
        if identifier:
            normalized = identifier.rstrip("#")
            for uri, validator in _VALIDATORS.items():
                if uri.rstrip("#") == normalized:
                    return validator
    return default
