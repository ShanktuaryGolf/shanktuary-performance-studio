"""Release recipes must ship the scoring model's required, non-code data."""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_all_release_recipes_include_analytics_data():
    workflow = (ROOT / '.github/workflows/build-releases.yml').read_text()
    assert '--add-data "src/analytics/data:src/analytics/data"' in workflow
    assert '--add-data "src/analytics/data;src/analytics/data"' in workflow
    for filename in ('ShanktuaryPerformanceStudio.spec', 'shanktuary_performance_studio.spec'):
        assert "('src/analytics/data', 'src/analytics/data')" in (ROOT / filename).read_text()


def test_frozen_layout_loads_scoring_table(tmp_path, monkeypatch):
    """Simulate PyInstaller's module/data layout away from the source tree."""
    bundle = tmp_path / '_internal'
    target = bundle / 'src/analytics'
    target.mkdir(parents=True)
    shutil.copy(ROOT / 'src/analytics/flight_model.py', target / 'flight_model.py')
    shutil.copytree(ROOT / 'src/analytics/data', target / 'data')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(bundle), raising=False)
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location('frozen_flight_model', target / 'flight_model.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TABLE_PATH.is_relative_to(bundle)
    assert module.model_optimum(100) > 0
    assert module.model_optimum(150) > module.model_optimum(100)


def test_ci_requires_a_working_tk_display():
    workflow = (ROOT / '.github/workflows/build-releases.yml').read_text()
    assert 'python3-tk xvfb xauth' in workflow
    assert 'xvfb-run' in workflow
    assert 'root = tk.Tk(); root.update(); root.destroy()' in workflow
