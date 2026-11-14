import os
import tempfile
from pathlib import Path

import pytest

# Must run before `app` is imported: keep tests away from the real cache.
os.environ.setdefault("SPHEREX_CACHE_DIR", tempfile.mkdtemp(prefix="spherex-test-cache-"))

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
