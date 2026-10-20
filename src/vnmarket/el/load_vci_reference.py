"""Load Vietcap (VCI) reference data into BigQuery `raw_vnstock` by direct REST calls.

Two datasets, each from one public endpoint (config/el.yml, `vci_rest`):
- `corporate_actions`: dividends and share issues per symbol, every page, from 2000. One
  run is one snapshot (`_run_id`); staging reads the newest. A symbol whose rows differ from
  the server's own `totalElements` is a silent truncation and refuses the whole write
  (rule 9). So does a symbol with fewer events than in the newest loaded snapshot, unless
  `--allow-fewer` names the reason.
- `index_members`: today's VN30 / HNX30 lists, appended to a ledger (one row per date,
  group and symbol). No history exists anywhere, so a missed day is lost; a list whose size
  is not the configured one is refused; a date already in the ledger is not loaded twice.

No vendor library: PyPI quarantined vnstock and vnai on 2026-09-24. Every HTTP call has a
timeout, calls are paced, and N consecutive errors stop the run. Credentials: no key; the
owner's application-default credentials impersonate `sa-loader`.

Exit codes: 0 = loaded and counted (or dry run printed) · 1 = refused (truncation, shrink,
wrong list size) or load failed · 2 = usage, config or input error.

Usage:
    python -m vnmarket.el.load_vci_reference --datasets index_members            # dry run
    python -m vnmarket.el.load_vci_reference --datasets corporate_actions --limit 5
    python -m vnmarket.el.load_vci_reference --apply --datasets corporate_actions,index_members
    python -m vnmarket.el.load_vci_reference --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow as pa

from vnmarket.common.config import load_config, load_env, utf8_stdio

DATASETS = frozenset({"corporate_actions", "index_members"})
VN = dt.timezone(dt.timedelta(hours=7))
EVENT_FIELDS = {  # raw column: (source key, kind)
    "event_id": ("id", "str"),
    "event_code": ("eventCode", "str"),
    "category": ("category", "str"),
    "event_name_en": ("eventNameEn", "str"),
    "event_title_en": ("eventTitleEn", "str"),
    "public_date": ("publicDate", "date"),
    "record_date": ("recordDate", "date"),
    "exright_date": ("exrightDate", "date"),
    "issue_date": ("issueDate", "date"),
    "payout_date": ("payoutDate", "date"),
    "exercise_ratio": ("exerciseRatio", "float"),
    "value_per_share": ("valuePerShare", "float"),
}
EVENT_SCHEMA = pa.schema(
    [("symbol", pa.string())]
    + [
        (name, {"str": pa.string(), "date": pa.date32(), "float": pa.float64()}[kind])
        for name, (_, kind) in EVENT_FIELDS.items()
    ]
    + [
        ("payload_json", pa.string()),
        ("_server_total", pa.int64()),
        ("_run_id", pa.string()),
        ("_loaded_at", pa.timestamp("us", tz="UTC")),
    ]
)
MEMBER_SCHEMA = pa.schema(
    [
        ("as_of_date", pa.date32()),
        ("group_code", pa.string()),
        ("symbol", pa.string()),
        ("_loaded_at", pa.timestamp("us", tz="UTC")),
    ]
)


class InputError(Exception):
    """Config or input is not usable; nothing is loaded (exit 2)."""


class Refused(Exception):
    """The source answered, but its answer fails a guard; nothing is loaded (exit 1)."""


Getter = Callable[[str, dict], Any]  # (url, params) -> parsed JSON


def http_getter(cfg: dict, sleep: Callable[[float], None] = time.sleep) -> Getter:
    """GET with the configured headers and timeout, paced. A failed call is retried after each
    configured backoff; a call that fails every retry counts one error, and N such calls in a
    row stop the run ("source down")."""
    import requests

    session = requests.Session()
    session.headers.update(cfg["headers"])
    return retrying(
        lambda url, params: session.get(url, params=params, timeout=cfg["timeout_seconds"]),
        cfg,
        sleep,
        (requests.RequestException, ValueError),
    )


def retrying(
    call: Callable, cfg: dict, sleep: Callable[[float], None], errors_caught: tuple
) -> Getter:
    state = {"failed_in_a_row": 0}

    def get(url: str, params: dict) -> Any:
        last: Exception | None = None
        for wait in [0.0, *cfg["retry_backoff_seconds"]]:
            sleep(cfg["pause_seconds"] + wait)
            try:
                response = call(url, params)
                response.raise_for_status()
                body = response.json()
                state["failed_in_a_row"] = 0
                return body
            except errors_caught as exc:
                last = exc
        state["failed_in_a_row"] += 1
        if state["failed_in_a_row"] >= cfg["max_consecutive_errors"]:
            raise Refused(
                f"source down: {state['failed_in_a_row']} calls failed every retry, last: {last}"
            )
        raise ConnectionError(f"failed after {len(cfg['retry_backoff_seconds'])} retries: {last}")

    return get


# --- corporate actions -----------------------------------------------------------------------


def fetch_events(get: Getter, symbol: str, cfg: dict, today: dt.date) -> tuple[list[dict], int]:
    """Every DIV / ISS event of `symbol`, all pages; (rows, server total). Raises Refused when
    the rows read differ from the server's totalElements (silent truncation)."""
    ca = cfg["corporate_actions"]
    rows: list[dict] = []
    total = None
    for page in range(ca["max_pages"]):
        body = get(
            ca["url"],
            {
                "ticker": symbol,
                "fromDate": ca["from_date"],
                "toDate": today.strftime("%Y%m%d"),
                "eventCode": ca["event_codes"],
                "page": page,
                "size": ca["page_size"],
            },
        )
        data = (body or {}).get("data") or {}
        content = data.get("content") or []
        total = data.get("totalElements", total)
        rows += content
        if data.get("last", True) or not content:
            break
    if total is None:
        total = len(rows)
    if len(rows) != total:
        raise Refused(f"{symbol}: read {len(rows)} events, the server reports {total}")
    return rows, int(total)


def as_date(value: Any) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(str(value)[:10])


def as_float(value: Any) -> float | None:
    return None if value is None or value == "" else float(value)


def events_table(
    symbol: str, rows: list[dict], total: int, run_id: str, at: dt.datetime
) -> pa.Table:
    cast = {"str": lambda v: None if v is None else str(v), "date": as_date, "float": as_float}
    cols: dict[str, list] = {name: [] for name in EVENT_SCHEMA.names}
    for r in rows:
        cols["symbol"].append(symbol)
        for name, (key, kind) in EVENT_FIELDS.items():
            cols[name].append(cast[kind](r.get(key)))
        cols["payload_json"].append(json.dumps(r, ensure_ascii=False, sort_keys=True))
        cols["_server_total"].append(total)
        cols["_run_id"].append(run_id)
        cols["_loaded_at"].append(at)
    return pa.table(cols, schema=EVENT_SCHEMA)


def fewer_than_before(counts: dict[str, int], previous: dict[str, int]) -> list[str]:
    """Symbols with fewer events now than in the newest loaded snapshot: history does not
    shrink, so a drop is the source losing rows (rule 9)."""
    return sorted(s for s, n in previous.items() if s in counts and counts[s] < n)


# --- index members ----------------------------------------------------------------------------


def fetch_group(get: Getter, group: str, expected: int, cfg: dict) -> list[str]:
    body = get(cfg["index_members"]["url"], {"group": group})
    symbols = sorted({str(r["symbol"]) for r in (body or []) if r.get("symbol")})
    if len(symbols) != expected:
        raise Refused(f"{group}: {len(symbols)} symbols, expected {expected}")
    return symbols


def members_table(as_of: dt.date, lists: dict[str, list[str]], at: dt.datetime) -> pa.Table:
    rows = [(as_of, g, s) for g, symbols in lists.items() for s in symbols]
    return pa.table(
        {
            "as_of_date": [r[0] for r in rows],
            "group_code": [r[1] for r in rows],
            "symbol": [r[2] for r in rows],
            "_loaded_at": [at] * len(rows),
        },
        schema=MEMBER_SCHEMA,
    )


# --- symbols, destination ---------------------------------------------------------------------


def symbol_list(bronze_dir: Path, cfg: dict) -> list[str]:
    import pyarrow.parquet as pq

    ca = cfg["corporate_actions"]
    path = bronze_dir / "source=vnstock_data" / f"{ca['symbol_file']}.parquet"
    if not path.exists():
        raise InputError(f"symbol list missing: {path}")
    t = pq.read_table(path, columns=["symbol", "exchange", "type"]).to_pylist()
    return sorted(
        {
            r["symbol"]
            for r in t
            if r["exchange"] in ca["exchanges"] and r["type"] == ca["instrument_type"]
        }
    )


class Destination:
    """The few reads and one append the loader needs, on a dlt pipeline."""

    def __init__(self, pipeline: Any):
        self.pipeline = pipeline

    def _query(self, sql: str) -> list[tuple]:
        from dlt.destinations.exceptions import DatabaseUndefinedRelation

        try:
            with self.pipeline.sql_client() as client:
                return list(client.execute_sql(sql))
        except DatabaseUndefinedRelation:
            return []

    def _table(self, name: str) -> str:
        with self.pipeline.sql_client() as client:
            return client.make_qualified_table_name(name)

    def newest_counts(self, table: str) -> dict[str, int]:
        t = self._table(table)
        rows = self._query(
            f"select symbol, count(*) from {t} where _run_id = "  # noqa: S608 - names from config
            f"(select _run_id from {t} order by _loaded_at desc limit 1) group by symbol"
        )
        return {s: int(n) for s, n in rows}

    def dates_loaded(self, table: str) -> set[dt.date]:
        rows = self._query(f"select distinct as_of_date from {self._table(table)}")  # noqa: S608
        return {
            r[0] if isinstance(r[0], dt.date) else dt.date.fromisoformat(str(r[0])) for r in rows
        }

    def run_rows(self, table: str, column: str, value: str) -> int:
        rows = self._query(
            f"select count(*) from {self._table(table)} where {column} = '{value}'"  # noqa: S608
        )
        return int(rows[0][0]) if rows else 0

    def append(self, table: str, data: pa.Table) -> None:
        import dlt

        @dlt.resource(name=table, write_disposition="append")
        def resource():
            yield data

        self.pipeline.run(resource())


# --- runs -------------------------------------------------------------------------------------


def run_corporate_actions(
    get: Getter,
    dest: Destination | None,
    symbols: list[str],
    cfg: dict,
    today: dt.date,
    allow_fewer: str | None,
) -> int:
    run_id, at = uuid.uuid4().hex, dt.datetime.now(dt.UTC)
    tables, counts, failed = [], {}, []
    for k, symbol in enumerate(symbols, 1):
        try:
            rows, total = fetch_events(get, symbol, cfg, today)
        except Refused:
            raise
        except Exception as exc:  # noqa: BLE001 - one symbol's error is counted, not fatal
            failed.append(f"{symbol}: {type(exc).__name__}")
            continue
        counts[symbol] = len(rows)
        if rows:
            tables.append(events_table(symbol, rows, total, run_id, at))
        if k % 100 == 0:
            print(f"  {k}/{len(symbols)} symbols, {sum(counts.values())} events", flush=True)
    if failed:
        raise Refused(
            f"{len(failed)} symbols failed (no partial snapshot is written): {failed[:5]}"
        )
    print(
        f"corporate actions: {len(symbols)} symbols, {sum(counts.values())} events, "
        f"run {run_id[:8]}"
    )
    if dest is None:
        print("Dry run: nothing loaded.")
        return 0
    table = cfg["corporate_actions"]["table"]
    shrunk = fewer_than_before(counts, dest.newest_counts(table))
    if shrunk and not allow_fewer:
        raise Refused(
            f"fewer events than the newest snapshot for {len(shrunk)} symbols: {shrunk[:10]}"
        )
    if shrunk:
        print(f"⚠️ fewer events for {len(shrunk)} symbols, allowed: {allow_fewer}")
    data = pa.concat_tables(tables) if tables else EVENT_SCHEMA.empty_table()
    dest.append(table, data)
    got = dest.run_rows(table, "_run_id", run_id)
    ok = got == data.num_rows
    print(
        f"{'✅' if ok else '🔴'} snapshot {run_id[:8]}: {data.num_rows} rows sent, "
        f"{got} in the destination"
    )
    return 0 if ok else 1


def run_index_members(get: Getter, dest: Destination | None, cfg: dict, today: dt.date) -> int:
    groups = cfg["index_members"]["groups"]
    lists = {g: fetch_group(get, g, n, cfg) for g, n in groups.items()}
    for g, symbols in lists.items():
        print(f"{g}: {len(symbols)} symbols")
    if dest is None:
        print("Dry run: nothing loaded.")
        return 0
    table = cfg["index_members"]["table"]
    if today in dest.dates_loaded(table):
        print(f"✅ {today} already in the ledger; nothing loaded")
        return 0
    data = members_table(today, lists, dt.datetime.now(dt.UTC))
    dest.append(table, data)
    got = dest.run_rows(table, "as_of_date", today.isoformat())
    ok = got == data.num_rows
    print(f"{'✅' if ok else '🔴'} {today}: {data.num_rows} rows sent, {got} in the destination")
    return 0 if ok else 1


def bigquery_destination(cfg: dict, env: dict) -> Destination:
    import os

    import dlt
    from dlt.common.configuration.specs.gcp_credentials import GcpServiceAccountCredentials
    from dlt.destinations import bigquery

    from vnmarket.common.gcp import impersonated

    v1 = load_config("el")["v1_history"]
    for key, name in (
        ("HTTP_TIMEOUT", "bigquery_http_timeout_seconds"),
        ("FILE_UPLOAD_TIMEOUT", "bigquery_file_upload_timeout_seconds"),
        ("RETRY_DEADLINE", "bigquery_retry_deadline_seconds"),
    ):
        os.environ[f"DESTINATION__BIGQUERY__{key}"] = str(v1[name])
    credentials = GcpServiceAccountCredentials()
    credentials.project_id = env["gcp"]["project_id"]
    # dlt's hook for non-key credentials; private in dlt 1.30.0, pinned in pyproject.
    credentials._set_default_credentials(
        impersonated(
            env["el"]["loader_service_account"],
            v1["oauth_scope"],
            v1["impersonation_token_seconds"],
        )
    )
    credentials.resolve()
    return Destination(
        dlt.pipeline(
            pipeline_name=cfg["pipeline_name"],
            destination=bigquery(credentials=credentials, location=cfg["bq_location"]),
            dataset_name=cfg["dataset"],
        )
    )


# --- self-test --------------------------------------------------------------------------------


def fake_source(
    events: dict[str, list[dict]], totals: dict[str, int] | None = None, groups=None, page_size=2
):
    """A getter answering like the VCI endpoints: events paged `page_size` at a time, with a
    server total that may be planted to differ; group lists as given."""
    totals = totals or {}
    calls = {"n": 0}

    def get(url: str, params: dict) -> Any:
        calls["n"] += 1
        if "group" in params:
            return [{"symbol": s} for s in (groups or {}).get(params["group"], [])]
        rows = events.get(params["ticker"], [])
        page = params["page"]
        chunk = rows[page * page_size : (page + 1) * page_size]
        last = (page + 1) * page_size >= len(rows)
        return {
            "data": {
                "content": chunk,
                "totalElements": totals.get(params["ticker"], len(rows)),
                "last": last,
            }
        }

    get.calls = calls  # type: ignore[attr-defined]
    return get


def self_test() -> int:
    import dlt

    cfg = json.loads(json.dumps(load_config("el")["vci_rest"]))
    cfg["corporate_actions"]["page_size"] = 2
    cfg["index_members"]["groups"] = {"VN30": 3}
    today = dt.date(2026, 10, 21)
    ev = lambda i, code="DIV": {  # noqa: E731
        "id": f"e{i}",
        "eventCode": code,
        "exrightDate": "2026-07-23T00:00:00",
        "exerciseRatio": 0.045,
        "valuePerShare": 450,
        "publicDate": "2026-07-14T00:00:00",
    }
    events = {"AAA": [ev(1), ev(2), ev(3, "ISS")], "BBB": [], "CCC": [ev(4)]}
    checks: dict[str, bool] = {}
    rows, total = fetch_events(fake_source(events), "AAA", cfg, today)
    checks["every page is read (3 events over 2 pages)"] = len(rows) == total == 3
    try:
        fetch_events(fake_source(events, totals={"AAA": 5}), "AAA", cfg, today)
        checks["planted: rows fewer than the server's total are refused"] = False
    except Refused:
        checks["planted: rows fewer than the server's total are refused"] = True
    t = events_table("AAA", rows, 3, "r1", dt.datetime(2026, 10, 21, tzinfo=dt.UTC))
    checks["dates parsed, ratios kept, payload kept whole"] = (
        t["exright_date"][0].as_py() == dt.date(2026, 7, 23)
        and t["exercise_ratio"][0].as_py() == 0.045
        and json.loads(t["payload_json"][0].as_py())["valuePerShare"] == 450
    )
    checks["a symbol with fewer events than before is named"] = fewer_than_before(
        {"AAA": 2, "CCC": 1}, {"AAA": 3, "CCC": 1, "ZZZ": 4}
    ) == ["AAA"]
    try:
        fetch_group(fake_source({}, groups={"VN30": ["A", "B"]}), "VN30", 3, cfg)
        checks["planted: a list of the wrong size is refused"] = False
    except Refused:
        checks["planted: a list of the wrong size is refused"] = True

    with tempfile.TemporaryDirectory() as name:
        pipeline = dlt.pipeline(
            pipeline_name="self_test_vci",
            pipelines_dir=str(Path(name) / "p"),
            destination=dlt.destinations.duckdb(str(Path(name) / "d.duckdb")),
            dataset_name="raw",
        )
        dest = Destination(pipeline)
        get = fake_source(events, groups={"VN30": ["A", "B", "C"]})
        first = run_corporate_actions(get, dest, ["AAA", "BBB", "CCC"], cfg, today, None)
        loaded = dest.newest_counts(cfg["corporate_actions"]["table"])
        checks["a snapshot loads and is counted in the destination"] = first == 0 and loaded == {
            "AAA": 3,
            "CCC": 1,
        }
        shrunk = {"AAA": [ev(1)], "BBB": [], "CCC": [ev(4)]}
        try:
            run_corporate_actions(
                fake_source(shrunk), dest, ["AAA", "BBB", "CCC"], cfg, today, None
            )
            checks["planted: a shrinking history is refused before writing"] = False
        except Refused:
            checks["planted: a shrinking history is refused before writing"] = (
                dest.newest_counts(cfg["corporate_actions"]["table"]) == loaded
            )
        m1 = run_index_members(get, dest, cfg, today)
        m2 = run_index_members(get, dest, cfg, today)
        checks["index members: one ledger row per symbol, a date is never loaded twice"] = (
            m1 == m2 == 0
            and dest.run_rows(cfg["index_members"]["table"], "as_of_date", "2026-10-21") == 3
        )
        dry_calls = get.calls["n"]
        run_index_members(get, None, cfg, today)
        checks["dry run calls the source but writes nothing"] = (
            get.calls["n"] > dry_calls
            and dest.run_rows(cfg["index_members"]["table"], "as_of_date", "2026-10-21") == 3
        )

    class Resp:
        def __init__(self, ok: bool):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise ConnectionError("503")

        def json(self):
            return {"data": {"content": [], "totalElements": 0, "last": True}}

    waits: list[float] = []
    answers = iter([False, False, True])
    flaky = retrying(lambda u, p: Resp(next(answers)), cfg, waits.append, (ConnectionError,))
    flaky("u", {})
    checks["a failed call is retried after each backoff, then succeeds"] = waits == [
        cfg["pause_seconds"] + w for w in [0.0, *cfg["retry_backoff_seconds"][:2]]
    ]
    dead = retrying(lambda u, p: Resp(False), cfg, lambda s: None, (ConnectionError,))
    outcomes = []
    for _ in range(cfg["max_consecutive_errors"]):
        try:
            dead("u", {})
        except Refused:
            outcomes.append("down")
        except ConnectionError:
            outcomes.append("error")
    checks["N calls failing every retry stop the run as 'source down'"] = outcomes[
        -1
    ] == "down" and outcomes[:-1] == ["error"] * (len(outcomes) - 1)

    def failing(url: str, params: dict) -> Any:
        raise ConnectionError("down")

    try:
        run_corporate_actions(failing, None, ["AAA"], cfg, today, None)
        checks["a failed symbol stops the snapshot (no partial write)"] = False
    except Refused:
        checks["a failed symbol stops the snapshot (no partial write)"] = True
    checks["an unknown argument is rejected with exit 2"] = (
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "vnmarket.el.load_vci_reference", "--bogus"],
            capture_output=True,
            timeout=120,
        ).returncode
        == 2
    )
    print()
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def parse_datasets(text: str) -> frozenset[str]:
    names = frozenset(n.strip() for n in text.split(",") if n.strip())
    if not names or names - DATASETS:
        raise argparse.ArgumentTypeError(f"choose from {sorted(DATASETS)}")
    return names


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="load into BigQuery (default: dry run)"
    )
    parser.add_argument(
        "--datasets", type=parse_datasets, required=False, help=f"subset of {sorted(DATASETS)}"
    )
    parser.add_argument("--limit", type=int, help="dry run only: the first N symbols")
    parser.add_argument(
        "--allow-fewer", metavar="REASON", help="load although a symbol has fewer events"
    )
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    if args.self_test:
        return self_test()
    if not args.datasets:
        parser.error("--datasets is required")
    if args.apply and args.limit:
        parser.error("--limit is for dry runs only: a partial snapshot would look like a shrink")
    try:
        cfg = load_config("el")["vci_rest"]
        env = load_env()
        today = dt.datetime.now(VN).date()
        get = http_getter(cfg)
        dest = bigquery_destination(cfg, env) if args.apply else None
        code = 0
        if "index_members" in args.datasets:
            code |= run_index_members(get, dest, cfg, today)
        if "corporate_actions" in args.datasets:
            symbols = symbol_list(Path(env["v1"]["bronze_dir"]), cfg)
            code |= run_corporate_actions(
                get,
                dest,
                symbols[: args.limit] if args.limit else symbols,
                cfg,
                today,
                args.allow_fewer,
            )
        return code
    except Refused as exc:
        print(f"🔴 refused: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, KeyError, InputError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
