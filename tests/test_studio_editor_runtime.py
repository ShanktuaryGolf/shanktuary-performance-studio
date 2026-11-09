"""Run integrated editor state transitions without touching stored user data."""
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('args', [[], ['--projection']])
def test_editor_draft_runtime(args):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed for browser controller runtime tests')
    result = subprocess.run([node, 'tests/js/studio_editor_harness.cjs', *args], cwd=ROOT,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_presets_and_geometry_are_real_accessible_controls():
    class Controls(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()
            self.options = set()

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if 'id' in values:
                assert values['id'] not in self.ids
                self.ids.add(values['id'])
            if tag == 'option':
                self.options.add(values.get('value'))

    parser = Controls()
    parser.feed((ROOT / 'assets/config.html').read_text())
    assert {'saved', 'studio-broadcast'} <= parser.options
    assert {'studioX', 'studioY', 'studioWidth', 'studioHeight', 'studioRotation',
            'studioSnap', 'studioSave', 'studioCancel', 'studioReset',
            'studioPresetName', 'studioNamePreset'} <= parser.ids


def test_projection_preview_and_output_use_independent_rotation():
    js = (ROOT / 'assets/studio-projection.js').read_text()
    overlay = (ROOT / 'assets/overlay.html').read_text()
    assert 'rotation_deg' in js and 'rotation_deg' in overlay
    assert "editor.save()" in js and "editor.cancel()" in js
    assert "widget.rotation = 0" in js
    assert "scale" not in js  # no fabricated feet/metres calibration
    assert "msg.layout && !studioPreviewLayout" in overlay
    assert "studioPreviewLayout = true" in overlay
    assert "event.source !== window.parent" in overlay
    assert "transformOrigin:'960px 540px'" in overlay
