# Compatibility policy

## Python

Taskprint 0.3 targets CPython 3.10 through 3.13. CI tests all four versions. PyPy and other
interpreters are not yet guaranteed.

## Artifact schemas

- Current trace schema: `taskprint-trace/1.0`
- Current workflow schema: `taskprint/1.0`
- Read compatibility: workflow `taskprint/0.1` is migrated in memory
- Write behavior: Taskprint always writes the current schema

Within a stable `1.x` artifact schema, fields will not be removed or change meaning. New
optional fields may be added. A future incompatible schema will require an explicit migration.

## Python API

Before Python package 1.0, minor versions may make documented breaking API changes, which must
be listed in the changelog. Patch versions must remain backward compatible.
