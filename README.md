# mojo-jsonschema

JSON Schema validation with a compiled [Mojo](https://www.modular.com/mojo)
fast path for batches of records. The Python API follows
[`jsonschema`](https://python-jsonschema.readthedocs.io/) for the covered
validator classes, methods, exceptions, and keyword behavior.

```python
import mojojsonschema as jsonschema

schema = {
    "type": "object",
    "required": ["id", "score"],
    "properties": {
        "id": {"type": "integer", "minimum": 0},
        "score": {"type": "number", "minimum": 0, "maximum": 100},
    },
    "additionalProperties": False,
}

jsonschema.validate({"id": 7, "score": 91.5}, schema)

validator = jsonschema.Draft202012Validator(schema)
valid = validator.is_valid_many([
    {"id": 7, "score": 91.5},
    {"id": -1, "score": 120},
])
assert valid == [True, False]
```

`validate`, `Draft202012Validator(...).validate`, `is_valid`, `iter_errors`,
`check_schema`, `evolve`, `descend`, `ValidationError`, `SchemaError`,
`FormatChecker`, `TypeChecker`, and `validators.validator_for` have their
upstream names and call patterns. `is_valid_many`, `iter_errors_many`, and
top-level `validate_many` are additions for batched data.

## Coverage

Draft 2020-12 is the primary target. Draft 2019-09, Draft 7, Draft 6, and
Draft 4 classes cover the corresponding forms of the same validation
keywords, including Draft 4's boolean exclusive bounds and integer semantics,
Draft 7 tuple-form `items`, and pre-2020 `dependencies`.

| area | implemented |
| --- | --- |
| Core | boolean schemas, `$schema`, local JSON Pointer and `$anchor` `$ref`, `$defs` / `definitions` |
| Types and equality | `type`, `enum`, `const`, JSON-aware boolean/numeric equality |
| Numbers | `minimum`, `maximum`, exclusive bounds, `multipleOf` |
| Strings | `minLength`, `maxLength`, `pattern`, `format` |
| Arrays | `prefixItems`, `items`, `additionalItems`, `contains`, `minContains`, `maxContains`, length bounds, `uniqueItems` |
| Objects | `properties`, `patternProperties`, `additionalProperties`, `required`, property-count bounds, `propertyNames`, dependent requirements and schemas |
| Applicators | `allOf`, `anyOf`, `oneOf`, `not`, `if` / `then` / `else` |
| Errors | paths, schema paths, JSON paths, nested context, `best_match`, `ErrorTree` |
| Formats | date/time, email, hostname, IP, UUID, regex, and JSON Pointer checks, plus custom checks |

The test suite compares all of those areas directly with upstream
`jsonschema` 4.x. It includes draft-specific cases, error structure, format
checking, local references, random mixed record batches, large integers, and
native-to-upstream parity.

Not implemented are remote or registry-backed references, `$dynamicRef`,
`$recursiveRef`, vocabulary negotiation, annotation-dependent
`unevaluatedProperties` / `unevaluatedItems`, content decoding, Draft 3, or
upstream's validator-construction extension API. Unknown annotation keywords
are ignored as the specification requires. Schemas outside the native batch
subset still use this project's Python validator; they are not delegated to
the upstream package.

## Install and run

The Pixi environment carries its own pinned Mojo compiler:

```bash
pixi install
pixi run build
pixi run test
pixi run bench
```

`pixi run build` creates `dist/libmojo-jsonschema.so`. Within the repository,
Pixi also puts `python/` on `PYTHONPATH`, so the usage example runs directly:

```bash
pixi run python -c \
  'import mojojsonschema as j; j.validate(3, {"type": "integer"})'
```

The Python package metadata and command-line entry point are in
`pyproject.toml`; the Mojo shared library is built separately by Pixi. A
deployed shared library can be selected with
`MOJOJSONSCHEMA_LIB=/absolute/path/libmojo-jsonschema.so`.

## Benchmarks

Measured with `pixi run bench`, which takes `/tmp/mojo-bench.lock` before
running. Both projects reuse a compiled validator; record construction is
outside the timed section, while conversion into FFI buffers is included.
Times are the best of two runs.

Machine: Intel(R) Xeon(R) CPU E5-2697 v4 @ 2.30GHz; Linux x86_64.

| case | mojo-jsonschema | jsonschema 4.x | result |
| --- | ---: | ---: | ---: |
| flat valid records (100k) | 913.0 ms | 4468.6 ms | 4.89x faster |
| flat mixed records (100k) | 482.3 ms | 5014.6 ms | 10.40x faster |
| nested fixed records (20k) | 300.0 ms | 1946.6 ms | 6.49x faster |

All three rows use the Mojo kernel. The nested case contains required objects
and an exact-size homogeneous array, which the column plan expands into fixed
paths. Run-to-run numbers vary with the machine; `bench/bench.py` verifies
result parity before printing any timing.

## How it works

For a supported object schema, the Python layer compiles every property path
into a fixed rule record: accepted type bits, required flag, numeric bounds,
`multipleOf`, and string or array length bounds. Required nested objects and
exact-size homogeneous arrays are expanded into paths without recursive
validation. A batch is transposed into preallocated property-major buffers:

```text
tags:       int64   [property, record]
numbers:    float64 [property, record]
lengths:    int64   [property, record]
valid:      int64   [record]
```

One `ctypes` call passes those buffers as integer addresses without another
copy. The exported Mojo function reconstructs each pointer with
`AnyOrigin[mut=True]`, checks float64-width SIMD chunks with a scalar remainder,
and writes one validity flag per record. Batches below the native parallel
threshold stay serial; larger batches split disjoint row ranges across
`parallelize` tasks.
Mojo allocates nothing and retains no pointer after the call. Python handles
property extraction, regex and format checks, additional-property names, and
exact error reconstruction.

If a schema uses non-fixed nesting, applicators, references, enums, or another
rule that cannot be represented by that layout, `is_valid_many` automatically
falls back to repeated `is_valid`. Integers beyond float64's exact range also
fall back, preventing a speed optimization from changing validation results.

There is no GPU path. Each property check performs only a handful of
comparisons while moving tags, values or lengths, and validity flags. This is
a memory-bound CPU kernel; the project makes no GPU performance claim.

## License

MIT
