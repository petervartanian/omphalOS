package omphalos.tests

import data.omphalos.run.manifest

test_manifest_allows_minimal {
  manifest.allow with input as {
    "run_id": "r1",
    "created_at": "2025-01-01T00:00:00Z",
    "tool_version": "0.1.0",
    "artifacts_root_hash": "abc123abc123abc123",
    "artifacts": [{"path":"a.txt","size":1,"sha256":"00"}]
  }
}
