# omphalos

A polycentric, offline-first casework suite.

## Objects
- **case**: question + scope + investigation selection
- **run**: materialization + executed investigations + artifacts + checksums
- **packet**: neutral memo + annexes + tables/figures + claims

## Structure
- `src/omphalos/` reference runtime
- `agents/` independent verifiers (Go/Rust/C++)
- `sql/` investigation sources and generated catalog (also shipped as a pack)
- `rules/` regime scaffolds and tests
- `ui/` local analyst UI source
