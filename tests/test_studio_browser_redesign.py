"""Contract checks for the concept-aligned browser presentation layer."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_studio_browser_tokens_are_generated_without_recoloring_projector():
    import theme
    css = (ROOT / 'assets/theme.css').read_text()
    assert 'body.studio-browser:not(.mode-projector)' in css
    for name, value in theme.BROWSER_STUDIO.items():
        assert f'--{name}: {value};' in css
    # Physical projector still emits bright cards on an unlit black backdrop.
    assert 'body.mode-projector {' in css
    assert '--bg:          #000000;' in css
    assert '--surface:     #F2F4F7;' in css
    before = css
    subprocess.run([sys.executable, 'scripts/gen_theme_css.py'], cwd=ROOT, check=True)
    assert (ROOT / 'assets/theme.css').read_text() == before


def test_configurator_preserves_every_existing_widget_control():
    html = (ROOT / 'assets/config.html').read_text()
    for control in ('v_divot', 'v_face_impact', 'v_wbb_heatmap', 'v_wbb_cop_dot',
                    'v_wbb_force_curve', 'm_carry', 'm_club_speed', 'm_wbb_balance_bar'):
        assert f'id="{control}"' in html
    assert 'id="studioPreviewFrame"' in html
    assert 'ResizeObserver' in (ROOT / 'assets/studio-editor.js').read_text()
    assert 'Until the first shot arrives, the overlay shows sample data.' in html
    assert 'Load your saved layout before saving' in (ROOT / 'assets/studio-editor.js').read_text()
    assert 'if (!r.ok) throw new Error' in (ROOT / 'assets/studio-editor.js').read_text()


def test_browser_redesign_resources_are_local_and_all_modes_remain_available():
    for path in ('config.html', 'overlay.html', 'range/index.html'):
        html = (ROOT / 'assets' / path).read_text()
        assert '/assets/studio-browser.css' in html
        assert 'studio-browser' in html
    html = (ROOT / 'assets/range/index.html').read_text()
    modes = re.findall(r'class="game-mode-card(?: active)?" role="button" tabindex="0" data-mode="([^"]+)"', html)
    assert modes == ['practice', 'challenge', 'target_practice', 'ladder', 'closest-pin',
                     'long-drive', 'grid', 'grid_custom', 'combine']
    assert (ROOT / 'assets/range/studio-mode-landscape.svg').is_file()
    assert (ROOT / 'assets/range/studio-mode-art.js').is_file()
    assert 'card.click()' in (ROOT / 'assets/range/studio-mode-art.js').read_text()


def test_projection_setup_preserves_layout_and_labels_calibration_units():
    html = (ROOT / 'assets/config.html').read_text()
    js = (ROOT / 'assets/studio-projection.js').read_text()
    assert '/config?view=projection' in html
    assert '/assets/studio-projection.js' in html
    assert "Offsets in canvas pixels" in js
    assert 'layout.divot_calibration = {...layout.divot_calibration' in js
    assert "Number.isFinite" in js
    assert "if (!response.ok)" in (ROOT / 'assets/studio-editor.js').read_text()
    assert "saving = true" in (ROOT / 'assets/studio-editor.js').read_text()
    assert "['Divot only', '/divot']" in js
    assert "['Metric tiles only', '/tiles']" in js


def test_fresh_install_broadcast_layout_and_existing_widgets_remain_available():
    import obs_server
    layout = obs_server.DEFAULT_LAYOUT
    visible = {key for key, value in layout['widgets'].items() if value['visible']}
    assert visible == {'carry', 'total_spin', 'side_launch', 'wbb_heatmap', 'wbb_balance_bar', 'shanktuary_index'}
    assert layout['widgets']['carry']['w'] == 600
    assert 'divot' in layout['widgets'] and 'face_impact' in layout['widgets']
    js = (ROOT / 'assets/studio-layout-presets.js').read_text()
    assert 'structuredClone' in js
    assert 'studio-layout-saved' in js
    assert 'studio-layout-preview' in (ROOT / 'assets/studio-editor.js').read_text()
    assert "fetch(" not in js  # preview never persists; existing explicit Save owns it


def test_websocket_readiness_does_not_claim_monitor_connection():
    js = (ROOT / 'assets/range/js/websocket.js').read_text()
    assert "setLmStatus('Studio connected', true)" in js
    assert "Nova Connected" not in js


def test_overlay_theme_presets_stay_scoped_and_preview_only():
    import theme
    css = (ROOT / 'assets/theme.css').read_text()
    for name in theme.BROWSER_OVERLAY_THEMES:
        assert f'body.studio-browser:not(.mode-projector)[data-studio-theme="{name}"]' in css
    html = (ROOT / 'assets/overlay.html').read_text()
    assert 'event.origin !== window.location.origin' in html
    assert 'event.source !== window.parent' in html
    assert "['broadcast-dark', 'clean-light'].includes(selectedTheme)" in html


def test_configurator_uses_current_smooth_brand_mark():
    html = (ROOT / "assets/config.html").read_text()
    assert 'src="/assets/studio_brand_mark.png"' in html
    assert 'src="/assets/shanktuary_shield.png"' not in html
