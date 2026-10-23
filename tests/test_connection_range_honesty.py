"""Execute JS pure helpers in Node; export tests verify provenance survives."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.analytics import session_report as sr

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'assets/range/js'


def node(code):
    if not shutil.which('node'):
        pytest.skip('Node unavailable')
    p = subprocess.run(['node', '--input-type=module', '-e', code], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def external(raw):
    source = (JS / 'websocket.js').read_text()
    start = source.index('    function extractExternalTelemetry(')
    end = source.index('    function extractShotTelemetry(', start)
    fn = source[start:end]
    return node("const handed=(v,d)=>v && typeof v==='object' ? v.right_handed : v ?? d;\n" + fn +
                '\nconsole.log(JSON.stringify(extractExternalTelemetry(' + json.dumps(raw) + ')));')


def base(**extra):
    return dict(_source='cgp', ball_speed_meters_per_second=60, vertical_launch_angle_degrees=0,
                horizontal_launch_angle_degrees=0, total_spin_rpm=3000, spin_axis_degrees=0, **extra)


def test_no_external_defaults_and_missing_club_is_missing():
    r = external({'_source': 'open_connect', 'ball_speed_meters_per_second': 50})
    assert r['simulationStatus'] == 'missing_launch_or_spin'
    for key in ('total_spin', 'spin_axis', 'verticalLaunchAngle', 'horizontalLaunchAngle',
                'clubSpeed', 'smash', 'clubPath', 'attackAngle', 'dynamicLoft', 'closureRate'):
        assert r[key] is None  # JSON.stringify(NaN), intentionally unavailable.


def test_external_zeros_preserved_and_session_shot_id_preferred():
    s = base(shotId='session-2:1', shot_number=1, open_golf_coach={'smash_factor': 0,
            'club_path_degrees': 0, 'us_customary_units': {'carry_distance_yards': 0}})
    r = external(s)
    assert r['shotId'] == 'session-2:1' and r['simulationStatus'] == 'ready'
    assert r['verticalLaunchAngle'] == r['horizontalLaunchAngle'] == r['ogcCarry'] == r['smash'] == r['clubPath'] == 0


def test_external_topspin_preserved_but_not_simulated():
    s = base(); s['total_spin_rpm'] = -3000; s['spin_axis_degrees'] = 30
    r = external(s)
    assert r['simulationStatus'] == 'unsupported_topspin'
    assert r['backspin'] < 0 and r['sidespin'] == pytest.approx(1500)


def test_external_complete_spin_components_are_enough():
    s = base(open_golf_coach={'backspin_rpm': 3000, 'sidespin_rpm': 0})
    del s['total_spin_rpm'], s['spin_axis_degrees']
    assert external(s)['simulationStatus'] == 'ready'


def test_external_recursive_estimated_alias():
    s = base(open_golf_coach={'us_customary_units': {'carry_distance_yards': 123}},
             _metric_provenance={'open_golf_coach.carry_distance_meters': {'kind': 'modelled'},
              'open_golf_coach.us_customary_units.carry_distance_yards': {'kind': 'derived', 'inputs': ['open_golf_coach.carry_distance_meters']}})
    assert external(s)['metricProvenance']['carry'] == 'modelled'


def test_physics_declines_missing_and_negative_preserves_zero_launch():
    code = (JS / 'physics.js').read_text().replace('export class', 'class')
    r = node(code + "\nconst p=new GolfPhysicsEngine(); console.log(JSON.stringify([p.calculateTrajectory({ballSpeed:100}).length,p.calculateTrajectory({ballSpeed:100,verticalLaunchAngle:0,horizontalLaunchAngle:0,total_spin:0,spin_axis:0}).length,p.calculateTrajectory({ballSpeed:100,verticalLaunchAngle:10,horizontalLaunchAngle:0,total_spin:-3000,spin_axis:0}).length]));")
    assert r[0] == r[2] == 0 and r[1] > 0


def test_metric_nan_is_muted_zero_not_missing_estimate_label():
    code = (JS / 'metrics.js').read_text().replace('export ', '')
    r = node(code + "\nconsole.log(JSON.stringify([readMetric('clubSpeed',{clubSpeed:NaN},{}), readMetric('clubPath',{clubPath:0,metricProvenance:{clubPath:'modelled'}},{})]));")
    assert r[0]['muted'] and r[1]['text'] == '+0.0' and r[1]['est']
    assert 'not measured' in r[1]['title']


def test_export_appends_provenance_and_pdf_labels(tmp_path):
    path = 'open_golf_coach.us_customary_units.carry_distance_yards'
    s = base(club='7 Iron', open_golf_coach={'us_customary_units': {'carry_distance_yards': 123}},
       _metric_provenance={'open_golf_coach.carry_distance_meters': {'kind': 'modelled'}, path: {'kind': 'derived','inputs': ['open_golf_coach.carry_distance_meters']}},
       _enrichment={'status':'enriched'})
    session = {'name':'Example','shots':[s]}
    row = sr.shot_rows(session)[0]
    assert sr.COLUMNS[-4:] == ['source','estimated_fields','metric_provenance','enrichment_status']
    assert path in json.loads(row['estimated_fields'])
    assert row['carry_yds'] == 123 and row['source'] == 'cgp' and row['enrichment_status'] == 'enriched'
    assert row['club_speed_mph'] == ''
    sr.write_csv(session,tmp_path/'report.csv')
    pages = sr.render_shot_pages(session)
    assert any(t == '123.0*' for t in pages[0].drawn)
    assert any('not measured' in t for t in pages[0].drawn)
    assert any('not measurements' in t for t in sr.render_summary_page(session).drawn)
