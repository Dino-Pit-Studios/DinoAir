#!/usr/bin/env python3
"""Fix null bytes in artifacts_db.py"""

# Read file with null bytes
with open(r"c:\Users\DinoP\Documents\DinoAir\database\artifacts_db.py", "rb") as f:
    content = f.read()

# Remove null bytes and clean up
null_bytes = b"\x00"
clean_content = content.replace(null_bytes, b"").rstrip()

print(f"Removed {content.count(null_bytes)} null bytes")
print(f"Original size: {len(content)} bytes")
print(f"Clean size: {len(clean_content)} bytes")

# Write clean content back
with open(r"c:\Users\DinoP\Documents\DinoAir\database\artifacts_db.py", "wb") as f:
    f.write(clean_content + b"\n")

print("File cleaned successfully")
