import copy
import math

import pytest

from src.connections.enrichment import OGC_VERSION, calibration_shot, enrich_shot


def shot(**kw):
    result = dict(_source='open_connect', ball_speed_meters_per_second=70,
                  vertical_launch_angle_degrees=13, horizontal_launch_angle_degrees=0,
                  total_spin_rpm=2700, spin_axis_degrees=0)
    result.update(kw)
    return result


def engine(inputs):
    assert all(k in inputs for k in ('ball_speed_meters_per_second', 'vertical_launch_angle_degrees',
               'horizontal_launch_angle_degrees', 'total_spin_rpm', 'spin_axis_degrees'))
    return {'open_golf_coach': {'carry_distance_meters': 210, 'total_distance_meters': 220,
            'offline_distance_meters': 0, 'peak_height_meters': 25, 'descent_angle_degrees': 40,
            'hang_time_seconds': 6, 'club_speed_meters_per_second': 48, 'smash_factor': 1.458,
            'club_path_degrees': {'right_handed': 1, 'left_handed': -1},
            'angle_of_attack_degrees': 2, 'dynamic_loft_degrees': 12, 'face_contact': {'x': 2}}}


def forbidden(_):
    pytest.fail('engine must not run')


def test_off_only_tags_and_never_mutates():
    s = shot(); old = copy.deepcopy(s)
    r = enrich_shot(s, calculator=forbidden)
    assert s == old and 'open_golf_coach' not in r and '_enrichment' not in r


def test_preserve_zero_reported_and_raw():
    s = shot(open_golf_coach={'carry_distance_meters': 0, 'smash_factor': 0, 'club_path_degrees': 0})
    old = copy.deepcopy(s)
    r = enrich_shot(s, enabled=True, estimate_club=True, calculator=engine)
    assert s == old and r['_enrichment']['raw_shot'] == old
    for key in ('carry_distance_meters', 'smash_factor', 'club_path_degrees'):
        assert r['open_golf_coach'][key] == 0


def test_root_and_imperial_values_win():
    r = enrich_shot(shot(carry_distance_meters=0, smash_factor=0,
        open_golf_coach={'us_customary_units': {'total_distance_yards': 5}}), enabled=True, estimate_club=True, calculator=engine)
    assert 'carry_distance_meters' not in r['open_golf_coach']
    assert 'smash_factor' not in r['open_golf_coach']
    assert r['open_golf_coach']['total_distance_meters'] == pytest.approx(4.572)


@pytest.mark.parametrize('field', ['ball_speed_meters_per_second', 'vertical_launch_angle_degrees',
                                  'horizontal_launch_angle_degrees', 'total_spin_rpm', 'spin_axis_degrees'])
def test_missing_never_zero_filled(field):
    s = shot(); del s[field]
    r = enrich_shot(s, enabled=True, calculator=forbidden)
    assert r['_enrichment']['reason'] == 'missing_inputs'
    assert 'carry_distance_meters' not in r.get('open_golf_coach', {})


@pytest.mark.parametrize('bad', [True, None, '70', float('nan'), float('inf')])
def test_invalid_input_declines(bad):
    r = enrich_shot(shot(ball_speed_meters_per_second=bad), enabled=True, calculator=forbidden)
    assert r['_enrichment']['reason'] == 'missing_inputs'


def test_component_spin_complete():
    s = shot(); del s['total_spin_rpm'], s['spin_axis_degrees']
    s['open_golf_coach'] = {'backspin_rpm': 3000, 'sidespin_rpm': 300}
    r = enrich_shot(s, enabled=True, calculator=engine)
    assert r['total_spin_rpm'] == pytest.approx(math.hypot(3000, 300))
    assert r['_enrichment']['status'] == 'enriched'


def test_cgp_negative_total_not_changed_and_model_declined():
    r = enrich_shot(shot(_source='cgp', total_spin_rpm=-3000, spin_axis_degrees=30), enabled=True, calculator=forbidden)
    assert r['total_spin_rpm'] == -3000
    assert r['open_golf_coach']['sidespin_rpm'] == pytest.approx(1500)
    assert r['open_golf_coach']['backspin_rpm'] < 0
    assert r['_enrichment']['reason'] == 'topspin_not_supported_by_ogc_adapter'


def test_spin_conflict_declines():
    r = enrich_shot(shot(open_golf_coach={'backspin_rpm': 100, 'sidespin_rpm': 5}), enabled=True, calculator=forbidden)
    assert r['_enrichment']['reason'] == 'inconsistent_spin_representations'


def test_club_separate_toggle_no_invented_metrics():
    r = enrich_shot(shot(), enabled=True, calculator=engine)
    for field in ('club_speed_meters_per_second', 'club_path_degrees', 'angle_of_attack_degrees', 'dynamic_loft_degrees', 'face_contact'):
        assert field not in r['open_golf_coach']
    r = enrich_shot(shot(), enabled=True, estimate_club=True, calculator=engine)
    assert r['_metric_provenance']['open_golf_coach.club_speed_meters_per_second']['kind'] == 'modelled'


def test_clamped_speed_smash_suppressed():
    r = enrich_shot(shot(ball_speed_meters_per_second=30), enabled=True, estimate_club=True, calculator=engine)
    assert r['_enrichment']['club_estimate_saturated']
    assert 'smash_factor' not in r['open_golf_coach']
    assert 'club_speed_meters_per_second' not in r['open_golf_coach']


def test_reported_speed_drives_smash():
    r = enrich_shot(shot(open_golf_coach={'club_speed_meters_per_second': 50}), enabled=True, estimate_club=True, calculator=engine)
    assert r['open_golf_coach']['smash_factor'] == 1.4
    assert r['_metric_provenance']['open_golf_coach.smash_factor']['kind'] == 'derived'


def test_provenance_calibration_and_estimated_off():
    s = shot(_source='cgp', _cgp={'estimated_fields': ['horizontal_launch_angle_degrees']})
    r = enrich_shot(s, enabled=True, calculator=engine)
    for path in r['_enrichment']['modelled_fields']:
        meta = r['_metric_provenance'][path]
        assert meta['version'] == OGC_VERSION and not meta['calibration_ground_truth']
        assert meta['inputs'] and meta['assumptions'] and 'confidence' not in meta
    c = calibration_shot(r)
    assert 'open_golf_coach' not in c and 'horizontal_launch_angle_degrees' not in c
    assert enrich_shot(s)['_metric_provenance']['horizontal_launch_angle_degrees']['kind'] == 'source_estimated'


def test_mapper_provenance_preserved():
    path = 'open_golf_coach.us_customary_units.ball_speed_mph'
    s = shot(_source='cgp', _cgp={'derived_fields': [path]},
             open_golf_coach={'us_customary_units': {'ball_speed_mph': 150}},
             _metric_provenance={'total_spin_rpm': {'kind': 'source_estimated'}})
    r = enrich_shot(s)
    assert r['_metric_provenance'][path]['kind'] == 'derived'
    assert r['_metric_provenance']['total_spin_rpm']['kind'] == 'source_estimated'


def test_repeat_uses_raw_not_estimates():
    r = enrich_shot(shot(), enabled=True, calculator=engine)
    assert enrich_shot(r, enabled=True, calculator=engine) == r
    assert '_enrichment' not in r['_enrichment']['raw_shot']


def test_engine_failure_keeps_shot():
    def broken(_):
        raise ImportError('missing')
    r = enrich_shot(shot(), enabled=True, calculator=broken)
    assert r['_enrichment']['status'] == 'unavailable' and r['ball_speed_meters_per_second'] == 70


def test_invalid_engine_output_filtered():
    def invalid(_):
        return {'open_golf_coach': {'carry_distance_meters': float('nan'), 'total_distance_meters': -5, 'club_speed_meters_per_second': True}}
    r = enrich_shot(shot(), enabled=True, estimate_club=True, calculator=invalid)
    assert 'carry_distance_meters' not in r['open_golf_coach'] and 'club_speed_meters_per_second' not in r['open_golf_coach']


def test_zero_spin_does_not_create_path():
    r = enrich_shot(shot(total_spin_rpm=0), enabled=True, estimate_club=True, calculator=engine)
    assert 'club_path_degrees' not in r['open_golf_coach']
    r = enrich_shot(shot(total_spin_rpm=0, spin_axis_degrees=10), enabled=True, calculator=forbidden)
    assert r['_enrichment']['reason'] == 'inconsistent_zero_spin_axis'


def test_pressure_and_invalid_environment():
    def check(inputs):
        assert inputs['pressure_pascals'] == 99000
        return engine(inputs)
    assert enrich_shot(shot(pressure_pascals=99000), enabled=True, calculator=check)['_enrichment']['status'] == 'enriched'
    assert enrich_shot(shot(pressure_pascals=-1), enabled=True, calculator=forbidden)['_enrichment']['reason'] == 'invalid_environment'


def test_real_pinned_engine():
    module = pytest.importorskip('opengolfcoach')
    assert module.__version__ == OGC_VERSION
    r = enrich_shot(shot(), enabled=True)
    assert r['_enrichment']['status'] == 'enriched'
    assert 150 < r['open_golf_coach']['carry_distance_meters'] < 300
    assert r['open_golf_coach']['offline_distance_meters'] == pytest.approx(0)
    assert 'club_speed_meters_per_second' not in r['open_golf_coach']
