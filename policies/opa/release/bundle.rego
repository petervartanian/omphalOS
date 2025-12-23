package omphalos.release.bundle

default allow := false

allow {
  input.kind == "omphalos_release_bundle"
  is_string(input.bundle_id)
  count(input.bundle_id) > 0
  input.manifests
  count(input.manifests) > 0
  not some i; input.manifests[i].artifacts_root_hash == ""
}
