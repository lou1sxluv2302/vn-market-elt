# ADR-0027: Cloud foundation now, collector VM at S0; buckets in us-central1

- Status: Accepted
- Date: 2026-10-13
- Spec: D6, D20, P0 step 0.7

## Context

Step 0.7 planned to create the whole cloud setup in P0, VM included. Since spec
v6, streaming comes after P1-P3 and the research track, and the S0 gate may find
that the VPS feed refuses non-Vietnamese IPs. A checked fact changes the cost: an
external IPv4 address on a running VM is not covered by the free tier
($0.005/hour, about $3.65/month at 24/7, against a $5 budget). A second checked
fact changes D6: the Cloud Storage free tier covers regional buckets in
us-east1, us-west1 and us-central1, not the `US` multi-region.

## Decision

- 0.7a, applied in P0: state and raw buckets, BigQuery datasets, service
  accounts and resource-scoped IAM, WIF for GitHub Actions, the secret
  container, security alerts.
- 0.7b, written and validated in P0, applied at S0 (`create_vm = true`): the
  collector VM in its own VPC, whose only inbound rule is SSH from IAP. The
  project's `default` network is not used: it opens port 22 to the internet.
- Buckets live in `us-central1`; BigQuery stays in `US`, which may load from a
  bucket in any US region (to be confirmed by a test load in S2).
- The alert e-mail app-password secret is dropped: alerts use Cloud
  Monitoring's e-mail channel, which needs no password.

## Consequences

- "SSH via IAP works" moves from the P0 done-when to S0 (step S0.3b).
- No idle VM and no IPv4 charge before the stream exists.
- Running the VM only in session hours (under $1/month of IPv4) is decided at S1.
