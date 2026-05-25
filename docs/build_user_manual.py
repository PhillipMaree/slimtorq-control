"""Render docs/user_manual.html -> docs/user_manual.pdf via WeasyPrint.

Usage:
    uvx --with weasyprint python docs/build_user_manual.py

Re-run whenever docs/user_manual.html changes. WeasyPrint resolves
`<img src="../frontend/public/logo.png">` relative to the HTML file path
(the same logo the Next.js bundle serves at /logo.png).
"""

from pathlib import Path

from weasyprint import HTML

HERE = Path(__file__).resolve().parent
SRC = HERE / "user_manual.html"
DST = HERE / "user_manual.pdf"

HTML(filename=str(SRC), base_url=str(HERE)).write_pdf(str(DST))
print(f"wrote {DST}")
