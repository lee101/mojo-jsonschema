from __future__ import annotations

from collections import Counter
import math
import random

import pytest

upstream = pytest.importorskip("jsonschema")
import mojojsonschema as mjs
from mojojsonschema import exceptions, validators
from mojojsonschema._lib import lib


CASES_202012 = [
    (True, [None, 1, "x", [], {}]),
    (False, [None, 1, "x"]),
    ({"type": "null"}, [None, 0, False]),
    ({"type": "boolean"}, [True, False, 0, 1]),
    ({"type": "integer"}, [1, 1.0, 1.5, True, "1"]),
    ({"type": "number"}, [1, 2.5, True, "2"]),
    ({"type": "string"}, ["x", "", 1]),
    ({"type": "array"}, [[], [1], (), {}]),
    ({"type": "object"}, [{}, {"x": 1}, [], None]),
    ({"type": ["string", "null"]}, ["x", None, 4]),
    ({"enum": [None, 1, True, {"x": [1, False]}]}, [None, 1, True, False, {"x": [1, False]}]),
    ({"const": {"x": [1, False]}}, [{"x": [1, False]}, {"x": [1, 0]}]),
    ({"minimum": 2}, [1, 2, 3, "1"]),
    ({"maximum": 2}, [1, 2, 3]),
    ({"exclusiveMinimum": 2}, [2, 2.1, 1]),
    ({"exclusiveMaximum": 2}, [2, 1.9, 3]),
    ({"multipleOf": 0.1}, [0.2, 0.3, 1.0, "0.3"]),
    ({"minLength": 2}, ["", "a", "éx", 3]),
    ({"maxLength": 2}, ["ab", "abc", "xy", None]),
    ({"pattern": r"^[A-Z][0-9]+$"}, ["A12", "xA12", "A", 1]),
    ({"minItems": 2, "maxItems": 3}, [[], [1], [1, 2], [1, 2, 3, 4]]),
    ({"uniqueItems": True}, [[1, 2], [1, 1], [1, True], [{"x": 1}, {"x": 1}]]),
    ({"prefixItems": [{"type": "integer"}, {"type": "string"}]}, [[1, "x"], ["1", "x"], [1, 2], [1]]),
    ({"prefixItems": [{"type": "integer"}], "items": {"type": "string"}}, [[1, "a", "b"], [1, 2], []]),
    ({"contains": {"type": "integer"}}, [[], ["x"], ["x", 2], [True]]),
    ({"contains": {"type": "integer"}, "minContains": 2, "maxContains": 3}, [[1], [1, 2], [1, 2, 3, 4], ["x", 2, 3]]),
    ({"minProperties": 1, "maxProperties": 2}, [{}, {"a": 1}, {"a": 1, "b": 2, "c": 3}]),
    ({"required": ["a", "b"]}, [{}, {"a": 1}, {"a": 1, "b": None}]),
    ({"properties": {"age": {"type": "integer", "minimum": 0}}}, [{"age": 3}, {"age": -1}, {"age": "3"}, {}]),
    ({"patternProperties": {r"^S_": {"type": "string"}}}, [{"S_x": "ok"}, {"S_x": 2}, {"x": 2}]),
    ({"properties": {"x": True}, "additionalProperties": False}, [{"x": 1}, {"y": 1}, {}]),
    ({"additionalProperties": {"type": "integer"}}, [{"x": 1}, {"x": "bad"}, {}]),
    ({"propertyNames": {"pattern": r"^[a-z]+$"}}, [{"ok": 1}, {"Bad": 1}, {}]),
    ({"dependentRequired": {"credit_card": ["billing_address"]}}, [{"credit_card": 1}, {"credit_card": 1, "billing_address": "x"}, {}]),
    ({"dependentSchemas": {"x": {"required": ["y"]}}}, [{"x": 1}, {"x": 1, "y": 2}, {}]),
    ({"allOf": [{"type": "integer"}, {"minimum": 2}]}, [1, 2, "2"]),
    ({"anyOf": [{"type": "integer"}, {"type": "string", "minLength": 2}]}, [1, "ab", "a", []]),
    ({"oneOf": [{"type": "number"}, {"type": "integer"}]}, [1, 1.5, "x"]),
    ({"not": {"type": "null"}}, [None, 1]),
    ({"if": {"properties": {"kind": {"const": "x"}}, "required": ["kind"]}, "then": {"required": ["x"]}, "else": {"required": ["y"]}}, [{"kind": "x"}, {"kind": "x", "x": 1}, {"kind": "z"}, {"kind": "z", "y": 1}]),
    ({"$defs": {"positive": {"type": "number", "exclusiveMinimum": 0}}, "$ref": "#/$defs/positive"}, [-1, 0, 1]),
    ({"$defs": {"named": {"$anchor": "named", "type": "string"}}, "$ref": "#named"}, ["ok", 3]),
]


def error_signature(validator, instance):
    return Counter(
        (error.validator, tuple(error.path))
        for error in validator.iter_errors(instance)
    )


@pytest.mark.parametrize(("schema", "instances"), CASES_202012)
def test_draft202012_parity(schema, instances):
    ours = mjs.Draft202012Validator(schema)
    theirs = upstream.Draft202012Validator(schema)
    for instance in instances:
        assert ours.is_valid(instance) == theirs.is_valid(instance)
        assert error_signature(ours, instance) == error_signature(theirs, instance)


@pytest.mark.parametrize(
    ("schema", "instances"),
    [
        ({"items": [{"type": "integer"}, {"type": "string"}]}, [[1, "x"], [1, 2], ["1", "x"]]),
        ({"items": [{"type": "integer"}], "additionalItems": False}, [[1], [1, 2], []]),
        ({"dependencies": {"x": ["y"]}}, [{"x": 1}, {"x": 1, "y": 2}, {}]),
        ({"$ref": "#/definitions/n", "minimum": 10, "definitions": {"n": {"type": "number"}}}, [2, "x"]),
    ],
)
def test_draft7_parity(schema, instances):
    ours = mjs.Draft7Validator(schema)
    theirs = upstream.Draft7Validator(schema)
    for instance in instances:
        assert ours.is_valid(instance) == theirs.is_valid(instance)
        assert error_signature(ours, instance) == error_signature(theirs, instance)


@pytest.mark.parametrize(
    ("schema", "instances"),
    [
        ({"type": "integer"}, [1, 1.0, 1.5, True]),
        ({"minimum": 2, "exclusiveMinimum": True}, [1, 2, 3]),
        ({"maximum": 2, "exclusiveMaximum": True}, [1, 2, 3]),
        ({"definitions": {"x": {"type": "string"}}, "$ref": "#/definitions/x"}, ["x", 1]),
    ],
)
def test_draft4_parity(schema, instances):
    ours = mjs.Draft4Validator(schema)
    theirs = upstream.Draft4Validator(schema)
    for instance in instances:
        assert ours.is_valid(instance) == theirs.is_valid(instance)
        assert error_signature(ours, instance) == error_signature(theirs, instance)


def test_draft4_schema_rules():
    mjs.Draft4Validator.check_schema(
        {"minimum": 1, "exclusiveMinimum": True}
    )
    for schema in (True, {"required": []}):
        with pytest.raises(mjs.SchemaError):
            mjs.Draft4Validator.check_schema(schema)


def test_draft201909_contains_counts_and_ref_siblings():
    schema = {
        "contains": {"type": "integer"},
        "minContains": 2,
        "maxContains": 2,
    }
    ours = mjs.Draft201909Validator(schema)
    theirs = upstream.Draft201909Validator(schema)
    for instance in ([1], [1, 2], [1, 2, 3]):
        assert ours.is_valid(instance) == theirs.is_valid(instance)
    ref_schema = {
        "$defs": {"n": {"type": "number"}},
        "$ref": "#/$defs/n",
        "minimum": 3,
    }
    for instance in (2, 3, "x"):
        assert mjs.Draft201909Validator(ref_schema).is_valid(instance) == (
            upstream.Draft201909Validator(ref_schema).is_valid(instance)
        )


def test_draft6_parity():
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer", "exclusiveMinimum": 0}},
        "dependencies": {"count": ["unit"]},
    }
    ours = mjs.Draft6Validator(schema)
    theirs = upstream.Draft6Validator(schema)
    for instance in (
        {"count": 1, "unit": "items"},
        {"count": 0, "unit": "items"},
        {"count": 1},
        {},
    ):
        assert ours.is_valid(instance) == theirs.is_valid(instance)
        assert error_signature(ours, instance) == error_signature(theirs, instance)


def test_structured_error_attributes_match():
    schema = {
        "type": "object",
        "properties": {"age": {"type": "integer", "minimum": 0}},
        "required": ["age"],
    }
    ours = next(mjs.Draft202012Validator(schema).iter_errors({"age": -1}))
    theirs = next(upstream.Draft202012Validator(schema).iter_errors({"age": -1}))
    assert ours.validator == theirs.validator == "minimum"
    assert ours.validator_value == theirs.validator_value == 0
    assert ours.instance == theirs.instance == -1
    assert list(ours.path) == list(theirs.path) == ["age"]
    assert list(ours.schema_path) == list(theirs.schema_path)
    assert ours.json_path == theirs.json_path == "$.age"


def test_anyof_context_matches_upstream_shape():
    schema = {"anyOf": [{"type": "string"}, {"minimum": 2}]}
    ours = next(mjs.Draft202012Validator(schema).iter_errors(1))
    theirs = next(upstream.Draft202012Validator(schema).iter_errors(1))
    assert ours.validator == theirs.validator == "anyOf"
    assert [(e.validator, list(e.schema_path)) for e in ours.context] == [
        (e.validator, list(e.schema_path)) for e in theirs.context
    ]
    assert all(error.parent is ours for error in ours.context)


def test_validate_and_schema_error_contracts():
    mjs.validate({"x": 1}, {"properties": {"x": {"type": "integer"}}})
    with pytest.raises(mjs.ValidationError) as caught:
        mjs.validate({"x": "bad"}, {"properties": {"x": {"type": "integer"}}})
    assert caught.value.validator == "type"
    with pytest.raises(mjs.SchemaError):
        mjs.validate(1, {"type": "not-a-type"})


@pytest.mark.parametrize(
    ("format_name", "values"),
    [
        ("date", ["2024-02-29", "2023-02-29"]),
        ("date-time", ["2024-01-02T03:04:05Z", "2024-01-02T03:04:05", "2024-01-02"]),
        ("ipv4", ["127.0.0.1", "999.0.0.1"]),
        ("ipv6", ["::1", "not-ip"]),
        ("hostname", ["example.com", "-bad.example"]),
        ("uuid", ["123e4567-e89b-12d3-a456-426614174000", "bad"]),
        ("json-pointer", ["/a~1b/0", "/bad~x"]),
        ("regex", [r"^[a-z]+$", "["]),
        ("email", ["a@b", "a@", "a"]),
        ("time", ["03:04:05", "03:04:05Z"]),
    ],
)
def test_format_checker_parity(format_name, values):
    schema = {"type": "string", "format": format_name}
    ours = mjs.Draft202012Validator(schema, format_checker=mjs.FormatChecker())
    theirs = upstream.Draft202012Validator(
        schema, format_checker=upstream.FormatChecker()
    )
    assert [ours.is_valid(value) for value in values] == [
        theirs.is_valid(value) for value in values
    ]


def test_formats_are_annotations_without_checker():
    schema = {"format": "ipv4"}
    assert mjs.Draft202012Validator(schema).is_valid("not an ip")


def test_builtin_formats_ignore_non_strings_like_upstream():
    ours = mjs.Draft202012Validator(
        {"format": "date"}, format_checker=mjs.FormatChecker()
    )
    theirs = upstream.Draft202012Validator(
        {"format": "date"}, format_checker=upstream.FormatChecker()
    )
    assert ours.is_valid(3) == theirs.is_valid(3) is True


def test_custom_format_checker():
    checker = mjs.FormatChecker([])

    @checker.checks("even")
    def even(value):
        return isinstance(value, int) and value % 2 == 0

    validator = mjs.Draft202012Validator({"format": "even"}, format_checker=checker)
    assert validator.is_valid(2)
    assert not validator.is_valid(3)


def test_type_checker_redefine_is_immutable():
    original = mjs.TypeChecker()
    changed = original.redefine(
        "number", lambda checker, value: isinstance(value, str)
    )
    assert original.is_type(2, "number")
    assert not original.is_type("2", "number")
    assert changed.is_type("2", "number")


def test_validator_for_drafts():
    assert (
        validators.validator_for(
            {"$schema": "https://json-schema.org/draft/2020-12/schema"}
        )
        is mjs.Draft202012Validator
    )
    assert (
        validators.validator_for(
            {"$schema": "http://json-schema.org/draft-07/schema#"}
        )
        is mjs.Draft7Validator
    )


def test_error_tree_and_best_match():
    validator = mjs.Draft202012Validator(
        {"properties": {"x": {"type": "integer"}, "y": {"type": "string"}}}
    )
    errors = list(validator.iter_errors({"x": "bad", "y": 2}))
    tree = exceptions.ErrorTree(errors)
    assert tree.total_errors == 2
    assert "x" in tree and "type" in tree["x"].errors
    assert exceptions.best_match(errors) in errors


def test_evolve_and_descend():
    validator = mjs.Draft202012Validator({"type": "integer"})
    evolved = validator.evolve(schema={"type": "string"})
    assert evolved.is_valid("x") and not evolved.is_valid(1)
    error = next(validator.descend("x", {"type": "integer"}, path="field"))
    assert list(error.path) == ["field"]


def flat_schema():
    return {
        "type": "object",
        "required": ["id", "score", "name"],
        "properties": {
            "id": {"type": "integer", "minimum": 0},
            "score": {
                "type": "number",
                "exclusiveMinimum": 0,
                "maximum": 100,
                "multipleOf": 0.5,
            },
            "name": {
                "type": "string",
                "minLength": 2,
                "maxLength": 12,
                "pattern": r"^[A-Za-z]+$",
            },
            "active": {"type": "boolean"},
        },
        "minProperties": 3,
        "maxProperties": 4,
        "additionalProperties": False,
    }


def test_mojo_batch_matches_upstream_on_random_records():
    rng = random.Random(0)
    rows = []
    for index in range(4000):
        row = {
            "id": index if index % 17 else -index,
            "score": rng.randrange(-5, 205) / 2,
            "name": "Alice" if index % 13 else "x1",
            "active": index % 2 == 0,
        }
        if index % 19 == 0:
            row.pop("name")
        if index % 23 == 0:
            row["extra"] = True
        rows.append(row)
    ours = mjs.Draft202012Validator(flat_schema()).is_valid_many(rows)
    ref = [upstream.Draft202012Validator(flat_schema()).is_valid(row) for row in rows]
    assert ours == ref


def test_batch_format_checker_and_error_recovery():
    schema = {
        "type": "object",
        "properties": {"ip": {"type": "string", "format": "ipv4"}},
        "required": ["ip"],
    }
    rows = [{"ip": "127.0.0.1"}, {"ip": "bad"}]
    validator = mjs.Draft202012Validator(
        schema, format_checker=mjs.FormatChecker()
    )
    assert validator.is_valid_many(rows) == [True, False]
    recovered = list(validator.iter_errors_many(rows))
    assert recovered[0][0] == 1
    assert recovered[0][1].validator == "format"


def test_batch_falls_back_for_nested_schemas_and_large_integers():
    schema = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "object",
                "properties": {"x": {"type": "integer"}},
            }
        },
    }
    rows = [{"payload": {"x": 1}}, {"payload": {"x": "bad"}}]
    assert mjs.Draft202012Validator(schema).is_valid_many(rows) == [True, False]
    numeric = {
        "type": "object",
        "properties": {"x": {"type": "integer", "minimum": 2**60}},
    }
    rows = [{"x": 2**60}, {"x": 2**60 - 1}]
    assert mjs.Draft202012Validator(numeric).is_valid_many(rows) == [True, False]


def test_batch_does_not_narrow_large_schema_numbers():
    schema = {
        "type": "object",
        "properties": {"x": {"type": "number", "minimum": 2**53 + 1}},
    }
    rows = [{"x": 2**53}]
    validator = mjs.Draft202012Validator(schema)
    assert validator.is_valid_many(rows) == [False]
    assert validator._batch_schema is False


def test_native_boundary_rejects_invalid_pointers_and_dimensions():
    assert lib().mjs_validate_flat(*(0 for _ in range(14))) == 1


@pytest.mark.parametrize("count", [19, 262143, 262147])
def test_native_simd_tail_and_parallel_threshold(count):
    schema = {
        "type": "object",
        "required": ["x", "name"],
        "properties": {
            "x": {"type": "number", "minimum": 0, "maximum": 10},
            "name": {"type": "string", "minLength": 2, "maxLength": 4},
        },
    }
    rows = [
        {
            "x": index % 13 - 1,
            "name": "x" if index % 17 == 0 else "ok",
        }
        for index in range(count)
    ]
    expected = [
        row["x"] >= 0 and row["x"] <= 10 and len(row["name"]) >= 2
        for row in rows
    ]
    assert mjs.Draft202012Validator(schema).is_valid_many(rows) == expected


def test_fixed_nested_batch_uses_native_path_and_matches_upstream():
    schema = {
        "type": "object",
        "required": ["payload"],
        "properties": {
            "payload": {
                "type": "object",
                "required": ["samples"],
                "properties": {
                    "samples": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {"type": "number", "minimum": 0},
                    }
                },
            }
        },
    }
    rows = [
        {"payload": {"samples": [1, 2, 3]}},
        {"payload": {"samples": [1, -1, 3]}},
        {"payload": {"samples": [1, 2]}},
        {"payload": {}},
        {},
        {"payload": {"samples": [1, "x", 3]}},
    ]
    validator = mjs.Draft202012Validator(schema)
    assert validator.is_valid_many(rows) == [
        upstream.Draft202012Validator(schema).is_valid(row) for row in rows
    ]
    assert validator._batch_schema is not None


def test_top_level_validate_many():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    assert mjs.validate_many([{"x": 1}, {"x": "bad"}], schema) == [True, False]
