"""Measure a colour palette against the rules in config/palette.yml.

Three measurements, all standard:
- contrast ratio (WCAG 2.2, relative luminance) between a foreground and a
  background colour;
- colour difference CIEDE2000 between two colours, under normal vision and under
  simulated colour-vision deficiency (Machado, Oliveira and Fernandes 2009,
  severity 1.0, applied in linear sRGB);
- chroma in OKLCH (Ottosson 2020), for colours that must stay neutral.

Every rule names its source and threshold in the config, not here. The report
prints the measured value next to the threshold for every pair it checks.

Exit codes: 0 = every rule holds · 1 = a rule fails, or a colour named by a rule
is missing · 2 = usage or config error.

Usage:
    python tools/check_palette.py [--config PATH]
    python tools/check_palette.py --self-test
"""

from __future__ import annotations

import argparse
import itertools
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# Machado et al. 2009, Table 1, severity 1.0 (linear RGB -> linear RGB).
CVD_MATRICES = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}
VISIONS = ("normal", *CVD_MATRICES)
# sRGB (D65) -> XYZ, IEC 61966-2-1.
SRGB_TO_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
D65_WHITE = (0.95047, 1.0, 1.08883)

Rgb = tuple[float, float, float]
Lab = tuple[float, float, float]


def parse_hex(colour: str) -> Rgb:
    value = colour.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"not a #RRGGBB colour: {colour!r}")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(m: tuple[Rgb, Rgb, Rgb], v: Rgb) -> Rgb:
    return tuple(sum(m[r][k] * v[k] for k in range(3)) for r in range(3))  # type: ignore[return-value]


def linear_rgb(colour: str, vision: str = "normal") -> Rgb:
    rgb = tuple(to_linear(c) for c in parse_hex(colour))
    if vision != "normal":
        rgb = tuple(min(1.0, max(0.0, c)) for c in mat(CVD_MATRICES[vision], rgb))
    return rgb  # type: ignore[return-value]


def luminance(colour: str) -> float:
    r, g, b = linear_rgb(colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def lab_from_linear(rgb: Rgb) -> Lab:
    xyz = mat(SRGB_TO_XYZ, rgb)

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = (f(xyz[i] / D65_WHITE[i]) for i in range(3))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def ciede2000(lab1: Lab, lab2: Lab) -> float:
    """CIEDE2000 colour difference (Sharma, Wu and Dalal 2005), kL = kC = kH = 1."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0

    dlp, dcp = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dhp_big = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))

    lp_bar, cp_bar = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    else:
        hp_bar = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(hp_bar - 30))
        + 0.24 * math.cos(math.radians(2 * hp_bar))
        + 0.32 * math.cos(math.radians(3 * hp_bar + 6))
        - 0.20 * math.cos(math.radians(4 * hp_bar - 63))
    )
    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_bar**7 / (cp_bar**7 + 25**7))
    s_l = 1 + 0.015 * (lp_bar - 50) ** 2 / math.sqrt(20 + (lp_bar - 50) ** 2)
    s_c = 1 + 0.045 * cp_bar
    s_h = 1 + 0.015 * cp_bar * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c
    return math.sqrt(
        (dlp / s_l) ** 2
        + (dcp / s_c) ** 2
        + (dhp_big / s_h) ** 2
        + r_t * (dcp / s_c) * (dhp_big / s_h)
    )


def oklch_chroma(colour: str) -> float:
    """Chroma C of OKLCH (Ottosson 2020); about 0 for a neutral grey."""
    r, g, b = linear_rgb(colour)
    lms = (
        (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3),
        (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3),
        (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3),
    )
    a = 1.9779984951 * lms[0] - 2.4285922050 * lms[1] + 0.4505937099 * lms[2]
    b_ = 0.0259040371 * lms[0] + 0.7827717662 * lms[1] - 0.8086757660 * lms[2]
    return math.hypot(a, b_)


def distance(c1: str, c2: str, vision: str = "normal") -> float:
    lab1, lab2 = (lab_from_linear(linear_rgb(c, vision)) for c in (c1, c2))
    return ciede2000(lab1, lab2)


RULE_FIELDS = {
    "contrast": ("fg", "bg", "min"),
    "distance": ("pairs", "min"),
    "distance_all": ("colours", "min"),
    "max_chroma": ("colours", "max"),
}


def config_errors(config: object) -> list[str]:
    """Structural problems that make the config unreadable (exit 2), not a failed rule."""
    if not isinstance(config, dict) or not isinstance(config.get("themes"), dict):
        return ["`themes` must be a mapping of theme name to colours"]
    if not isinstance(config.get("rules"), list):
        return ["`rules` must be a list"]
    errors = []
    for i, rule in enumerate(config["rules"]):
        kind = rule.get("kind") if isinstance(rule, dict) else None
        if kind not in RULE_FIELDS:
            errors.append(f"rule {i}: unknown kind {kind!r} (known: {', '.join(RULE_FIELDS)})")
            continue
        missing = [f for f in ("name", *RULE_FIELDS[kind]) if f not in rule]
        if missing:
            errors.append(f"rule {i}: missing {', '.join(missing)}")
        unknown_vision = set(rule.get("vision", [])) - set(VISIONS)
        if unknown_vision:
            errors.append(f"rule {i}: unknown vision {sorted(unknown_vision)}")
    for theme, colours in config["themes"].items():
        for name, value in colours.items():
            try:
                parse_hex(str(value))
            except ValueError as exc:
                errors.append(f"[{theme}] {name}: {exc}")
    return errors


def check_rule(rule: dict, colours: dict[str, str]) -> list[tuple[bool, str]]:
    """Return one (ok, line) per measured pair; KeyError names a colour that is missing."""
    lines = []
    if rule["kind"] == "contrast":
        for fg, bg in itertools.product(rule["fg"], rule["bg"]):
            value = contrast(colours[fg], colours[bg])
            lines.append((value >= rule["min"], f"{fg} on {bg}: {value:.2f}:1 (min {rule['min']})"))
    elif rule["kind"] in ("distance", "distance_all"):
        pairs = (
            rule["pairs"]
            if rule["kind"] == "distance"
            else list(itertools.combinations(rule["colours"], 2))
        )
        for (a, b), vision in itertools.product(pairs, rule.get("vision", ["normal"])):
            value = distance(colours[a], colours[b], vision)
            line = f"{a} vs {b}, {vision}: ΔE00 {value:.1f} (min {rule['min']})"
            lines.append((value >= rule["min"], line))
    else:  # max_chroma; config_errors() has rejected every other kind
        for name in rule["colours"]:
            value = oklch_chroma(colours[name])
            line = f"{name}: OKLCH chroma {value:.3f} (max {rule['max']})"
            lines.append((value <= rule["max"], line))
    return lines


def failed_rules(config: dict, report: bool = True) -> set[tuple[str, str]]:
    """Return the (theme, rule name) pairs that fail; print the report when asked."""
    failed = set()
    for theme, colours in config["themes"].items():
        for rule in config["rules"]:
            try:
                results = check_rule(rule, colours)
            except KeyError as exc:
                failed.add((theme, rule["name"]))
                if report:
                    print(f"🔴 [{theme}] {rule['name']}: colour {exc} is not defined")
                continue
            bad = [line for ok, line in results if not ok]
            if bad:
                failed.add((theme, rule["name"]))
            if report:
                symbol, passed = "🔴" if bad else "✅", len(results) - len(bad)
                print(f"{symbol} [{theme}] {rule['name']} ({passed}/{len(results)})")
                for _, line in results:
                    print(f"     {line}")
    return failed


def check(config_path: Path) -> int:
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"⚪ not run: cannot read {config_path}: {exc}", file=sys.stderr)
        return 2
    errors = config_errors(config)
    for error in errors:
        print(f"⚪ not run: {config_path}: {error}", file=sys.stderr)
    if errors:
        return 2
    return 1 if failed_rules(config) else 0


def self_test() -> int:
    """Known answers from the literature; each planted palette fails exactly its own rule."""
    # Sharma, Wu and Dalal (2005), test data pairs 1, 7, 17 and 25.
    sharma = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ]
    checks = {
        f"CIEDE2000 matches Sharma pair {i}": abs(ciede2000(a, b) - want) < 1e-4
        for i, (a, b, want) in zip((1, 7, 17, 25), sharma, strict=True)
    }
    checks["OKLCH chroma of grey is 0, of pure red is 0.258"] = (
        oklch_chroma("#808080") < 1e-6 and abs(oklch_chroma("#FF0000") - 0.2577) < 1e-3
    )
    checks["contrast black on white is 21:1"] = abs(contrast("#000000", "#FFFFFF") - 21) < 1e-9
    checks["contrast #767676 on white passes 4.5, #777777 does not"] = (
        contrast("#767676", "#FFFFFF") >= 4.5 > contrast("#777777", "#FFFFFF")
    )
    checks["simulated deficiency keeps greys grey"] = all(
        max(abs(x - y) for x, y in zip(linear_rgb(g, v), linear_rgb(g), strict=True)) < 2e-3
        for g in ("#202020", "#808080", "#E0E0E0")
        for v in CVD_MATRICES
    )
    # Protanopes lack long-wave cones, so red looks much darker to them than to
    # deuteranopes; swapping the two matrices fails this.
    red_luminance = {
        v: sum(
            w * c for w, c in zip((0.2126, 0.7152, 0.0722), linear_rgb("#FF0000", v), strict=True)
        )
        for v in ("protanopia", "deuteranopia")
    }
    checks["protanopia darkens red more than deuteranopia"] = (
        red_luminance["protanopia"] < red_luminance["deuteranopia"] / 2
    )
    checks["deuteranopia collapses pure red vs green more than normal vision"] = (
        distance("#FF0000", "#00FF00", "deuteranopia") < distance("#FF0000", "#00FF00") / 2
    )

    rules = [
        {
            "name": "text contrast",
            "kind": "contrast",
            "fg": ["text"],
            "bg": ["background"],
            "min": 4.5,
        },
        {
            "name": "up vs down",
            "kind": "distance",
            "pairs": [["up", "down"]],
            "vision": list(VISIONS),
            "min": 8,
        },
        {"name": "neutral midpoint", "kind": "max_chroma", "colours": ["neutral"], "max": 0.02},
    ]
    good = {
        "text": "#1A1A1A",
        "background": "#FFFFFF",
        "up": "#00704A",
        "down": "#E8833A",
        "neutral": "#EEEEEE",
    }
    cases = {
        "control palette fails no rule": (good, set()),
        "planted low-contrast text fails only text contrast": (
            {**good, "text": "#9A9A9A"},
            {"text contrast"},
        ),
        "planted equal-lightness red/green fails only up vs down": (
            {**good, "up": "#5F8F3A", "down": "#B8653F"},
            {"up vs down"},
        ),
        "planted yellow midpoint fails only neutral midpoint": (
            {**good, "neutral": "#F5E6A0"},
            {"neutral midpoint"},
        ),
        "planted missing colour fails only the rule that names it": (
            {k: v for k, v in good.items() if k != "down"},
            {"up vs down"},
        ),
    }
    for name, (colours, expected) in cases.items():
        got = failed_rules({"themes": {"t": colours}, "rules": rules}, report=False)
        checks[name] = {rule for _, rule in got} == expected
    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "palette.yml"
        broken.write_text(
            yaml.safe_dump({"themes": {"t": good}, "rules": [{"name": "x", "kind": "hue_angle"}]}),
            encoding="utf-8",
        )
        checks["an unknown rule kind is a config error, exit 2"] = check(broken) == 2
    checks["an unknown argument is rejected with exit 2"] = (
        subprocess.run(  # noqa: S603
            [sys.executable, __file__, "--bogus"], capture_output=True, timeout=60
        ).returncode
        == 2
    )
    print()
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--config", type=Path, default=Path("config/palette.yml"), help="palette config"
    )
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    return self_test() if args.self_test else check(args.config)


if __name__ == "__main__":
    sys.exit(main())
