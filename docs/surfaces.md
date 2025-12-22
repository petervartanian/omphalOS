# Surfaces: what “Python + SQL + more” means here

The public reference ships **one core** and multiple **optional surfaces** around it.

The core is what produces a run directory, writes the manifest, and enforces gates.

The surfaces are ways to scale, schedule, and deploy the same contract-bound workflow
without forking logic.

## 1) Core runtime (Python)

Location: `src/omphalos/`

Responsibilities:

- deterministic run execution (`omphalos run`)
- run directory manifests + integrity verification
- publishability scanning
- release bundling (portable tarballs)
- contract schemas and rule packs

The reference pipeline is intentionally small and synthetic, but the *contract posture*
is the point.

## 2) SQL layer (dbt + plain SQL)

Location:

- `warehouse/` (dbt project: models/tests/macros)
- `sql/` (analyst-facing SQL library)

Use this layer when:

- you want marts/views that live outside the Python process
- you want SQL tests as first-class assertions
- you need the same transforms across SQLite (artifact), DuckDB (workstation), Postgres (deployment)

The repo does not force dbt as a dependency; treat it as an opt-in surface.

## 3) Orchestration (Airflow + shell)

Location:

- `orchestration/` (job and schedule registry)
- `orchestration/airflow/` (DAGs)
- `scripts/` (bash wrappers that CI or cron can run)

The principle: orchestration should call the same CLI you run locally.

## 4) Distributed compute (Spark)

Location: `spark/`

Spark is shipped as a reference surface for teams who need to precompute large staging
datasets. It is not required by the core.

## 5) Deployment (Kubernetes + Terraform)

Location:

- `infra/k8s/` (CronJob-based runner reference)
- `infra/terraform/` (cloud artifact store modules + examples)

These surfaces answer a practical question: where do run directories live, and how do
scheduled runs execute in a controlled environment?

