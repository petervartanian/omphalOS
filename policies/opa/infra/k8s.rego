package omphalos.infra.k8s

default allow := true

deny[msg] {
  obj := input[_]
  obj.kind == "Job"
  c := obj.spec.template.spec.containers[_]
  not c.resources.limits.cpu
  msg := sprintf("missing cpu limit for %s", [c.name])
}

deny[msg] {
  obj := input[_]
  obj.kind == "CronJob"
  tmpl := obj.spec.jobTemplate.spec.template
  c := tmpl.spec.containers[_]
  not c.resources.requests.memory
  msg := sprintf("missing memory request for %s", [c.name])
}
