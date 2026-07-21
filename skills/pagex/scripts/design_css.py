#!/usr/bin/env python3
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSET_DIR = SKILL_DIR / "assets"
FONT_SPECS = (
    ("cormorant-garamond-latin.woff2.b64", "Cormorant Garamond", "normal", "400 600"),
    ("newsreader-latin.woff2.b64", "Newsreader", "normal", "400 600"),
    ("newsreader-italic-latin.woff2.b64", "Newsreader", "italic", "400"),
)
BASE_CSS = """
:root {
  color-scheme: light;
  --paper: #f1efe8;
  --paper-deep: #e8e5dc;
  --ink: #1b1b18;
  --muted: #6d6a61;
  --line: #c7c3b8;
  --signal: #b83a20;
  --display: 'Cormorant Garamond', 'Iowan Old Style', 'Palatino Linotype', Georgia, serif;
  --body: 'Newsreader', 'Iowan Old Style', 'Palatino Linotype', Georgia, serif;
  --ui: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  --mono: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--body);
  font-optical-sizing: auto;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}
h1, h2, h3, h4 {
  font-family: var(--display);
  font-optical-sizing: auto;
  font-weight: 600;
  text-wrap: balance;
}
p, li, dd { line-height: 1.58; }
strong { font-weight: 600; }
code, kbd, pre, samp { font-family: var(--mono); }
""".strip()


def load_font(filename: str, expected_sha256: str) -> str:
    payload = (ASSET_DIR / filename).read_text(encoding="ascii").strip()
    try:
        font = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as error:
        raise SystemExit(f"invalid base64 font asset: {filename}") from error
    if not font.startswith(b"wOF2"):
        raise SystemExit(f"font asset is not WOFF2: {filename}")
    if hashlib.sha256(font).hexdigest() != expected_sha256:
        raise SystemExit(f"font asset checksum mismatch: {filename}")
    return payload


def main() -> None:
    metadata = {
        item["file"]: item
        for item in json.loads((ASSET_DIR / "fonts.json").read_text(encoding="utf-8"))
    }
    blocks = []
    for filename, family, style, weight in FONT_SPECS:
        item = metadata[filename]
        payload = load_font(filename, item["sha256"])
        blocks.append(
            "\n".join(
                (
                    "@font-face {",
                    f"  font-family: '{family}';",
                    f"  src: url(data:font/woff2;base64,{payload}) format('woff2');",
                    f"  font-style: {style};",
                    f"  font-weight: {weight};",
                    "  font-display: swap;",
                    "}",
                )
            )
        )
    print("\n".join((*blocks, BASE_CSS)))


if __name__ == "__main__":
    main()
