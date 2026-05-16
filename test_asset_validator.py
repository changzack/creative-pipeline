"""
Regression tests for validate_asset_references() — the regex/normalization
parser that was misreading slugs containing parentheses, producing false
"missing asset" + "asset under-utilization" reports in the
quiz-wars-bold-unified-20260516-111715 run.

Run:  python test_asset_validator.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import validate_asset_references  # noqa: E402

import pipeline as _p  # to reset the compiled regex between test runs

PASSED: list[str] = []
FAILED: list[str] = []


def _reset_regex():
    _p._ASSET_URL_RE = None


def _run(name: str, html: str, manifest: list[dict], expect_matched: set[str], expect_missing: set[str]):
    _reset_regex()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        h = td / "x.html"
        h.write_text(html)
        m = td / "manifest.json"
        m.write_text(json.dumps(manifest))
        result = validate_asset_references(h, m)
    got_matched = set(result["matched"])
    got_missing = set(result["missing"])
    if got_matched == expect_matched and got_missing == expect_missing:
        PASSED.append(name)
        print(f"  ✓ {name}")
    else:
        FAILED.append(name)
        print(f"  ✗ {name}")
        print(f"    expected matched={expect_matched} missing={expect_missing}")
        print(f"    got      matched={got_matched} missing={got_missing}")


print("test_asset_validator")

# 1. Quoted asset:// with parens in name (img src style)
_run(
    "quoted-img-src-with-parens",
    html='<img src="asset://badge-glyph-set-(3-tiers)">',
    manifest=[{"name": "badge-glyph-set-(3-tiers)"}],
    expect_matched={"badge-glyph-set-(3-tiers)"},
    expect_missing=set(),
)

# 2. Unquoted CSS url(asset://name-with-(parens))
_run(
    "css-url-unquoted-with-parens",
    html='.x { background: url(asset://daily-plate-backdrop-(q4-reveal-background)); }',
    manifest=[{"name": "daily-plate-backdrop-(q4-reveal-background)"}],
    expect_matched={"daily-plate-backdrop-(q4-reveal-background)"},
    expect_missing=set(),
)

# 3. CSS url('asset://name') quoted (parens come from url() wrapper, not slug)
_run(
    "css-url-quoted-no-paren-in-slug",
    html=".x { background: url('asset://plain-slug'); }",
    manifest=[{"name": "plain-slug"}],
    expect_matched={"plain-slug"},
    expect_missing=set(),
)

# 4. Extension variants
_run(
    "ext-variant-jpg",
    html='<img src="asset://hero-shot.jpg">',
    manifest=[{"name": "hero-shot"}],
    expect_matched={"hero-shot"},
    expect_missing=set(),
)
_run(
    "ext-variant-png",
    html='<img src="asset://hero-shot.png">',
    manifest=[{"name": "hero-shot"}],
    expect_matched={"hero-shot"},
    expect_missing=set(),
)
_run(
    "ext-variant-webp",
    html='<img src="asset://hero-shot.webp">',
    manifest=[{"name": "hero-shot"}],
    expect_matched={"hero-shot"},
    expect_missing=set(),
)

# 5. Percent-encoded unicode slugs (em-dash, etc.)
_run(
    "percent-encoded-em-dash",
    html='<img src="asset://shoe-photo-%E2%80%94-bred.jpg">',
    manifest=[{"name": "shoe-photo-—-bred"}],
    expect_matched={"shoe-photo-—-bred"},
    expect_missing=set(),
)

# 6. True hallucinated slug must NOT match
_run(
    "hallucinated-slug-must-miss",
    html='<img src="asset://this-was-never-commissioned">',
    manifest=[{"name": "real-asset-one"}],
    expect_matched=set(),
    expect_missing={"this-was-never-commissioned"},
)

# 7. Mixed: real-with-parens + hallucinated in same HTML
_run(
    "mixed-real-and-hallucinated",
    html=(
        '<img src="asset://avatar-default-(monogram-fallback)">'
        '<div style="background:url(asset://made-up-thing)"></div>'
    ),
    manifest=[{"name": "avatar-default-(monogram-fallback)"}],
    expect_matched={"avatar-default-(monogram-fallback)"},
    expect_missing={"made-up-thing"},
)

# 8. Trailing punctuation noise: only peel when peel produces a hit
_run(
    "peel-only-when-peel-helps",
    html='var s = "asset://real-slug";',
    manifest=[{"name": "real-slug"}],
    expect_matched={"real-slug"},
    expect_missing=set(),
)

# 9. Repro of the failing run's exact concept-1 manifest names
_run(
    "quiz-wars-concept-1-repro",
    html=(
        '<img src="asset://daily-plate-backdrop-(q4-reveal-background)">'
        '<div style=\'background:url("asset://complex-quiz-wars-mark-(logo-lockup-for-share-card-top-left)")\'></div>'
        '<img src="asset://avatar-default-(monogram-fallback).png">'
        '<img src="asset://badge-glyph-set-(3-monochrome-diamond-marks)">'
        '<img src="asset://share-card-edge-bleed-mark-(bottom-right-corner-of-q5)">'
    ),
    manifest=[
        {"name": "daily-plate-backdrop-(q4-reveal-background)"},
        {"name": "complex-quiz-wars-mark-(logo-lockup-for-share-card-top-left)"},
        {"name": "avatar-default-(monogram-fallback)"},
        {"name": "badge-glyph-set-(3-monochrome-diamond-marks)"},
        {"name": "share-card-edge-bleed-mark-(bottom-right-corner-of-q5)"},
    ],
    expect_matched={
        "daily-plate-backdrop-(q4-reveal-background)",
        "complex-quiz-wars-mark-(logo-lockup-for-share-card-top-left)",
        "avatar-default-(monogram-fallback)",
        "badge-glyph-set-(3-monochrome-diamond-marks)",
        "share-card-edge-bleed-mark-(bottom-right-corner-of-q5)",
    },
    expect_missing=set(),
)

print()
print(f"passed: {len(PASSED)}  failed: {len(FAILED)}")
if FAILED:
    print("FAIL:", FAILED)
    sys.exit(1)
print("OK")
