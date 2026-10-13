---
name: harvest-knowledge
description: Bring a piece of v1's Vietnamese knowledge base into vn-market-elt's English docs/knowledge - check its inventory label, read the source, keep evidence levels, and keep research content out of the public repo. Use for phase K0.3, or whenever a phase needs v1 knowledge (indicators, flows, BI conventions, market rules).
---

# harvest-knowledge

Policy: ADR-0021 (inherit through a reviewed harvest) and ADR-0022 (re-select rules).
The inventory and v1's paths are local; see `CLAUDE.local.md`.

1. **Select rows.** In the private inventory, take the rows whose v2 target is the file being written.
   - `KEEP`, `LESSON` and `V1-RULE→rewrite` come in.
   - `STALE` and `V1-RULE→drop` stay out.
   - `RESEARCH` goes to the private repository only.

   Done when the row list and the skipped rows (with reasons) are written down.

2. **Read the source.** Open each v1 section at its line number. v1 is read-only. Prefer the latest, corrected version of a fact.
   Done when every selected row has been read in full, not taken from the inventory note.

3. **Write.** Write condensed English.
   - Every fact carries an evidence tag: ✅ · ⚠️ · ❓ · `measured on v1, <date>`, with its population.
   - Every fact carries a v1 source reference.
   - State what to do, not what to avoid.

   Done when each selected row maps to text or to a recorded skip.

4. **Keep the public repo clean.** These stay out:
   - strategy, signal, backtest or hypothesis numbers;
   - vendor-internal licence or feed mechanics;
   - local paths, account tiers and private names.

   Done when `python tools/secret_scan.py` exits 0 with no warnings, and a read-through finds none of the above.

5. **Glossary first.** Every new code term is added to `docs/glossary.md` before it is used.
   Done when no new term is missing.

6. **Route.** Update the status in `docs/knowledge/README.md`, the routing in `docs/domain.md` and spec §0.
   Done when the new file is reachable from `CLAUDE.md` → `docs/domain.md`.

Then continue with `ship-pr`.
