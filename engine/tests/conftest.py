from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENGINE_ROOT = PROJECT_ROOT
INFERENCE_SRC = PROJECT_ROOT / "inference" / "src"
SDK_SRC = PROJECT_ROOT / "sdk"
SHARED_SRC = PROJECT_ROOT / "shared" / "src"

for p in (ENGINE_ROOT, INFERENCE_SRC, SDK_SRC, SHARED_SRC):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
