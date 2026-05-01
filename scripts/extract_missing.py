"""Extract Chinese strings that aren't yet in the Vietnamese translation file.

Outputs:
  - missing_tr.json   — strings inside .tr(...) calls in videocaptioner/ui
  - missing_enum.json — enum value strings (Chinese) in core types/entities

Run:
    python scripts/extract_missing.py
"""

import json
import os
import re

P_DOUBLE = re.compile(r'\.tr\(\s*"((?:[^"\\]|\\.)*?)"', re.DOTALL)
P_SINGLE = re.compile(r"\.tr\(\s*'((?:[^'\\]|\\.)*?)'", re.DOTALL)
ENUM_PAT = re.compile(r'^\s*[A-Z_][A-Z_0-9]*\s*=\s*"([^"]*[一-鿿][^"]*)"', re.M)


def main() -> None:
    with open("resource/translations/VideoCaptioner_vi_VN.json", encoding="utf-8") as f:
        existing = set(json.load(f).keys())

    tr_strings: set[str] = set()
    for root, _, files in os.walk("videocaptioner/ui"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(root, fn), encoding="utf-8") as f:
                src = f.read()
            for pat in (P_DOUBLE, P_SINGLE):
                for m in pat.finditer(src):
                    raw = m.group(1)
                    # Only decode escape sequences inside the literal (\n, \t, \"…),
                    # NOT the underlying UTF-8 bytes — they are already correct text.
                    decoded = raw.encode("utf-8").decode(
                        "unicode_escape"
                    ).encode("latin-1").decode("utf-8") if "\\" in raw else raw
                    if decoded:
                        tr_strings.add(decoded)

    enum_strings: set[str] = set()
    for p in [
        "videocaptioner/core/translate/types.py",
        "videocaptioner/core/entities.py",
    ]:
        with open(p, encoding="utf-8") as f:
            src = f.read()
        for m in ENUM_PAT.finditer(src):
            enum_strings.add(m.group(1))

    missing_tr = sorted(tr_strings - existing)
    missing_enum = sorted(enum_strings - existing)

    with open("missing_tr.json", "w", encoding="utf-8") as f:
        json.dump(missing_tr, f, ensure_ascii=False, indent=2)
    with open("missing_enum.json", "w", encoding="utf-8") as f:
        json.dump(missing_enum, f, ensure_ascii=False, indent=2)

    print(f"missing tr() strings:   {len(missing_tr)}")
    print(f"missing enum values:    {len(missing_enum)}")


if __name__ == "__main__":
    main()
