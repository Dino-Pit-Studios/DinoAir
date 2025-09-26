#!/usr/bin/env python3
"""Add proper line ending to artifacts_db.py"""

# Read file
with open(r"c:\Users\DinoP\Documents\DinoAir\database\artifacts_db.py", "rb") as f:
    content = f.read()

# Add proper Windows line ending
content = content + b"\r\n"

# Write back
with open(r"c:\Users\DinoP\Documents\DinoAir\database\artifacts_db.py", "wb") as f:
    f.write(content)

print("Added final newline")
