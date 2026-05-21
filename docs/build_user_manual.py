"""Render docs/user_manual.html -> docs/user_manual.pdf via WeasyPrint.

Usage:
    uvx --with weasyprint python docs/build_user_manual.py

Re-run whenever docs/user_manual.html changes. WeasyPrint resolves the
`<img src="../assets/logo.png">` reference relative to the HTML file path.
"""

from pathlib import Path

from weasyprint import HTML

HERE = Path(__file__).resolve().parent
SRC = HERE / "user_manual.html"
DST = HERE / "user_manual.pdf"

HTML(filename=str(SRC), base_url=str(HERE)).write_pdf(str(DST))
print(f"wrote {DST}")
