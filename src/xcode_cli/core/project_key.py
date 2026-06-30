from __future__ import annotations

import os


def project_key_for_path(cwd: str) -> str:
    path = os.path.abspath(cwd)
    key = path.replace(":", "").replace("\\", "--").replace("/", "--")
    while key.startswith("-"):
        key = key[1:]
    return key or "default"
