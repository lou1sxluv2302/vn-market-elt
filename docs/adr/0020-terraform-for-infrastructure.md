# ADR-0020: Terraform for infrastructure

- Status: Accepted
- Date: 2026-10-06
- Spec: D20

## Context

Infrastructure changes must be reviewable before they happen.

## Decision

Terraform with remote state in a dedicated versioned GCS bucket. The owner runs `apply` locally after reviewing `plan`; CI only runs `plan` with a read-only identity.

## Consequences

State is never committed; tfvars are git-ignored.
