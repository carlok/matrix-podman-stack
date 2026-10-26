from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bots" / "example_bot"))
sys.path.insert(0, str(ROOT / "scripts"))
