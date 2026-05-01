"""Find strings passed to .tr(...) in UI code that aren't yet in vi_VN.json.

Run from project root:
    python scripts/find_missing_tr.py
"""

import json
import os
import re

PATTERN_DOUBLE = re.compile(r'\.tr\(\s*"((?:[^"\\]|\\.)*?)"', re.DOTALL)
PATTERN_SINGLE = re.compile(r"\.tr\(\s*'((?:[^'\\]|\\.)*?)'", re.DOTALL)


def main() -> None:
    with open("resource/translations/VideoCaptioner_vi_VN.json", encoding="utf-8") as f:
        existing = set(json.load(f).keys())
    missing: set[str] = set()
    for root, _, files in os.walk("videocaptioner/ui"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for pat in (PATTERN_DOUBLE, PATTERN_SINGLE):
                for m in pat.finditer(src):
                    raw = m.group(1)
                    try:
                        decoded = raw.encode().decode("unicode_escape")
                    except UnicodeDecodeError:
                        decoded = raw
                    if decoded and decoded not in existing:
                        missing.add(decoded)
    out_path = "strings_missing.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        for s in sorted(missing):
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
        f.write(f"---\ntotal: {len(missing)}\n")
    print(f"saved {len(missing)} missing strings to {out_path}")


if __name__ == "__main__":
    main()
