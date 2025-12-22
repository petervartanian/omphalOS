# Terraform (deployment surface)

This folder turns the previous placeholders into a real, minimal Terraform surface.

The repository does **not** assume a single cloud. Instead, it ships provider-specific
modules and examples for:

- AWS: S3 artifact bucket
- GCP: GCS artifact bucket
- Azure: Blob container + storage account

These examples are intentionally small. Real deployments will usually add:

- identities / IAM policies for the omphalOS runner
- encryption keys (KMS/CMEK) if required by policy
- object lifecycle/retention policies
- Kubernetes cluster provisioning (out of scope here)

## Use

Pick a cloud under `infra/terraform/examples/` and run:

```bash
terraform init
terraform plan
terraform apply
```

