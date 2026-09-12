#!/usr/bin/env python3
"""Simple release tag mechanism for Neuro-Somaa."""
import subprocess
import sys
from datetime import datetime

def create_release_tag(version: str = None):
    if version is None:
        version = datetime.now().strftime("v%Y.%m.%d")
    tag_message = f"Release {version} — Automated pipeline release tag."
    subprocess.run(["git", "tag", "-a", version, "-m", tag_message], check=True)
    print(f"Created release tag: {version}")

if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else None
    create_release_tag(version)
