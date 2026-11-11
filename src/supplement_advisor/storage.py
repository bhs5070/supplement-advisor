"""Private raw HTML files: generated paths only, never publicly mounted."""

import os
from pathlib import Path
from uuid import UUID


def store_html(root: Path, analysis_id: str, claim_token: str, html: str) -> str:
    filename = f"{UUID(analysis_id)}-{UUID(claim_token)}.html"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = root / filename
    # Each fenced attempt has its own name; an old worker cannot replace a new file.
    with destination.open("x", encoding="utf-8") as output:
        os.chmod(destination, 0o600)
        output.write(html)
    return filename
