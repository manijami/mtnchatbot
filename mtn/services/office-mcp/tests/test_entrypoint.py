"""The entry point must load the way anyio's to_process worker loads it.

anyio's worker re-runs the parent's ``__main__`` file by path (``runpy.run_path`` as
``__mp_main__``), so relative imports there break every tool that runs in a worker process
(inspect_workbook, analyse_workbook, create_insights_files) on the live server only.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_module_loads_by_path_like_an_anyio_worker():
    code = f"import runpy; runpy.run_path({str(ROOT / 'office_mcp' / '__main__.py')!r}, run_name='__mp_main__')"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-2000:]
