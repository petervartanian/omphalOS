# Kubernetes runtime

This directory defines a runnable Kubernetes deployment for scheduled and ad hoc omphalOS jobs.

The Kubernetes objects standardize three concerns:

- identity: service account and RBAC for reading configuration and writing artifacts
- configuration: ConfigMap and Secret mounts for run parameters
- storage: either a persistent volume mount or an object-store upload step

The base manifests define a namespace, RBAC, and job templates. Overlays adjust resources and scheduling.

## Layout

base/
  namespace, service account, RBAC
  job template for on-demand runs
  cronjob template for scheduled runs
  config and secret templates

overlays/
  local/
  prod/

## Artifact paths

All jobs write to a run directory rooted under a mounted path:

/var/lib/omphalos/artifacts/runs/<run_id>/

When an object store is used, the job writes locally and then uploads the run directory as a bundle.

## Config injection

The job reads a single run configuration file mounted at:

/etc/omphalos/run.yaml

The configuration selects:

- contract pack
- ingest connectors
- warehouse target and path
- export set and destinations

## Operational procedures

1. Apply the base:
   kubectl apply -k infra/k8s/base

2. Apply an overlay:
   kubectl apply -k infra/k8s/overlays/local

3. Trigger an ad hoc run:
   kubectl create job --from=cronjob/omphalos-nightly omphalos-ad-hoc-<suffix>

4. Inspect artifacts:
   kubectl exec -it <pod> -- ls -R /var/lib/omphalos/artifacts/runs

5. Verify the run:
   kubectl exec -it <pod> -- python -m omphalos verify --run-dir /var/lib/omphalos/artifacts/runs/<run_id>
