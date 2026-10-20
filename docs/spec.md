# vn-market-elt - intraday Vietnamese market data on a cloud warehouse (ELT)

Status: approved (v6, 2026-10-08; research split into a private repo 2026-10-13 - D23-D24; streaming deferred) · Work started 2026-10-08
Origin: the owner's earlier private research repository (the *main repo*);
the Vietnamese source of this spec lives there at `.scratch/vts-elt/spec.md`.

**Legend:** 👤 = owner does it (accounts, billing, entering API keys - things an
agent must not do) · 🤖 = agent does it · ⛔ = gate: stop and discuss if it
fails · all hours are **estimates**.

---

## 0. Progress

Checked = done. Updated 2026-10-17. Once GitHub milestones exist (step 0.6),
they become the source of progress and this list is retired.

**K0 - Knowledge harvest**
- [x] K0.1 Inventory of v1's knowledge base - approved 2026-10-08 (kept in the private research repo)
- [x] K0.2 Foundation translated - `market-microstructure.md`, `data-sources.md`, `data-quality-lessons.md`; `engineering-rules.md` rewritten (33 rules); glossary +32 terms
- [x] K0.3 Indicators, flows, BI conventions - `indicators.md`, `flows.md`, `bi-conventions.md` and a measured v2 palette (#12); research findings stay in the private repo

**P0 - Foundations**
- [x] 0.1 Repository skeleton, English spec, ADRs, glossary, knowledge harvest - all in the bootstrap commit on `main` (2026-10-13), local only
- [x] 0.2 Main repo: KB update committed (`b2ddd44`), Vietnamese spec replaced by a pointer (`1785a9b`)
- [x] 0.3 GCP project, billing, $5 budget (credits excluded, alerts 20% / 100% / forecast), 2-step verification, `gcloud` and ADC with quota project (👤, 2026-10-13)
- [x] 0.4 GitHub: public repo `lou1sxluv2302/vn-market-elt` created, `gh` signed in, personal git identity set (2FA to be confirmed by the owner)
- [x] Commit the pending docs (folded into the bootstrap commit, 2026-10-13)
- [x] Research content split into a private companion repo; README rewritten for a portfolio audience (2026-10-13)
- [x] Security audit before first push (2026-10-13): no secrets; 2 Medium + 4 Low fixed - procedure in `docs/runbooks/security-audit.md`
- [x] Pushed 2026-10-13: public `main`; private companion repo created (visibility verified private) and pushed; Dependabot security updates on
- [x] Agent workflow skills, mattpocock/skills integration (`docs/agents/`, `CONTEXT.md`), git guardrail hook - PR #5, merged 2026-10-13
- [x] 0.5 Repo security - pre-commit installed and green on the whole repo (secret scan, gitleaks, private keys, large files, data files, dashes, ruff); Dependabot; GitHub secret scanning and push protection on (#6)
- [x] 0.6 Rulesets `protect-main` and `protect-release-tags`, squash-only, auto-delete branches, labels, phase milestones, PR/issue templates, CODEOWNERS (#7); status checks join the ruleset in 0.8
- [x] 0.7 Terraform (#14, #15) - `bootstrap` and `main` applied by the owner, CI secrets stored, `infra / terraform-plan` green and required; `marts_research` added (#28). 0.7b (VM + IAP firewall) is written and applied at S0 (ADR-0027)
- [x] 0.8 Minimal CI - workflows `ci` and `security`, required in `protect-main`; a red PR was blocked and a planted key caught (#9). Terraform checks arrive with 0.7

**Spec**
- [x] v6 approved 2026-10-08 - research track before streaming (D23, D24); research moved to a private repo 2026-10-13

**Cold path · research · streaming** (tags: `v0.1.0` on P0's last commit, `v0.2.0` on the cold path's, both 2026-10-17)
- [x] P1 history load - `raw_vnstock` holds every pull of v1's daily OHLCV (145 files to 2026-10-13) and the symbol lists; `tools/reconcile_v1.py` green on all four checks (#18)
- [x] P2 dbt (#20) - project, keyless identity, market-rule seeds, staging, intermediate (#21); marts (calendar, securities SCD2, prices, liquidity, universe) and `tools/reconcile_v1_marts.py` green on all four checks, every difference named by its mechanism (#22)
- [x] P3 data-quality tests (#23) - v1's checks for the layers v2 has as 66 dbt data tests; `tools/planted_faults.py` proves each can go red (32 faults, in CI); `dbt build --target prod` green 2026-10-15
- [x] Research track (private repo) - features and PANIC labels, hypotheses registered then measured once, a walk-forward test; a forward journal runs every trading day from 2026-10-16. Inputs added here: flows and index history (#27, #28), `--datasets` for the daily reload (#30)
- [ ] P4 (#34) - code merged (#35, ADR-0029): vendor rewrites classified (`fct_price_revision`), daily reconciliation logged; done at 10 consecutive passing sessions (1 of 10 on 2026-10-16)
- [x] S0.1 feed probe and report (#33); a one-minute connection check connected (2026-10-16)
- [x] S0.2 local probe, 30 minutes of a live session (2026-10-19): 3,301 msgs/min, 0.17 MiB/min as parquet, 0 disconnects, ~1 s latency, 183 MB RAM; reference / ceiling / floor and foreign flow per symbol present - `docs/reports/s0-feed-probe.md`
- [x] S0.3 a Linux licence slot is free (2 of 2, owner, 2026-10-19)
- [x] S0.3b-S0.4 the VM applied (#45), key in Secret Manager, vendor installer on the VM; the same probe there on 2026-10-20: **cloud gate passed** (ADR-0033)
- [x] S1.1-S1.3 collector and verified uploader (#37, ADR-0030)
- [ ] S1.4 outside alert (ADR-0032): metric and policy written, tried on the live metric, policy applied and checked 2026-10-17; planted network cut in a live session · S1.5-S1.6 deployment, 5 sessions - after the gate
- [x] S2.1-S2.3 load exactly once from the verified file, `tools/reconcile_stream.py` (#39, ADR-0031); table and owner impersonation applied and checked 2026-10-17
- [ ] S2.4 first live session reconciled per batch
- [ ] S3 hot path: dbt views + Power BI
- [ ] S4, P4, P5 → `v1.0.0`

**Raised for the main repo, not acted on** (v1 is read-only from here; needs a separate decision)
- [ ] `market_rules.yml` lacks 2026-11-24 (Vietnam Culture Day) and all 2027 holidays
- [ ] `sources.yml` still declares CafeF CSV as the primary foreign-flow source; v1's own KB says VCI

---

## 1. Goals

1. **≤ 5 minutes of latency during the trading session.** At 09:20 you can see
   the market as of 09:15. Not tick-by-tick real time. A **manually refreshed**
   dashboard is enough.
2. **Learn cloud warehousing, dbt and BI** and make the result **demo-able**: a
   public English repository with readable history, releases and security docs.
3. **Do not break the running system.** The main repo's 15:00 batch pipeline
   stays untouched, and its DuckDB is the **reference answer** this project
   reconciles against.
4. **Serve as the data foundation for a private stock-selection research
   track** (D23), under the research discipline of D24.

Out of scope: automated order placement · investment advice · publishing **data** (vendor licences
forbid redistribution; publishing **code** is fine) · auto-refreshing dashboards
(deferred, §9).

## 2. Baseline measurements

| Fact | Value | Source |
|---|---|---|
| Duration of the 15:00 batch chain | **62-79 min** (2026-08-26 → 10-06) | main repo scheduler log |
| Where the time goes (2026-10-06) | Foreign/proprietary flow extraction: **~52 min / 613 slices**, 477 empty. Indicator computation: **339 s** | main repo run log |
| ⇒ Bottleneck | **Waiting on the API**, not transformation. Switching ETL→ELT does **not** make it faster by itself; **streaming** does | - |
| Price history in the main repo | `vnstock_quote` 4,578,258 rows (2000-07-28 → 2026-10-06) · `vndirect_dchart` 8,787 | DuckDB query, 2026-10-06 |
| vnstock plan | Paid sponsor plan; device-based licence counted per operating system | vendor account · main repo KB 02 §v1.7 |
| Intraday feed | `vnstock_pipeline.stream.WSSClient`, VPS WebSocket. **Code read only, not yet run** | main repo KB 02 §v1.7 |
| Databricks Free Edition | One 2X-Small SQL warehouse, **no external storage**, restricted outbound internet | Databricks docs |

Intraday prices are always *actual* traded prices; corporate-action adjustment
only happens *later*, when a vendor rewrites history. Recording the daily close
from the feed therefore yields a **raw price series from the first capture day
onward that no vendor can rewrite**.

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Separate repository**, a sibling folder of the main repo | A branch would be checked out under the main repo's 15:00 job; a nested repo becomes a gitlink under `git add -A` and pollutes searches |
| D2 | History is loaded **once from the main repo's parquet files** (read-only); increments come from the source | Do not re-pull 26 years through a shared API key |
| D3 | **dlt** for EL, **dbt** for T | Standard ELT pair; dbt is warehouse-portable |
| D4 | **BigQuery** is the primary warehouse; Snowflake, Athena, Databricks are comparison phases (§7) | Perpetual free tier; matches day-job stack |
| D5 | **Intraday streaming**, loaded in 60-second batches | Goal 1 |
| D6 | **Cloud from day one**: Compute Engine **e2-micro** in `us-central1`; GCS in **`us-central1`** (the free tier covers US regions, not the `US` multi-region); BigQuery in `US` (ADR-0027) | Perpetual free tier; persistent disk keeps the vnstock device id ⇒ one licence slot |
| D7 | **No** Cloud Run or ephemeral containers for the collector | Each start may register a new device ⇒ HTTP 429 |
| D8 | VPS feed terms-of-use risk: **accepted** | Owner decision, 2026-10-06 |
| D9 | A process running for the whole session: **accepted** | Owner decision, 2026-10-06 |
| D10 | **BI = Power BI Desktop, manual refresh**, for both hot and cold paths | Highest career value; connects to BigQuery with a Google login, no key; `.pbix` stays local |
| D11 | Hot path uses **dbt views**, not cron-built tables | Refresh runs the query on the newest data ⇒ latency = batch interval |
| D12 | **No JSON key files anywhere**, CI included | VM uses its attached service account; local uses ADC; GitHub Actions uses WIF; Power BI uses a Google login |
| D13 | Secondary warehouses only **after P3**, same parquet, same dbt project | Earlier would mean fixing each bug in four places |
| D14 | **Everything in this repository is in English**: identifiers, comments, commits, branches, tags, docs | Demo-ability. The main repo keeps its Vietnamese rule; one rule per repo |
| D15 | Vietnamese market terms are translated through **one glossary**, `CONTEXT.md` at the repo root (ADR-0025) | Two translations of one concept cannot be reconciled |
| D16 | **GitHub Flow + Conventional Commits + SemVer** (`CONTRIBUTING.md`) | One long-lived branch is enough for a solo project; history still reads like a team's |
| D17 | **The VM only runs tagged releases**, never `main` HEAD | The tag is what runs; rollback = deploy the previous tag |
| D18 | Repository **`vn-market-elt`**, Python package `vnmarket` | Descriptive kebab-case English name |
| D19 | Repository is **public from day one** | GitHub Free only offers rulesets on public repos; leak risk is handled by §14 on **every PR** |
| D20 | Infrastructure in **Terraform**; remote state in a dedicated versioned GCS bucket, never committed; `apply` runs on the owner's machine after reviewing `plan` | Reviewable plans and diffs |
| D21 | **v2 inherits v1's knowledge through a reviewed harvest** (phase K0). Once migrated, the copy in `docs/knowledge/` is the source of truth for v2; v1 is a frozen reference and the two may diverge. Numbers measured on v1's warehouse keep the label *measured on v1, <date>* | v1 holds hard-won market knowledge, but also infrastructure and model errors that must not be inherited silently |
| D22 | **v2's rules are re-selected, not copied.** A rule stays only if it prevents irreversible harm, is standard industry practice, or can be enforced by a tool (CI, dbt test, gitleaks, ruleset); tool-enforced rules are preferred. Rules are written as defaults with a stated escape, except the always-on guardrails in `CLAUDE.md` | v1 accumulated many strict rules fitted to its own architecture (single DuckDB file, Task Scheduler, rebuild order) that do not transfer |
| D23 | **A stock-selection research track runs in a private companion repository**, scheduled before streaming (S0-S3); this repository supplies its data foundation | The owner's priority; research content is a private asset and is not published |
| D24 | **Research discipline is kept even though v1's process rules are not**: pre-registration before any run · a random same-session control · `n_eff` for overlapping windows · exploration on 2015-2020 only · confirmation only by forward accumulation · no parameter tuning toward a better result | These rules protect conclusions, not infrastructure; v1's 11 refuted hypotheses are their track record |

## 4. Architecture

```
                     ┌──────────── VM collector-prod-01 (e2-micro, us-central1) ────────────┐
VPS feed (WebSocket) ┼─► stream_collector (systemd 08:55-15:05) ─► parquet batch / 60 s ─────┼─► GCS raw bucket
                     │   Cloud Monitoring: no batch > 3 min ⇒ email                          │        │
                     │   ingress: IAP only · runs as user `collector` · tag-pinned release   │        ▼
                     └───────────────────────────────────────────────────────────────────────┘  BigQuery raw_vps_stream
                                                                                                         │
                                                                              dbt views (marts_intraday) ◄┘
                                                                                         │
                                                                 Power BI Desktop ◄── manual Refresh

main repo parquet ─dlt (once)────► BigQuery raw_vnstock ─dbt (end of day)─► marts_daily ─► Power BI
vnstock API, after 16:30 ─dlt (incremental)─┘                                    │
                                                         reconcile against the main repo's DuckDB (read-only)
                                       marts_daily ─► private research repository (read-only consumer)
```

**Hot path** (views, refresh on demand): indices · market breadth
(advancing/declining/ceiling/floor) · liquidity vs. the same time in the previous
session · intraday foreign and proprietary flow · today's setup list vs. entry
and stop levels.

**Cold path** (end of day): price history, `is_stale`, trading calendar,
point-in-time universe. The private research track builds on it. Later:
financial statements.

Intraday EMA is incremental: `EMA_t = α·price + (1−α)·EMA_yesterday`, computed
for exactly one bar.

🔴 **Never mix intraday prices with adjusted history.** Every intraday
comparison uses the feed's own **`reference_price_vnd`**, never the adjusted
close of `vnstock_quote` - that is wrong on ex-rights days.

## 5. Latency budget (hot path)

| Hop | Estimate | Measured in |
|---|---|---|
| Feed → collector | seconds | S0: received time − message time |
| Batching | ≤ 60 s | - |
| Upload to GCS + BigQuery load | 10-60 s | S2 |
| dbt view + Power BI refresh | seconds to ~1 min | S3 |
| **Total** | **~2-3 min** | S3: wall clock during a live session |

If a view is slow because it parses raw JSON every time, switch **only that
model** to incremental (only then is a cron needed), based on measurements.

## 6. Phases - main path on BigQuery

Each phase = one **GitHub milestone**; each step = one issue + one branch + one
PR; a finished phase = one tag (`CONTRIBUTING.md`).

**Execution order (v6):** K0 → P0 → K0.3 → P1-P3 → research track (private
repo) → S0-S3 → S4, P4, P5. Streaming waits behind the research track (D23);
the sections below are reference, not sequence.

### K0 - Knowledge harvest from v1 (~9 h, part of `v0.1.0`)

| Step | Who | Work |
|---|---|---|
| K0.1 | 🤖 → 👤 | **Inventory**: label every section of v1's knowledge base - `KEEP` (still-valid knowledge) · `LESSON` (incident, condensed) · `V1-RULE` (drop, or rewrite if it passes D22) · `STALE` (outdated or wrong, with the reason) · `RESEARCH` (research knowledge; now needed by track R, D23). Output kept in the private research repo; **the owner approves it before any translation** |
| K0.2 | 🤖 | Translate and condense the foundation every phase needs: market microstructure, data sources and the feed, data-architecture lessons → `docs/knowledge/` |
| K0.3 | 🤖 | Indicators, flows and BI conventions, in the phase that needs them. v1's research findings go to the private research repo |

Every migrated fact keeps its evidence level (✅ measured · ⚠️ from documentation · ❓ unverified) and its v1 source section.

### P0 - Foundations (~11 h, tag `v0.1.0`)

| Step | Who | Work |
|---|---|---|
| 0.1 | 🤖 | Repository skeleton; `git init -b main`; this English spec; one ADR per decision; the glossary (now `CONTEXT.md`) |
| 0.2 | 🤖 | Main repo: commit KB update and the Vietnamese spec (done, `b2ddd44`); replace that spec with a pointer here |
| 0.3 | 👤 | GCP: project · billing · **budget $5 with alerts at 20% and 100%** · 2-step verification · install `gcloud`; run `gcloud auth login` and `gcloud auth application-default login` |
| 0.4 | 👤 | GitHub: 2FA · install `gh`, run `gh auth login` · create the empty public repo `vn-market-elt` (done) |
| 0.5 | 🤖 | Repo security (§14.6): `.gitignore` · pre-commit (gitleaks, ruff) · `SECURITY.md` · Dependabot · secret scanning + push protection |
| 0.6 | 🤖 | GitHub (`CONTRIBUTING.md`): `main` ruleset · labels · milestones P0…X3 · PR/issue templates · `CODEOWNERS` |
| 0.7 | 🤖👤 | Terraform (D20): agent writes, owner reviews `terraform plan` and runs `apply`. 0.7a creates: state and raw buckets · datasets · 4 service accounts · WIF for GitHub Actions · Secret Manager container (no value) · security alerts. 0.7b (VM in its own VPC + IAP-only firewall) is written now and applied at S0 (ADR-0027) |
| 0.8 | 🤖 | Minimal CI: the P0 required checks (`CONTRIBUTING.md`) |

Repository layout:
```
vn-market-elt/
├── .github/        workflows/ (ci, infra, security, release) · ISSUE_TEMPLATE/ · pull_request_template.md · CODEOWNERS · dependabot.yml
├── CLAUDE.md       agent router (topic → file); directory rules in nested CLAUDE.md
├── README.md · SECURITY.md · CONTRIBUTING.md · CHANGELOG.md · LICENSE
├── docs/           spec.md · engineering-rules.md · domain.md · knowledge/ · adr/ · runbooks/ · reports/
├── config/         *.yml (no constants in Python) · env/<env>.example.yml
├── src/vnmarket/   collector/ · el/ · common/
├── dbt/            models/{staging,intermediate,marts/intraday,marts/daily} · seeds · macros · tests
├── infra/          terraform/ · systemd/ · deploy.sh
├── tools/          gate.py · reconcile_duckdb.py
├── tests/fixtures/ synthetic data only - NEVER real market data
├── bi/             *.pbix - git-ignored
└── data/           local buffer - git-ignored
```

**Done when:** `bq ls` shows the datasets · budget alert on · `infra / terraform-plan` green through WIF ·
a test PR is blocked while CI is red · gitleaks blocks a planted fake key.

### S0 - Feed probe (~4 h, part of `v0.3.0`) ⛔ gate: go to the cloud or not

| Step | Who | Work |
|---|---|---|
| S0.1 | 🤖 | `src/vnmarket/collector/feed_probe.py --minutes N --symbols <list> --out <dir>`: write **every message verbatim** to JSONL with `received_at`. Rejects unknown arguments. Timeouts everywhere. `--self-test` on synthetic messages with known answers, including planted malformed messages and disconnects |
| S0.2 | 👤🤖 | **Run locally for 30 min, session of 2026-10-09 around 09:30-10:00** (avoid the opening auction): 30 universe symbols + indices. Uses the **main repo's virtualenv** (already has `vnstock_pipeline`, same Windows device id ⇒ no new licence slot); writes nothing into the main repo |
| S0.3 | 👤 | Check the vnstock device page: free Linux slots |
| S0.3b | 👤🤖 | Apply 0.7b (`create_vm = true`): VM, its VPC and the IAP-only firewall. **Done when** SSH through IAP works |
| S0.4 | 👤🤖 | Owner stores the vnstock API key in Secret Manager (once) and runs the vnstock installer on the VM over IAP SSH; agent repeats the 30-minute probe there |

S0 report (`docs/reports/s0-feed-probe.md`): messages/min · MB/min · latency ·
disconnects and reconnects · **does the feed carry reference/ceiling/floor
prices** · is foreign flow per symbol · process RAM and CPU. **Aggregates only,
no raw data.**

**⛔ Gate:** works on the VM ⇒ continue · IP blocked ⇒ stop; options: a
Vietnam-hosted VPS, or collect locally and push to the cloud · not enough RAM ⇒
decide whether to upsize (leaves the free tier).

### S1 - Collector in production (~8 h, tag `v0.3.0`)

- `stream_collector.py`: WebSocket → buffer → every **60 s** write `dt=YYYY-MM-DD/batch=HHMMSS.parquet`, storing the **verbatim message** (`payload` JSON) + `received_at` + `batch_id`; parsing is dbt's job.
- `uploader.py`: upload batches to GCS with retries and timeouts.
- Alert: during trading hours, **no new batch for 3 min** ⇒ email, from Cloud Monitoring outside the collector's machine, watching a custom metric the uploader writes per batch (ADR-0030, ADR-0032; replaces a `healthcheck.py` on the machine, which could not mail while its network is cut).
- `infra/systemd/vnmarket-collector.service` + `.timer`: restart on failure; start **08:55**, stop **15:05**, Mon-Fri; systemd sandboxing (§14.4).
- Holiday calendar from seed `trading_calendar`, **copied once** from the main repo with provenance. No row for today ⇒ **run anyway** (a missed real session is lost forever; an unnecessary run costs one warning).
- Deployment: the VM checks out **exactly one tag** (D17) via `infra/deploy.sh <tag>`.

**Done when:** 5 consecutive sessions, every data gap matched by an alert.
**Planted fault:** cut the VM's network for 5 minutes ⇒ the email must arrive.

### S2 - Load into the warehouse (~4 h, part of `v0.4.0`)

After each batch: a load job appends it to `raw_vps_stream.messages` (partitioned by day on `received_at`) from the local file already verified against its GCS copy; job ids make each load exactly once (ADR-0031).
**Done when:** message counts in BigQuery equal those in parquet, **per batch** (`tools/reconcile_stream.py`).

### S3 - Hot path: dbt views + Power BI (~7 h, tag `v0.4.0`)

- dbt: `stg_vps_stream__<message_type>` → `int_quotes__latest_by_symbol` → `marts/intraday/*`, **materialized as views**, reading today's partition only.
- Power BI Desktop: Get Data → Google BigQuery, Google login, **connect only to `marts_*`** (a convention, not a barrier: the owner's account can see everything).
- **Q7 (setup list):** requires changing the main repo's 15:00 chain to upload `setup_hom_nay.json` to GCS - a change to a running system, **approved separately**.

**Done when:** in a live session, a refresh at T+5 min shows the state at T (wall clock).

### P1-P3 - Cold path (~18 h, tag `v0.2.0`)

| Phase | Work | Done when |
|---|---|---|
| P1 | dlt loads history from the main repo's raw parquet into `raw_vnstock` (**read-only**): every pull of daily OHLCV kept as a log, plus the symbol reference lists; security master and calendar are rebuilt in P2 | `tools/reconcile_v1.py`: raw = parquet per file · latest-wins over raw reproduces DuckDB except explained residuals · reference lists = parquet |
| P2 | dbt: `is_stale` · `dim_trading_calendar` (≥ 30 traded symbols) · point-in-time universe · market-rule seeds with effective dates (tick size, price band, holidays, exchange aliases and changes, known bad dates). `tools/reconcile_v1_marts.py` opens DuckDB **read-only** | Matches DuckDB per Q4 (redefined: exact where v2 means the same, every deliberate difference counted) |
| P3 | Port the main repo's data-quality tests to dbt tests, with planted faults | Every test has failed at least once |

From P2 on: portable SQL; warehouse-specific functions go **behind macros**.

### Research track (private companion repository)

A stock-selection research track (D23) runs in a **private** companion
repository. It reads this project's marts (prices, calendar, universe, breadth,
flows) and keeps its features, hypotheses, measurements and journal to itself.
This repository provides the data foundation and the research discipline it
follows (D24); nothing about the hypotheses or their results is published here.

### S4, P4, P5 (~18 h, tags `v0.5.0` then `v1.0.0`)

| Phase | Work | Done when |
|---|---|---|
| S4 | Daily bars rebuilt from ticks vs. vnstock end-of-day OHLC - measures collector completeness | Every deviation explained |
| P4 | Incremental load after 16:30 (from v1's parquet for now, ADR-0029); vendor history rewrites classified in `fct_price_revision` (Q1); `tools/reconcile_v1_marts.py --log` every trading day | `--streak` reaches 10 consecutive passing sessions |
| P5 | Demo README (architecture, dashboard screenshots on **synthetic data**, dbt lineage) · CI adds `dbt build` on **DuckDB with synthetic data** · full security review (§14.8) | **`v1.0.0`: demo-ready** |

## 7. Warehouse comparison phases (after P3)

Same parquet, same dbt project, only the adapter changes; Power BI has
connectors for all four ⇒ **one report, swapped source**.

| Phase | Warehouse | Free model | When | What it teaches | Tag |
|---|---|---|---|---|---|
| **X1** | Snowflake (`dbt-snowflake`) | ~30-day trial | After P3; **sign up the day you start** | Compute/storage separation · Time Travel · zero-copy clone · count of SQL changes | `v1.1.0` |
| **X2** | AWS S3 + Athena + Glue (`dbt-athena`) | New-account credits, time-limited | Learning-plan phase 5, can move earlier | Serverless lakehouse; real AWS↔GCP numbers. Power BI needs the Athena ODBC driver | `v1.2.0` |
| **X3** | Databricks Free Edition (`dbt-databricks`) | Free, no time limit | **Optional**, last | Delta, Spark. No external storage ⇒ upload parquet to a Volume by hand | `v1.3.0` |

Each X phase adds one row to `docs/warehouse-comparison.md`: `dbt build` time ·
bytes scanned · cost · lines of SQL changed · DuckDB match. Every new warehouse
gets **the same §14 rules** (dedicated users, least privilege, no long-lived keys).

## 8. Schedule (2 h/day, started 2026-10-08)

| Block | Hours (est.) | Milestone |
|---|---|---|
| K0.1-K0.2 | ~9 | done 2026-10-08 |
| P0 | ~11 | ~10-15 |
| K0.3 | ~8 | ~10-19 |
| P1-P3 | ~18 | ~10-30 · cold path matches DuckDB |
| Research track (private repo) | ~26 | ~11-14 |
| S0-S3 | ~23 | ~11-28 · **⛔ cloud gate**, then hot path live |
| S4, P4, P5 | ~18 | ~12-09 · **`v1.0.0`** |
| HNX→HOSE switch | - | 2026-12-28 · plan a `v1.x` release |
| X1 → X2 → (X3) | ~10 / ~10 / ~6 | after `v1.0.0` |
| **Main path** | **~113** | |

Expected cost: **$0** within the free tier, **except one item to measure in
P0**: the public IPv4 charge for the VM (§14.3). The $1 budget alert will fire if
this estimate is wrong.

## 9. Deliberately deferred

- **Auto-refresh dashboards:** Grafana Cloud - not part of the current plan (BI is
  Power BI with manual refresh, D10). Checked 2026-10-06: the official Apache-2.0
  BigQuery plugin supports keyless auth via Workload Identity Federation (not
  tried). If adopted: refresh **every 5 min, no faster** - BigQuery bills at least
  10 MB per table per query ⇒ 10 panels refreshed every minute ≈ 0.8 TB/month,
  close to the 1 TB free tier.
- Looker Studio · Lightdash (semantic layer) · Zalo alerts · automated releases (release-please).

## 10. Open questions

| # | Question | Proposal | Blocks |
|---|---|---|---|
| Q1 | How to detect vendor history rewrites after corporate actions? | **Decided (P4, ADR-0029):** every pull is compared with the one before; each rewrite is classed same_close, rescale, noise or other in `fct_price_revision`; `other` warns above the measured count | - |
| Q2 | First cold-path scope? | **Decided (P1):** daily OHLCV + symbol reference lists loaded; security master and calendar built in dbt (P2); flows, fundamentals and index later | - |
| Q3 | EMA and recursive indicators in dbt? | History: window-function definitions (SMA, ranges, ATR from SMA of true range); an EMA only where a consumer needs it, computed in a Python step. Intraday: incremental | P2 |
| Q4 | DuckDB match criteria | Row count per (symbol, date) · exact price match · `is_stale` and universe 100% | P2 |
| Q6 | Subscribe to all HOSE+HNX symbols or the universe only? | Decide after S0 from MB/min | S1 |
| Q7 | Where does today's setup list come from? | From the research track if it produces one; otherwise the main repo uploads its list after 15:00 (**separate approval**) | S3 |

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| VPS feed blocks non-Vietnamese IPs | D6 fails | Tested in S0.4; two fallbacks at the S0 gate |
| Collector dies mid-session unnoticed | Rest of the session lost forever | Cloud Monitoring alert from S1 (ADR-0030); **no alert ⇒ S1 not done** |
| 1 GB RAM insufficient | OOM | Measured in S0.4 |
| vnstock device slots exhausted | Process dies at import | Persistent disk (D7); check device page first (S0.3) |
| Cost overrun | Money | Budget alert · date partitions · manual refresh · measure IPv4 charge |
| Shared API key with the main pipeline | Main pipeline throttled | End-of-day pulls after 16:30 at a lower rate |
| **HNX→HOSE consolidation on 2026-12-28** (VNX, announced 2026-09-30), about three weeks after the planned `v1.0.0` | Exchange, band, tick and possibly tickers change for ~300 symbols; HNX-Index fate unknown | `exchange` modelled as SCD2 from P2; band/tick seeds keyed by (exchange, date); re-verify when VNX publishes final rules; plan a `v1.x` release around the switch |
| Data or secrets leak into the public repo | Licence breach · account takeover | All of §14 |

## 12. Working rules

Engineering rules inherited from the main repo (self-tests, timeouts, strict
CLIs, three-state results, reconciliation) live in one place:
[`engineering-rules.md`](engineering-rules.md). Domain rules (reference price,
units, scope, stale sessions): [`domain.md`](domain.md).

## 13. Naming conventions

One rule: **a name must equal what it holds.** No abbreviations unless listed in
`CONTEXT.md`.

### 13.1 Repository, Python, CLI

| Thing | Convention | Example |
|---|---|---|
| Repository | kebab-case | `vn-market-elt` |
| Package / module | snake_case noun | `vnmarket.collector.batch_writer` |
| Function | snake_case verb | `write_batch()` |
| Class | PascalCase | `StreamCollector` |
| Constant | UPPER_SNAKE, **only** loaded from config | `BATCH_SECONDS` from `config/collector.yml` |
| CLI flag | kebab-case, full words | `--dry-run`, `--self-test`, `--minutes` |
| Config file / key | snake_case | `batch_seconds: 60` |

### 13.2 Columns (all warehouses)

| Suffix / prefix | Meaning | Example |
|---|---|---|
| `_at` | TIMESTAMP in **UTC** | `received_at` |
| `_date` | DATE in **Vietnam time** (UTC+7) | `trade_date` |
| `_vnd` | integer VND | `close_vnd` |
| `_qty` | number of shares | `match_qty` |
| `_pct` | percentage ×100 | `change_pct` |
| `_ratio` | ratio, not ×100 | `foreign_ownership_ratio` |
| `is_` / `has_` | BOOLEAN | `is_stale` |
| `_id` | technical key; a security's stable key is `security_id`, its ticker column is `symbol` | `batch_id`, `security_id` |
| `_count` | count | `advancing_count` |
| leading `_` | technical, non-business column | `_ingested_at`, `_source_id` |

### 13.3 dbt

| Layer | Convention | Example |
|---|---|---|
| source | `<vendor>_<channel>` | `vps_stream`, `vnstock` |
| staging | `stg_<source>__<entity>` | `stg_vps_stream__quotes` |
| intermediate | `int_<entity>__<transform>` | `int_quotes__latest_by_symbol` |
| fact / dimension | `fct_<process>` · `dim_<entity>` | `fct_intraday_breadth`, `dim_security` |
| mart folders | `marts/intraday/` · `marts/daily/` | - |
| singular test | `assert_<invariant>` | `assert_close_within_price_band` |
| macro | verb | `to_vn_date()` |
| seed | plural noun or rule name | `market_rules`, `trading_calendar` |

### 13.4 Warehouse and cloud

| Thing | Convention | Example |
|---|---|---|
| BigQuery dataset | layer name; `dev_` prefix for dev | `raw_vps_stream` · `raw_vnstock` · `staging` · `intermediate` · `marts_intraday` · `marts_daily` |
| GCS bucket | `<project-id>-<env>-<purpose>` | `<project-id>-prod-raw` |
| Object path | Hive partitions | `vps_stream/dt=2026-10-09/batch=093000.parquet` |
| VM | `<role>-<env>-<NN>` | `collector-prod-01` |
| Service account | `sa-<role>` | `sa-collector`, `sa-loader`, `sa-dbt`, `sa-bi-reader`, `sa-ci-plan` |
| Resource labels | `project`, `env`, `component`, `managed_by` | `managed_by=terraform` |

Glossary of Vietnamese market terms: [`../CONTEXT.md`](../CONTEXT.md).

## 14. Security

See [`../SECURITY.md`](../SECURITY.md) for the reporting policy. Design rules:

### 14.1 Assets and threats

| Asset | If lost | Main threats |
|---|---|---|
| vnstock API key | Paid plan abused, device slots consumed | Committed by mistake · leaked from the VM or logs |
| GCP access | Crypto-mining on your bill | A leaked service-account key · SSH open to the internet · no 2FA |
| GitHub access | Code running on the VM altered; GCP access stolen through CI | Leaked token · compromised third-party action |
| Market data | Licence breach | Committed parquet/pbix · public bucket · real-data screenshots |

### 14.2 Identities and least privilege

| Identity | Used by | Permissions (resource-scoped wherever possible) |
|---|---|---|
| Owner's Google account | Console, local Terraform, Power BI | Project owner. **2FA mandatory** |
| `sa-collector` | Attached to the VM | `storage.objectCreator` **on the raw bucket only** · `bigquery.jobUser` · `bigquery.dataEditor` **on `raw_vps_stream` only** · secret accessor on its own secrets · `logging.logWriter` and `monitoring.metricWriter` (VM logs and metrics); off the VM the owner impersonates it (Token Creator, ADR-0031) |
| `sa-loader` | dlt loads (P1 history, later daily pulls), run on the owner's machine through impersonation | `dataEditor` **on `raw_vnstock` only** · `jobUser`; only the owner holds `serviceAccountTokenCreator` on it |
| `sa-dbt` | dbt runs | `dataViewer` on `raw_*` · `dataEditor` on `staging`, `intermediate`, `marts_*` · `jobUser` |
| `sa-bi-reader` | Reserved for future BI (Grafana) | `dataViewer` on `marts_*` only · `jobUser` |
| `sa-ci-plan` | GitHub Actions via WIF | **Metadata only**: `iam.securityReviewer`, service-account, WIF-pool, BigQuery metadata, bucket, secret and monitoring viewer roles, a custom compute-metadata role (no serial-port output), and `objectViewer` on the state bucket; enough for `terraform plan -lock=false`. Never `roles/viewer`: project viewers can read every dataset and bucket by default. No BigQuery access (CI runs dbt on DuckDB). `apply` never runs in CI |

- **No JSON keys** (D12). Without a GCP organization the key-creation policy
  cannot be enforced, so a gate checks that
  `gcloud iam service-accounts keys list` returns only Google-managed keys.
- WIF is restricted to this repository; CI holds **no write-capable identity**.
  GitHub issues no OIDC token to fork PRs.

### 14.3 Network and VM

- **Port 22 is never open to the internet.** SSH only through **IAP**; the
  firewall allows `35.235.240.0/20` on port 22 and nothing else inbound.
- Outbound internet is required for the feed. ⚠️ **Measure in P0** whether the
  free tier covers the public IPv4 charge; alternatives: keep an ephemeral public
  IP with no inbound rules, or Cloud NAT (also billed).
- Debian stable · Shielded VM · OS Login · `unattended-upgrades` · default disk encryption.

### 14.4 Processes on the VM

- The collector runs as a dedicated non-root user `collector` without a login shell.
- systemd: `NoNewPrivileges=yes` · `ProtectSystem=strict` · `ProtectHome=read-only` (except the data dir and `~collector/.vnstock`) · `PrivateTmp=yes` · `ReadWritePaths=` buffer only.
- Logs never contain keys, tokens or long raw messages - counts and error codes only.

### 14.5 Secrets

| Secret | Single home | Delivered by |
|---|---|---|
| vnstock API key | Secret Manager `vnstock-api-key` | On deploy, `sa-collector` reads it and writes `~collector/.vnstock/api_key.json` (mode 600). The owner enters it once |
| GCP credentials | None (D12) | Metadata server / ADC / WIF |
| Environment values (project id, bucket names) | `config/env/prod.yml` - **git-ignored**; only `*.example.yml` is committed | Read at runtime |

Code obtains secrets through **one module**, `vnmarket.common.secrets`.

### 14.6 Repository

- `.gitignore` blocks data, BI files, DuckDB, `.env*`, Terraform state and
  tfvars, and everything in `config/env/` except examples.
- pre-commit: **gitleaks** · ruff · max file size 1 MB · block data extensions outside `tests/fixtures/`.
- GitHub: secret scanning + push protection · Dependabot (pip, Actions, Terraform) · CodeQL.
- `tests/fixtures/` holds **synthetic data** generated by a seeded script.
- Commits use the GitHub **noreply** address, never a work or personal e-mail.

### 14.7 Supply chain and CI

- Dependencies locked with hashes.
- Every GitHub Action is **pinned to a commit SHA**; Dependabot bumps them.
- Every workflow declares minimal `permissions:` (default `contents: read`).
- CI does **not** need vnstock's sponsor libraries (not on PyPI, key-gated): the
  collector isolates them behind an interface; CI uses synthetic feeds.
- `pip-audit` on every PR; gitleaks over the **full history** weekly.

### 14.8 Data and warehouse

- Buckets: uniform bucket-level access · **public access prevention enforced** · versioning · never `allUsers`.
- The raw stream bucket has **no deletion lifecycle** - stream samples cannot be re-captured. Watch the 5 GB free tier.
- `dev_*` datasets: 7-day table expiration.
- README screenshots use **synthetic data** only.
- Two layers of checks (repo is public, D19): **every PR** - gitleaks on the diff, data-file block. **Before every tag** and as a `v1.0.0` condition - gitleaks over full history = 0 · no data file ever in history · no project id or e-mail in code · no user-managed service-account keys.

### 14.9 Monitoring

- Cloud Audit Logs (admin activity on by default).
- Log-based e-mail alerts on: IAM changes · service-account key creation · firewall changes.
- Budget alerts at $1 / $5.

## 15. GitHub workflow

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) - branches, commits, tags,
releases, rulesets, labels and milestones are defined there, once.
