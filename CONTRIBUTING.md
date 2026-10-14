# Contributing

Use Python 3.11+, Poetry, and the pinned lockfile. Keep the browser free of external runtime dependencies. Code retains CC0-1.0; do not assume imported datasets share that license.

Run `poetry install`, `poetry run pytest`, `poetry run ruff check src tests`, and `poetry run black --check src tests tools`. Build with `poetry build` and smoke-test the installed wheel. Native verifier instructions are in `native/README.md`. CI runs the Python matrix on Linux, macOS, and Windows; do not describe configured jobs as executed until their actual results are known.

Changes to an investigation need semantic fixtures: a positive observation, a benign counterexample, missing prerequisites, exact evidence references, boundary parameters, currencies/units where relevant, scope behavior, and deterministic replay. A golden digest alone is insufficient. Changes to evidence handling need altered/missing/extra/duplicate/unsafe artifact cases.

Record exact provenance, preserve input bytes, and keep identity candidates separate from established facts. No fabricated counts, probabilities, legal clearances, or success flags. Explicitly name not-evaluable states. Review input must remain human-authored; test fixtures must be clearly synthetic.

Use type hints, Pydantic for exchange validation, Black-compatible 88-column formatting, and structured event fields without logging source records or secrets. Keep edits confined to the relevant package, tests, and documentation. Do not commit local workspaces, personal data, live list snapshots, virtual environments, or toolchains.
