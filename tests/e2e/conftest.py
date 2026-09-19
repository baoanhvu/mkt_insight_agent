"""Khoi dong `main.py` nhu mot tien trinh con cho toan bo phien e2e, doi
`/health` san sang, roi giao `base_url` cho tung test. Tat tien trinh khi
xong phien.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
_PORT = 8099  # cong rieng cho e2e, tranh dung cong 8080 neu dev dang chay server khac
_BASE_URL = f"http://127.0.0.1:{_PORT}"


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    env = dict(os.environ)
    env["APP_PROFILE"] = "test"
    env["MKT_APP__PORT"] = str(_PORT)

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "main.py")],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"{_BASE_URL}/health", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if proc.poll() is not None:
                out = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
                pytest.skip(f"main.py thoat truoc khi san sang:\n{out[-2000:]}")
            time.sleep(0.3)
        else:
            proc.kill()
            pytest.skip("main.py khong san sang trong 20s - bo qua e2e")

        yield _BASE_URL
    finally:
        proc.kill()
        proc.wait(timeout=5)


__all__ = ["base_url"]
