#!/usr/bin/env python3
"""Check for quote matching issues in artifacts_db.py"""

import ast

try:
    with open(r"c:\Users\DinoP\Documents\DinoAir\database\artifacts_db.py", encoding="utf-8") as f:
        content = f.read()

    # Try to parse with AST
    ast.parse(content)
    print("✅ File parses successfully!")

except SyntaxError as e:
    print(f"❌ Syntax Error: {e}")
    print(f"Line {e.lineno}: {e.text}")
    print(f"Error at position {e.offset}")

    # Check for quote balance around the error
    lines = content.split("\n")
    start = max(0, e.lineno - 5)
    end = min(len(lines), e.lineno + 5)

    print(f"\nContext around line {e.lineno}:")
    for i in range(start, end):
        marker = " >> " if i == e.lineno - 1 else "    "
        print(f"{marker}{i + 1:3d}: {lines[i]}")
