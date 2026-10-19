# S0 feed probe - local run

Spec §6 S0. Aggregates only: no message content, no message formats (those stay with the
vendor's terms). The raw recording was deleted after these numbers were taken.

## Run

| | |
|---|---|
| When | 2026-10-19, 09:35-10:06 Vietnam time (continuous trading, morning) |
| Where | the owner's Windows machine (licensed device) - **not yet the cloud VM** |
| Subscription | 30 symbols: the point-in-time universe's 30 largest by 20-session average traded value |
| Tool | `src/vnmarket/collector/feed_probe.py --minutes 30`, then `feed_report.py`; exit 0 |

## Gate inputs

| Input | Measured |
|---|---|
| Message rate | mean 3,301 / min, peak 4,241 / min; 0 silent minutes |
| Volume | 0.60 MiB / min as text; **0.17 MiB / min** as the collector's parquet (3.4x smaller) |
| Disconnects | 0 in 31 minutes (1 connect) |
| Latency | median **about 1 s** from the message's server time to receipt (server time has 1 s resolution; the local clock was not checked against NTP) |
| Process | 183 MB peak RAM, 0.7 % CPU - fits the e2-micro's 1 GB |
| Coverage | 30 / 30 subscribed symbols delivered |
| Reference, ceiling and floor prices per symbol | **present** - the hot path can show real ceiling / floor states, which the adjusted cold path cannot |
| Foreign flow per symbol | **present** |
| Market-wide breadth (up / down, ceiling / floor counts) | **present** |
| Index levels | present, 27 indices |

## Sizing for the subscription choice (spec Q6)

Upper bounds, scaled linearly from the 30 most active symbols:

| Subscription | Symbols | Parquet per session | Per month (22 sessions) |
|---|---|---|---|
| Universe | 123 | ≤ 0.25 GiB | ≤ 5.4 GiB |
| All HOSE + HNX in scope | 556 | ≤ 1.1 GiB | ≤ 24 GiB |

Even the universe outgrows the free storage tiers (Cloud Storage 5 GB, BigQuery 10 GiB)
within one to two months: storage classes, a raw-table retention once staging has parsed
it, or a smaller subscription keep the cost near zero. Decided with Q6.

## Not answered yet

Whether the feed accepts a connection from a Google Cloud address - the gate itself
(S0.3-S0.4, the same probe on the VM). The afternoon session and the closing auction were
not part of this run.
