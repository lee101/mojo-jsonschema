"""Minimal command-line validator for JSON files."""

from __future__ import annotations

import argparse
import json

from . import validator_for


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--instance", action="append", required=True)
    parser.add_argument("schema")
    options = parser.parse_args(args)
    with open(options.schema, encoding="utf-8") as stream:
        schema = json.load(stream)
    validator = validator_for(schema)(schema)
    failed = False
    for filename in options.instance:
        with open(filename, encoding="utf-8") as stream:
            instance = json.load(stream)
        for error in validator.iter_errors(instance):
            print(f"{filename}: {error.json_path}: {error.message}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

