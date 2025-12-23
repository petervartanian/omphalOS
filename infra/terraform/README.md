# Terraform runtime provisioning

This directory provides Terraform modules and examples that provision the minimum external services required by omphalOS:

- artifact storage with encryption and retention policy
- runtime identity with least-privilege write access to artifacts
- logging sink for job logs and run summaries

The examples are structured so that Kubernetes manifests can reference the provisioned outputs.

## Module set

modules/artifact_store
  encrypted bucket/container with lifecycle rules

modules/runtime_identity
  service account or role with scoped access to artifact store

modules/logging_sink
  log group/sink for operational logs

modules/secrets_wiring
  wiring for runtime secrets required by connectors

modules/scheduler_runtime
  optional primitives for scheduled execution

modules/network_minimal
  minimal networking surfaces when required by the platform

## Examples

examples/aws
examples/gcp
examples/azure

Each example wires the same module set and outputs:

- artifact_store_uri
- runtime_identity_id
- logging_sink_id

## Procedure

1. Select an example and initialize:
   terraform init

2. Plan:
   terraform plan -out plan.out

3. Apply:
   terraform apply plan.out

4. Export outputs into Kubernetes Secret/ConfigMap material used under infra/k8s.
