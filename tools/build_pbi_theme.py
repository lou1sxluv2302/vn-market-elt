"""Write the Power BI report theme from `config/palette.yml` (BI plan B3; ADR-0026).

The palette is the only place colours live; this tool maps its roles onto Power BI's theme
slots (bi-conventions §4) so the report never carries a hand-typed colour:

    dataColors[0..4]          cat_1..cat_5   series identity only, never price meaning
    good / bad / neutral      up / down / neutral
    maximum / center / minimum  up_strong / neutral / down_strong  (diverging heat)
    background, foreground, tableAccent, text classes   background, text, surface, text_muted

`ceiling`, `floor` and `reference` are not theme slots: they belong to the intraday pages
and are applied by role there. Only themes the palette defines are written.

Exit codes: 0 = written · 2 = usage or palette error.

Usage:
    python tools/build_pbi_theme.py --theme light --out <path>.json
    python tools/build_pbi_theme.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

from vnmarket.common.config import load_config, utf8_stdio

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
FONT = "Segoe UI"


def theme_json(palette: dict, theme: str) -> dict:
    """The Power BI theme for one palette theme (light or dark)."""
    c = palette["themes"][theme]
    for role, value in c.items():
        if not HEX.match(value):
            raise ValueError(f"{theme}.{role} is not #RRGGBB: {value!r}")

    def text(size: int, color: str) -> dict:
        return {"fontFace": FONT, "fontSize": size, "color": c[color]}

    return {
        "name": f"vn-market-elt {theme}",
        "dataColors": [c[f"cat_{i}"] for i in range(1, 6)],
        "background": c["background"],
        "foreground": c["text"],
        "tableAccent": c["surface"],
        "good": c["up"],
        "bad": c["down"],
        "neutral": c["neutral"],
        "maximum": c["up_strong"],
        "center": c["neutral"],
        "minimum": c["down_strong"],
        "textClasses": {
            "callout": text(24, "text"),
            "title": text(12, "text"),
            "header": text(11, "text"),
            "label": text(9, "text_muted"),
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"color": {"solid": {"color": c["background"]}}}],
                }
            },
            "page": {
                "*": {
                    "background": [{"color": {"solid": {"color": c["background"]}}}],
                }
            },
        },
    }


def self_test() -> int:
    import subprocess

    palette = load_config("palette")
    light = theme_json(palette, "light")
    c = palette["themes"]["light"]
    planted = {"themes": {"light": {**c, "up": "green"}}}
    try:
        theme_json(planted, "light")
        rejected = False
    except ValueError:
        rejected = True
    every_colour = re.findall(r"#[0-9A-Fa-f]{6}", json.dumps(light))
    checks = {
        "series colours are the five categorical roles, in order": light["dataColors"]
        == [c[f"cat_{i}"] for i in range(1, 6)],
        "good / bad are up / down; the diverging scale is down_strong - neutral - up_strong": (
            light["good"],
            light["bad"],
            light["minimum"],
            light["center"],
            light["maximum"],
        )
        == (c["up"], c["down"], c["down_strong"], c["neutral"], c["up_strong"]),
        "every colour in the theme comes from the palette": set(every_colour) <= set(c.values()),
        "ceiling, floor and reference are not theme slots": not {
            c["ceiling"],
            c["floor"],
        }
        & set(every_colour),
        "planted: a colour that is not #RRGGBB is refused": rejected,
        "an unknown argument is rejected with exit 2": subprocess.run(  # noqa: S603
            [sys.executable, __file__, "--bogus"], capture_output=True, timeout=120, check=False
        ).returncode
        == 2,
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "t.json"
        code = subprocess.run(  # noqa: S603 - this script, fixed arguments
            [sys.executable, __file__, "--theme", "light", "--out", str(out)],
            capture_output=True,
            timeout=120,
            check=False,
        ).returncode
        checks["the CLI writes valid JSON"] = code == 0 and json.loads(out.read_text("utf-8"))[
            "name"
        ].endswith("light")
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--theme", choices=["light", "dark"], help="palette theme to write")
    parser.add_argument("--out", type=Path, help="theme JSON to write")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not (args.theme and args.out):
        parser.error("--theme and --out are required")
    try:
        theme = theme_json(load_config("palette"), args.theme)
    except (KeyError, ValueError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(theme, indent=2) + "\n", "utf-8")
    print(f"✅ {args.theme} theme -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
