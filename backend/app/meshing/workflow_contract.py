"""Seven-step Watertight Geometry UI/PyFluent contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

CONTRACT_PATH = Path(__file__).with_name("workflow_schema.json")


@lru_cache(maxsize=1)
def get_watertight_workflow_contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))
