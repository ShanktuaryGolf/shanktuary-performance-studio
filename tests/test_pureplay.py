import json
import queue
import time

import pytest

from src.connections.controller import SourceConnections
from src.connections.presentation import metric_status, metric_value
from src.connections.pureplay import PureplayPoller, map_pureplay_shot_to_sps_payload
from src.processing.pressure.trace_store import shot_trace_id


def shot(id='one', **kwargs):
    return dict(shotId=id, sessionId='session', bFromLaunchMonitor=True,
                ballSpeed=50, ballSpeedRaw=40, vLA=12, hLA=0, totalSpin=3000,
                spinAxis=0, carryDistanceM=150, totalDistanceM=160,
                restTime='2026.11.08-18.00.00', **kwargs)


def write(root, shots, name='session-a.json'):
    p=root/'0'/'shots'/name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(schemaVersion=1,sessionId='session',shots=shots)), encoding='utf-8')
    return p


def test_mapper_units_provenance_identity():
    raw=shot(attackAngle=0,clubHeadSpeed=25,apexHeightM=0)
    mapped,_=map_pureplay_shot_to_sps_payload(raw)
    assert mapped['ball_speed_meters_per_second']==40
    assert metric_value(mapped,'carry')==pytest.approx(150/.9144)
    assert metric_status(mapped,'carry')=='ESTIMATED'
    assert metric_status(mapped,'launch')=='REPORTED'
    assert metric_value(mapped,'attack_angle') is None
    assert metric_value(mapped,'club_speed') is None
    assert metric_value(mapped,'apex') is None
    assert shot_trace_id(mapped).startswith('pureplay-')
    other,_=map_pureplay_shot_to_sps_payload(shot('two'))
    assert shot_trace_id(other)!=shot_trace_id(mapped)
    assert raw['ballSpeed']==50


@pytest.mark.parametrize('change',[{'ballSpeedRaw':float('nan')},{'ballSpeedRaw':True},{'hLA':999},{'restTime':''},
    {'shotId':''},{'sessionId':None}])
def test_mapper_rejects_unusable(change):
    raw=shot();raw.update(change)
    with pytest.raises(ValueError):map_pureplay_shot_to_sps_payload(raw)


def test_baseline_new_shots_simulation_and_dedup(tmp_path):
    events=[];old=shot('old');write(tmp_path,[old])
    reader=PureplayPoller(lambda p,m:events.append(p),tmp_path)
    reader.poll_once();assert not events
    fake=shot('fake');fake['bFromLaunchMonitor']=False
    write(tmp_path,[old,fake,shot()]);reader.poll_once();reader.poll_once()
    assert len(events)==2 and reader.status()['shot_received']
    # Same shot in another file must not duplicate it.
    write(tmp_path,[shot()],name='session-copy.json');reader.poll_once()
    assert len(events)==2


def test_partial_write_retries_and_existing_broken_file_baselines(tmp_path):
    events=[];path=write(tmp_path,[]);path.write_text('{',encoding='utf-8')
    reader=PureplayPoller(lambda p,m:events.append(p),tmp_path)
    reader.poll_once();write(tmp_path,[shot('old')]);reader.poll_once()
    assert not events
    path.write_text('{',encoding='utf-8');reader.poll_once()
    write(tmp_path,[shot('old'),shot('new')]);reader.poll_once()
    assert len(events)==1


def test_new_session_and_unfinished_shot(tmp_path):
    tmp_path.mkdir(exist_ok=True);events=[]
    reader=PureplayPoller(lambda p,m:events.append(p),tmp_path);reader.poll_once()
    pending=shot();pending['restTime']=''
    write(tmp_path,[pending]);reader.poll_once();assert not events
    write(tmp_path,[shot()]);reader.poll_once();assert len(events)==1


def test_restart_does_not_replay(tmp_path):
    write(tmp_path,[shot()]);events=[]
    reader=PureplayPoller(lambda p,m:events.append(p),tmp_path,poll_interval=.01)
    reader.start();reader.stop();reader.start();reader.stop()
    assert not events


def test_missing_folder_errors(tmp_path):
    reader=PureplayPoller(lambda p,m:None,tmp_path/'missing')
    reader.start();assert reader.status()['state']=='error'


def test_delivery_failure_is_retried(tmp_path):
    write(tmp_path,[])
    def fail(p,m):raise RuntimeError('full')
    reader=PureplayPoller(fail,tmp_path);reader.poll_once()
    write(tmp_path,[shot()]);reader.poll_once()
    assert reader.status()['state']=='error'
    events=[];reader.on_shot=lambda p,m:events.append(p);reader.poll_once()
    assert len(events)==1


def test_controller_ready_and_stop_generation(tmp_path):
    write(tmp_path,[]);q=queue.Queue();controller=SourceConnections(q)
    controller.start('pureplay',{'pureplay_profiles_path':str(tmp_path)})
    deadline=time.monotonic()+3
    while controller.snapshot()['state']=='connecting' and time.monotonic()<deadline:time.sleep(.01)
    assert controller.snapshot()['state']=='connected'
    assert not controller.snapshot()['shot_received']
    write(tmp_path,[shot()]);item=q.get(timeout=3)
    assert controller.accepts(item)
    assert controller.snapshot()['shot_received']
    controller.stop();assert not controller.accepts(item)


def test_unverified_pureplay_shots_are_accepted_without_claiming_measurement(tmp_path):
    write(tmp_path, [])
    events=[]
    reader = PureplayPoller(lambda p, m: events.append(p), tmp_path)
    reader.poll_once()
    unverified = shot(); unverified['bFromLaunchMonitor'] = False
    write(tmp_path, [unverified]); reader.poll_once()
    assert reader.status()['shot_received']
    assert 'not hardware-verified' in reader.status()['message']
    assert events[0]['_pureplay']['launch_monitor_flag'] is False
    assert events[0]['_pureplay']['measurement_provenance'] == 'pureplay_reported_unverified'
    assert all(not m['calibration_ground_truth'] for m in events[0]['_metric_provenance'].values())
    reader.poll_once()
    assert len(events)==1


@pytest.mark.parametrize('flag', [True, False, None])
def test_source_agnostic_mapper_preserves_input_flag(flag):
    raw=shot();raw['bFromLaunchMonitor']=flag
    mapped,_=map_pureplay_shot_to_sps_payload(raw)
    assert mapped['_pureplay']['launch_monitor_flag'] is flag
    assert metric_status(mapped, 'ball_speed') == 'REPORTED'
    assert metric_status(mapped, 'carry') == 'ESTIMATED'
