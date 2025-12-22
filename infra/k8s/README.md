# Kubernetes (deployment surface)

This directory is a runnable reference deployment for omphalOS on Kubernetes.
It is intentionally minimal: it demonstrates the **shape** of a real deployment
without assuming a specific cloud vendor.

## What it deploys

- Namespace: `omphalos`
- A PVC mounted at `/var/omphalos` to store run artifacts
- A nightly CronJob that runs the example config via the canonical CLI

## Use

```bash
kubectl apply -k infra/k8s/overlays/local
```

To run it once (ad-hoc), convert the CronJob to a Job:

```bash
kubectl -n omphalos create job --from=cronjob/omphalos-nightly-example omphalos-run-once
```

## Image

The manifests refer to `omphalos:latest`. Build and push your image using `docker/`:

- `docker/Dockerfile` builds an image that can run `python -m omphalos ...`
- override the image in an overlay, or with `kustomize edit set image ...`

