"""Make api.py importable without Home Assistant installed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "gree_local"))
