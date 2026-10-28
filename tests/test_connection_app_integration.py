import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT=Path(__file__).resolve().parents[1]


def method(name):
    tree=ast.parse((ROOT/'shanktuary_performance_studio.py').read_text())
    for node in ast.walk(tree):
        if isinstance(node,ast.FunctionDef) and node.name==name:
            return node
    raise AssertionError(name)


def test_signed_spin_not_flagged_for_new_sources():
    node=method('validate_shot_payload')
    node.decorator_list=[]
    env={};exec(compile(ast.Module(body=[node],type_ignores=[]),'test','exec'),env)
    for source in ('cgp','open_connect'):
        shot={'_source':source,'total_spin_rpm':-3000,'open_golf_coach':{'backspin_rpm':-3000}}
        env['validate_shot_payload'](None,shot)
        assert not shot.get('_data_quality')


def test_pipeline_enriches_before_history_and_filters_generation():
    source=ast.unparse(method('_process_queued_shot'))
    assert source.index('source_connections.accepts')<source.index('enrich_shot')<source.index("sess['shots'].append")
    assert 'calibration_shot(msg)' in source
    assert "calibration.get('horizontal_launch_angle_degrees') is not None" in source


def test_input_start_explicit_and_shutdown_stop():
    source=(ROOT/'shanktuary_app.py').read_text()
    assert 'source_connections.start(' not in source
    assert 'ConnectionWizard(' in source and 'source_connections.stop()' in source
    assert 'SPS_UI_PREVIEW' in source


def test_source_neutral_view_clears_contact_and_keeps_zero():
    from src.connections.metric_view import draw_connection_metrics
    canvas=Mock()
    app=SimpleNamespace(canvas=canvas,current_shot={'_source':'cgp','vertical_launch_angle_degrees':0},
                        aim_corrected=lambda shot:shot,contact_face_rect=(1,2,3,4),
                        contact_face_geometry={},contact_clear_rect=(1,2,3,4))
    draw_connection_metrics(app,900,800)
    assert app.contact_face_rect is app.contact_face_geometry is app.contact_clear_rect is None
    text=[call.kwargs.get('text') for call in canvas.create_text.call_args_list]
    assert '--' in text and '0.0 °' in text


def test_frozen_entrypoints_and_optional_package_markers():
    for spec in ROOT.glob('*.spec'):
        text=spec.read_text()
        assert 'shanktuary_app.py' in text and "hookspath=['hooks']" in text
    assert 'copy_metadata("opengolfcoach")' in (ROOT/'hooks/hook-opengolfcoach.py').read_text()
    req=(ROOT/'requirements.txt').read_text()
    assert 'aioquic==1.2.0' in req and 'opengolfcoach==0.3.0;' in req
    assert 'platform_machine == "arm64"' in req


def test_release_workflow_requires_all_builds_and_explicit_approved_commit():
    text = (ROOT / '.github/workflows/build-releases.yml').read_text()
    build, release = text.split('  release:\n', 1)
    assert 'softprops/action-gh-release' not in build
    assert 'needs: [test, build]' in release
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in release
    assert "github.event.head_commit.message == 'Release v1.8.1: fix Pillow Tk packaging'" in release
    assert 'RELEASE_TAG: v1.8.1' in release
    assert 'draft: true' in release
    assert 'fail_on_unmatched_files: true' in release
    assert "if: steps.release_check.outputs.publish == 'true'" in release
    assert release.index('PYVERIFY\n') < release.index('gh release edit')
    for name in ('Shanktuary-Studio-Linux-x64.tar.gz', 'Shanktuary-Studio-Windows-x64.zip',
                 'Shanktuary-Studio-macOS.zip', 'Shanktuary-Studio-x86_64.AppImage',
                 'SHA256SUMS.txt'):
        assert 'release-assets/' + name in release
