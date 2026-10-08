# ADR-0012: No JSON service-account keys anywhere

- Status: Accepted
- Date: 2026-10-06
- Spec: D12

## Context

Long-lived keys are the most common cause of cloud account compromise.

## Decision

VM: attached service account. Local: application-default credentials. CI: Workload Identity Federation. Power BI: Google login.

## Consequences

A gate checks that no user-managed keys exist.
