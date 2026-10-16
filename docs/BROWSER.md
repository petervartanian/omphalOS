# Browser edition

The browser edition runs the Python investigation engine in a Web Worker using WebAssembly. It can be served as static files under `/omphalos/` on the existing GitHub Pages site, with no paid application server. Runtime files, dependencies, fonts, and application code are served from that same site. The build does not copy local workspaces, examples containing retained investigations, or credentials.

Records and investigation state remain in this browser's IndexedDB storage. The worker restores the filesystem before opening the workspace and saves changes after operations. Browser storage can be cleared or evicted; downloaded evidence packages provide a separate retained copy. Browser persistence and a successful reload are verified in the website, separately from the Node runtime test.

The browser and native guided workflows use the same approval checks. After source retrieval and plan drafting, **Use these sources** accepts II, **Run reviewed plan** authorizes III, and **Mark results reviewed** opens Assessment from IV. The completed run retains its case schema 2.1 source and plan record. Earlier case schema 2.0 runs remain readable without retroactive approval claims. Unsaved review actions and drafts remain temporary until recorded; a workspace backup does not capture an unfinished form.

Use **Open → Download workspace backup** to retain the complete workspace, including saved records, source snapshots, cases, reviews, and exports. **Restore a backup** validates the archive and asks before replacing the current browser workspace. Download the current workspace first when its contents need to be kept. Restoration blocks other actions while it runs and leaves the existing workspace available if validation fails. Evidence packages remain separate, case-specific records.

Workspace backups also preserve work that has not reached assessment or Package. A restore validates the complete file inventory and retained records before replacing this browser's workspace. Its staged replacement can recover an interrupted swap. Backups have a 512 MiB compressed and expanded limit and are private investigation data; their hashes detect changed bytes, not authenticated authorship.

## Build and verify

From the application repository:

```sh
python tools/build_browser.py --output dist/browser
node tools/check_browser_runtime.mjs dist/browser
python -m pytest tests/test_browser_build.py
```

The builder downloads only artifacts pinned in `deploy/browser-runtime.lock.json` and verifies their sizes and SHA-256 hashes, including cached downloads. It uses normal TLS certificate validation; an installed `truststore` package supplies the system certificate store when available. No browser package resolution or third-party runtime CDN is needed after publishing the output.

The build contains approximately 16 MB of files. Its largest individual file is the 9.6 MB WebAssembly runtime. `build-manifest.json` lists every deployment file with its path, byte count, and hash. Publish only these listed files and the build manifest itself. The builder refuses to replace an output directory with unrecognized files. The generated interface uses relative paths, loads the browser bridge before the application, and declares `https://petervartanian.xyz/omphalos/` as its canonical URL.

`runtime/manifest.json` supplies the worker's local runtime path, exact wheel paths and hashes, and the engine ZIP inventory. The ZIP contains the application's Python modules with deterministic timestamps and excludes the hosted-server draft. Each build records the actual code bytes used by the browser engine. Builds made from different source revisions therefore have different engine fingerprints.

## Pinned runtime

| Component | Version |
| --- | --- |
| Pyodide | `314.0.7` |
| CPython in Pyodide | `3.14.2` |
| WebAssembly platform | `pyemscripten_2026_0_wasm32` |
| Pydantic | `2.14.1` |
| Pydantic Core | `2.50.1` |
| annotated-types | `0.8.0` |
| typing-extensions | `4.16.0` |
| typing-inspection | `0.4.4` |

These use the [official Pyodide release](https://github.com/pyodide/pyodide/releases/tag/314.0.7) and the [exact Pydantic Core WebAssembly wheel](https://pypi.org/project/pydantic_core/2.50.1/). The builder derives a restricted Pyodide package lock containing only these five versions, local wheel paths, dependencies, and hashes. The worker calls `pyodide.loadPackage()` by package name with integrity checking enabled, so the browser verifies the downloaded bytes it actually installs. No external package index is consulted. See [Pyodide package loading](https://pyodide.org/en/stable/usage/loading-packages.html).

`tools/check_browser_runtime.mjs` executes this actual WebAssembly runtime under Node with network requests disabled. It independently checks every deployed asset hash, valid and invalid Pydantic input, application schemas, and the subject → source → plan → explicit approvals → run → review → export → verify → replay sequence. It verifies original JavaScript source bytes, reopens the workspace, recovers an approved run, and exercises backup/restore through the JavaScript byte-array bridge. The independent hashes also cover Pyodide's Node loader, which does not enforce browser Fetch integrity. This tests the real Python path; it does not substitute for testing browser IndexedDB, file downloads, provider CORS behavior, or mobile layout.

## Supported boundaries

The normal import, investigation, assessment, unsigned package, hash verification, and replay workflows use the Python engine. Native command-line detached Ed25519 signature verification is not included in the browser runtime. `cryptography` is not silently replaced by an older version, and the recorded environment identifies the installed browser dependencies. A signed package's publisher signature cannot be authenticated by the browser edition without the optional cryptographic verifier; byte-integrity checks and authenticated authorship are separate claims.

Live public lookups are subject to each provider's browser access policy. The browser bridge permits direct requests to the Consolidated Screening List, GLEIF, and Wikidata, with the required Wikidata CORS parameter. OFAC's download endpoint does not currently permit direct cross-origin browser access; its published source file can be downloaded and imported. No third-party CORS proxy is used. Source retrieval sends the requested lookup to its public provider; local record processing does not require an application server.

When changing the runtime, update the pinned lock, rebuild, run the real WebAssembly checks, and test the full browser workflow and reload behavior before publishing. Python and dependency versions are part of replay evidence; do not claim an exact replay in a changed environment without checking the retained environment.
