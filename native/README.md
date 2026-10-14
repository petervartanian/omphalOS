# Independent integrity verifiers

The Go and Rust programs independently read omphalOS 2.0 run inventories, compare the complete set of regular files, recompute SHA-256 digests and sizes, check mandatory files and the engine snapshot, and recompute the normalized analysis digest. They reject missing, changed, unlisted, repeated, and malformed inventory entries. They do not execute archived code.

These programs verify a **run directory**, not the outer ZIP bundle. The Python verifier additionally validates the complete application schemas, finding references, review coverage, and bundle export rules. Native success is not a substitute for those checks and does not authenticate a publisher, reviewer, or analytical conclusion.

From the repository root:

```sh
cd native/go
go build -o ../omphalos-verify-go .
cd ../rust
cargo build --release --locked
```

Run the resulting program with one run-directory argument. A verified inventory exits 0; failed validation exits 1; invalid command usage exits 2. Windows builds use the corresponding `.exe` names.

```sh
native/omphalos-verify-go /absolute/path/to/run-directory
native/rust/target/release/omphalos-integrity-verifier /absolute/path/to/run-directory
```

The supported analysis encoding is `omphalos-json-v1`: UTF-8, recursively sorted object keys, compact JSON, and one terminating newline. Decimal values and integers outside signed 64-bit range are strings. Native verifiers do not describe this application encoding as RFC 8785. The cross-language test includes Unicode, HTML characters, and escaped control characters.

Run the shared conformance fixtures after building both programs:

```sh
python -m unittest discover -s tests -p 'test_*evidence.py' -v
```

For programs built elsewhere, set `OMPHALOS_GO_VERIFIER` and `OMPHALOS_RUST_VERIFIER` to their executable paths. The test explicitly skips native checks when neither program is available; such a skip is not evidence of native conformance.

The Go verifier has no third-party dependencies. Rust dependencies are pinned by `Cargo.lock`. Initial builds require installed toolchains and, for Rust, cached or downloadable dependencies; verification itself is offline. Both programs apply limits of 20,000 inventoried files, 256 MiB per file, and 1 GiB total. A local owner can replace a manifest along with its contents, so independent custody or an externally trusted signature is needed to establish more than agreement with the supplied inventory.
