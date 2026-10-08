# ADR-0010: Power BI Desktop with manual refresh

- Status: Accepted
- Date: 2026-10-06
- Spec: D10

## Context

Options were Looker Studio, Grafana Cloud, Power BI, Metabase, Evidence and Streamlit. Auto-refresh adds cost (BigQuery bills ≥ 10 MB per table per query) and complexity.

## Decision

Use Power BI Desktop with manual refresh for both paths.

## Consequences

Highest career value; Google login, no key; `.pbix` files stay local and git-ignored. Grafana is deferred.
