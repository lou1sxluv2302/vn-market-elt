# Terraform

Two stacks. The agent writes and plans; **the owner applies** (ADR-0020, `infra/CLAUDE.md`).

| Stack | State | Creates |
|---|---|---|
| `bootstrap/` | local, git-ignored, applied once | the APIs and the versioned state bucket `<project-id>-tfstate` |
| `main/` | `gs://<project-id>-tfstate/main` | raw bucket, BigQuery datasets, service accounts and resource-scoped IAM (spec §14.2), WIF for GitHub Actions, the `vnstock-api-key` secret container, security alerts, and the collector VM when `create_vm = true` |

Environment values live in git-ignored `prod.tfvars` files; copy each `prod.example.tfvars`.
Run every command from the repository root with your own Google login (application-default credentials); no key file is ever used.

## First run

```bash
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap plan -var-file=prod.tfvars -out=bootstrap.tfplan
terraform -chdir=infra/terraform/bootstrap apply bootstrap.tfplan
terraform -chdir=infra/terraform/main init -backend-config="bucket=<project-id>-tfstate"
terraform -chdir=infra/terraform/main plan -var-file=prod.tfvars -out=main.tfplan
terraform -chdir=infra/terraform/main apply main.tfplan
```

Then store the outputs as GitHub Actions **secrets** (not variables: the repository is public and only secrets are masked in logs): `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER` (output `wif_provider`), `GCP_CI_SERVICE_ACCOUNT` (output `ci_service_account`), `ALERT_EMAIL`.

## Free tier and cost

| Resource | Free tier | Expected cost |
|---|---|---|
| Buckets (us-central1) | 5 GB-months, 5,000 class A ops | ~0; a few cents of writes once the stream runs |
| BigQuery (`US`) | 10 GiB storage, 1 TiB queries | 0 |
| Secret Manager | 6 versions, 10,000 accesses | 0 |
| Monitoring alerts, admin audit logs | included | 0 |
| e2-micro VM, 30 GB pd-standard (only with `create_vm`) | 1 instance, 30 GB-months | 0 |
| External IPv4 on the running VM | **not covered**, $0.005/h | ~$3.65/month at 24/7; under $1 in session hours only |

## Safety

- `prevent_destroy` guards the state bucket, the raw bucket and the VM disk (stream samples and the vnstock device id cannot be recreated).
- The VM has its own VPC with one inbound rule: SSH from IAP (`35.235.240.0/20`). The project's `default` network, created with the Compute API, opens port 22 to the internet; nothing is placed in it. Delete it when convenient: `gcloud compute networks delete default` after removing its firewall rules.
- Alerts fire on IAM policy changes, service-account key creation and firewall changes. An apply that changes IAM triggers the first one; that is expected.
- Check after every apply that no service account has a user-managed key:
  `gcloud iam service-accounts keys list --iam-account=<account> --managed-by=user` must be empty.
