# infra/ — rules for agents

Loaded when working under `infra/`. Security design: `docs/spec.md` §14.

- **Plan, then the owner applies.** Write Terraform, run `terraform fmt`,
  `validate` and `plan`, and show the plan. The owner runs `apply` locally;
  CI only ever runs `plan` with the read-only `sa-ci`.
- **Keyless.** Identities are attached service accounts, application-default
  credentials, or Workload Identity Federation — a resource that needs a JSON
  key is redesigned.
- **Least privilege, resource-scoped.** Grant roles on the bucket or dataset,
  not the project, wherever the API allows (§14.2 table is the target state).
- **Ingress is IAP only** (`35.235.240.0/20`, port 22).
- **Environment values** (project id, bucket names) come from git-ignored
  `*.tfvars` / `config/env/*.yml`; commit only `*.example.*`.
- **Deployments are tags.** `deploy.sh <tag>` checks out exactly one tag on the
  VM; rollback is the previous tag.
- **Free tier first.** Before adding a resource, state its free-tier limit and
  expected cost in the PR.
