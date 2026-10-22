import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.fluent.fake import FakeFluentAdapter  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_TOKEN = "test-sidecar-token"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def fake_fluent_adapter() -> FakeFluentAdapter:
    return FakeFluentAdapter(
        {
            "residual.continuity": 0.001,
            "reference.area": 1.0,
            "reference.density": 1.225,
        }
    )


@pytest.fixture
def app_client(
    tmp_path: Path,
    fake_fluent_adapter: FakeFluentAdapter,
) -> Iterator[TestClient]:
    app = create_app(
        TEST_TOKEN,
        tmp_path / "fluent-ai-test.db",
        fluent_adapter=fake_fluent_adapter,
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return AUTH_HEADERS.copy()
