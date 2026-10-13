# ADR-0026: A measured v2 palette, not v1's colours

- Status: Accepted
- Date: 2026-10-13
- Spec: D21, D22

## Context

ADR-0021 inherits v1's knowledge through a reviewed harvest. v1's dashboard
colours were tuned for an HTML report on one background and were partly
corrected after the fact (the green/red heat scale was first declared
impossible, then allowed at dark steps only). The owner chose not to inherit
the values and asked for a palette grounded in colour science, vision research
and UX practice.

## Decision

- v2 keeps v1's colour **rules** (VN price-board semantics, two steps per hue,
  neutral midpoint, mandatory secondary encodings) and drops its **values**.
- Colour values live only in `config/palette.yml`, chosen in OKLCH, for a light
  and a dark theme.
- Every value is measured by `tools/check_palette.py`: WCAG 2.2 contrast,
  CIEDE2000 under normal vision and under simulated colour-vision deficiency
  (Machado 2009, severity 1.0), and OKLCH chroma for neutral midpoints. The
  thresholds sit next to the values in the config, each with its source.
- Up/down stay green/red (the VN convention), shifted toward bluish green and
  crimson and split in lightness so the pair survives red-green deficiency.
  A blue/orange colour-blind mode is not built until a reader needs it.

## Consequences

- A palette change is a config change plus a passing `check_palette.py`; CI
  runs it in `ci / lint`.
- The research basis is `docs/design/colour-and-ux-research.md`; the rules are
  in `docs/knowledge/bi-conventions.md` §4.
- Thresholds marked "calibrate" in the config are starting points, revisited
  when the first Power BI pages exist.
