package omphalos.run.manifest

default allow := false

required_keys := {"run_id","created_at","tool_version","artifacts_root_hash","artifacts"}

allow {
  type_name(input) == "object"
  has_required_keys
  root_hash_nonempty
  artifacts_valid
}

has_required_keys {
  missing := required_keys - {k | input[k]}
  count(missing) == 0
}

root_hash_nonempty {
  is_string(input.artifacts_root_hash)
  count(input.artifacts_root_hash) >= 16
}

artifacts_valid {
  count(input.artifacts) > 0
  not some i; invalid_artifact(i)
}

invalid_artifact(i) {
  a := input.artifacts[i]
  type_name(a) != "object"
}
invalid_artifact(i) {
  a := input.artifacts[i]
  not is_string(a.path)
}
invalid_artifact(i) {
  a := input.artifacts[i]
  not is_number(a.size)
}
invalid_artifact(i) {
  a := input.artifacts[i]
  not is_string(a.sha256)
}
