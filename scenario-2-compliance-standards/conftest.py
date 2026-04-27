"""
pytest conftest — Scenario 2.

Adds the scenario directory and repo root to sys.path so that
'agent' and 'shared' packages are importable from tests.
"""
import sys
from pathlib import Path

_scenario_dir = Path(__file__).resolve().parent   # scenario-2-compliance-standards/
_repo_root = _scenario_dir.parent                  # ai-devsecops-showcase/

for _p in [str(_repo_root), str(_scenario_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
