"""Strict Open Connect mapping and real TCP lifecycle tests on loopback only."""

import copy
import json
import queue
import socket
import time

import pytest

from src.connections.open_connect import (
    FRAME_TIMEOUT_SECONDS,
    MAX_CLIENTS,
    MAX_MESSAGE_BYTES,
    MPH_TO_MPS,
    OpenConnectError,
    OpenConnectJSONStream,
    OpenConnectListener,
    map_open_connect_shot_to_sps_payload,
)


def shot(number=1, device='Test monitor'):
    return {
        'DeviceID': device, 'APIversion': '1', 'Units': 'Yards', 'ShotNumber': number,
        'BallData': {'Speed': 140.0, 'VLA': 13.0, 'HLA': -2.0,
                     'TotalSpin': 3000.0, 'SpinAxis': -8.0},
        'ShotDataOptions': {'ContainsBallData': True, 'ContainsClubData': False},
    }


def encode(message):
    return json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def recv_messages(client, count=1):
    parser = OpenConnectJSONStream()
    result = []
    while len(result) < count:
        data = client.recv(8192)
        if not data:
            break
        result.extend(parser.feed(data))
    return result


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def connect(receiver):
    client = socket.create_connection(receiver.address, timeout=2)
    client.settimeout(2)
    return client


@pytest.fixture
def listener():
    shots, statuses = queue.Queue(), []
    receiver = OpenConnectListener(shots, on_status=statuses.append)
    receiver.start(port=0)
    try:
        yield receiver, shots, statuses
    finally:
        receiver.stop()


class TestMapper:
    def test_units_signs_and_provenance(self):
        message = shot()
        message['BallData'].update(CarryDistance=210, BackSpin=2970, SideSpin=-300)
        message['ShotDataOptions']['ContainsClubData'] = True
        message['ClubData'] = {'Speed': 95, 'AngleOfAttack': -2, 'FaceToTarget': 1,
                               'Path': 3, 'ClosureRate': 700, 'Loft': 21,
                               'Lie': 62, 'HorizontalFaceImpact': 4}
        original = copy.deepcopy(message)
        payload, meta = map_open_connect_shot_to_sps_payload(message)
        assert original == message
        assert payload['ball_speed_meters_per_second'] == pytest.approx(140 * MPH_TO_MPS)
        assert payload['vertical_launch_angle_degrees'] == 13
        assert payload['horizontal_launch_angle_degrees'] == -2
        assert payload['spin_axis_degrees'] == -8
        assert payload['total_spin_rpm'] == 3000
        ogc = payload['open_golf_coach']
        assert ogc['club_speed_meters_per_second'] == pytest.approx(95 * MPH_TO_MPS)
        assert ogc['carry_distance_meters'] == pytest.approx(210 * 0.9144)
        assert ogc['us_customary_units'] == {'ball_speed_mph': 140, 'club_speed_mph': 95,
                                             'carry_distance_yards': 210}
        assert ogc['angle_of_attack_degrees'] == -2
        assert ogc['club_face_to_target_degrees'] == 1
        assert ogc['club_path_degrees'] == 3
        assert ogc['backspin_rpm'] == 2970
        assert ogc['sidespin_rpm'] == -300
        assert ogc['total_spin_rpm'] == 3000
        assert ogc['spin_axis_degrees'] == -8
        assert meta['raw_message'] == original
        assert meta['raw_message'] is not message
        assert meta['measurement_provenance'] == 'sender_reported'
        provenance = payload['_metric_provenance']
        speed = provenance['ball_speed_meters_per_second']
        assert speed['kind'] == 'derived'
        assert speed['inputs'] == ['open_golf_coach.us_customary_units.ball_speed_mph']
        assert provenance[speed['inputs'][0]]['kind'] == 'source_reported'
        assert provenance['open_golf_coach.total_spin_rpm']['inputs'] == ['total_spin_rpm']
        assert all(not entry['calibration_ground_truth'] for entry in provenance.values())

    def test_missing_does_not_become_zero_or_nova_measurement(self):
        payload, meta = map_open_connect_shot_to_sps_payload(shot())
        ogc = payload['open_golf_coach']
        for key in ('carry_distance_meters', 'total_distance_meters', 'offline_distance_meters',
                    'club_speed_meters_per_second', 'smash_factor', 'dynamic_loft_degrees',
                    'face_contact', 'backspin_rpm', 'sidespin_rpm'):
            assert key not in ogc
        assert 'club_speed_mph' not in ogc['us_customary_units']
        assert 'club' not in payload
        assert 'ClubData.Speed' in meta['missing_fields']
        assert 'spin_axis_degrees' not in meta['derived_fields']

    def test_undeclared_club_fields_remain_raw(self):
        message = shot()
        message['ClubData'] = {'Speed': 0, 'Path': 0}
        payload, meta = map_open_connect_shot_to_sps_payload(message)
        assert 'club_speed_meters_per_second' not in payload['open_golf_coach']
        assert meta['raw_message']['ClubData'] == message['ClubData']

    def test_reported_zeroes_stay_zero(self):
        message = shot()
        message['BallData'].update(TotalSpin=0, SpinAxis=0, HLA=0, VLA=0, CarryDistance=0)
        message['ShotDataOptions']['ContainsClubData'] = True
        message['ClubData'] = {'Speed': 0, 'Path': 0}
        payload, _ = map_open_connect_shot_to_sps_payload(message)
        assert payload['total_spin_rpm'] == 0
        assert payload['spin_axis_degrees'] == 0
        assert payload['horizontal_launch_angle_degrees'] == 0
        assert payload['open_golf_coach']['carry_distance_meters'] == 0
        assert payload['open_golf_coach']['club_speed_meters_per_second'] == 0
        assert payload['open_golf_coach']['us_customary_units']['club_speed_mph'] == 0

    def test_derived_vector_spin_is_labeled(self):
        message = shot()
        message['BallData'].pop('TotalSpin')
        message['BallData'].pop('SpinAxis')
        message['BallData'].update(BackSpin=3000, SideSpin=-4000)
        payload, meta = map_open_connect_shot_to_sps_payload(message)
        assert payload['total_spin_rpm'] == 5000
        assert payload['spin_axis_degrees'] == pytest.approx(-53.130102)
        assert {'total_spin_rpm', 'spin_axis_degrees'}.issubset(meta['derived_fields'])
        assert 'BallData.SpinAxis' in meta['missing_fields']
        assert payload['_metric_provenance']['spin_axis_degrees']['inputs'] == [
            'open_golf_coach.backspin_rpm', 'open_golf_coach.sidespin_rpm']

    def test_zero_vector_has_labeled_canonical_axis(self):
        message = shot()
        message['BallData'].pop('TotalSpin')
        message['BallData'].pop('SpinAxis')
        message['BallData'].update(BackSpin=0, SideSpin=0)
        payload, meta = map_open_connect_shot_to_sps_payload(message)
        assert payload['total_spin_rpm'] == 0
        assert payload['spin_axis_degrees'] == 0
        assert meta['zero_spin_axis_convention'] is True
        assert payload['_metric_provenance']['spin_axis_degrees']['assumptions']

    def test_unknown_estimation_flags_and_ambiguous_units_stay_raw(self):
        message = shot()
        message['BallData']['SpinIsEstimated'] = True
        message['ShotDataOptions']['ContainsClubData'] = True
        message['ClubData'] = {'Loft': 17, 'VerticalFaceImpact': -3,
                               'HorizontalFaceImpact': 2, 'SpeedAtImpact': 90}
        payload, meta = map_open_connect_shot_to_sps_payload(message)
        assert meta['raw_message']['BallData']['SpinIsEstimated'] is True
        for key in ('dynamic_loft_degrees', 'face_contact', 'club_speed_meters_per_second'):
            assert key not in payload['open_golf_coach']

    def test_heartbeat_is_not_a_shot(self):
        message = shot()
        message['ShotDataOptions'].update(ContainsBallData=False, IsHeartBeat=True)
        payload, meta = map_open_connect_shot_to_sps_payload(message)
        assert payload is None
        assert meta['raw_message'] == message

    def test_default_yards_profile(self):
        message = shot()
        message.pop('Units')
        payload, _ = map_open_connect_shot_to_sps_payload(message)
        assert payload['ball_speed_meters_per_second'] == pytest.approx(140 * MPH_TO_MPS)

    @pytest.mark.parametrize('field,value', [
        ('DeviceID', ''), ('DeviceID', None), ('DeviceID', 'x' * 257), ('DeviceID', '\ud800'),
        ('APIversion', 1), ('APIversion', '2'), ('Units', 'Meters'),
        ('ShotNumber', True), ('ShotNumber', -1), ('ShotNumber', 1.2),
        ('ShotNumber', float('inf')), ('ShotNumber', 2 ** 53),
        ('ShotDataOptions', {}), ('BallData', []),
    ])
    def test_invalid_schema(self, field, value):
        message = shot()
        message[field] = value
        with pytest.raises(OpenConnectError):
            map_open_connect_shot_to_sps_payload(message)

    @pytest.mark.parametrize('field,value', [
        ('Speed', None), ('Speed', '100'), ('Speed', True), ('Speed', 0),
        ('VLA', float('nan')), ('HLA', float('inf')), ('HLA', 181),
        ('VLA', 91), ('TotalSpin', -1), ('SpinAxis', 181), ('CarryDistance', '210'),
    ])
    def test_invalid_ball_number(self, field, value):
        message = shot()
        message['BallData'][field] = value
        with pytest.raises(OpenConnectError):
            map_open_connect_shot_to_sps_payload(message)

    def test_heartbeat_cannot_smuggle_shot(self):
        message = shot()
        message['ShotDataOptions']['IsHeartBeat'] = True
        with pytest.raises(OpenConnectError):
            map_open_connect_shot_to_sps_payload(message)


class TestFraming:
    @pytest.mark.parametrize('chunk_size', [1, 2, 5, 8192])
    def test_arbitrary_splits_concatenation_and_unicode(self, chunk_size):
        messages = [shot(1, '球 🏌 {escaped}'), shot(2, 'quote " slash \\')]
        data = b'\r\n ' + encode(messages[0]) + encode(messages[1]) + b'\n'
        parser, result = OpenConnectJSONStream(), []
        for offset in range(0, len(data), chunk_size):
            result.extend(parser.feed(data[offset:offset + chunk_size]))
        assert result == messages
        assert not parser.frame
        assert parser.pending_since is None

    @pytest.mark.parametrize('data', [
        b'[]', b'null', b'{"x":]}', b'{oops}', b'{"a":1,"a":2}',
        b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'{"x":"\xff"}',
        b'{"x":"\\ud800"}',
    ])
    def test_invalid_stream_is_terminal(self, data):
        parser = OpenConnectJSONStream()
        with pytest.raises(OpenConnectError):
            list(parser.feed(data))
        with pytest.raises(OpenConnectError):
            list(parser.feed(b'{}'))

    def test_size_depth_and_slow_frame_bounds(self):
        with pytest.raises(OpenConnectError, match='size limit'):
            list(OpenConnectJSONStream(max_bytes=10).feed(b'{"message":"too long"}'))
        with pytest.raises(OpenConnectError, match='nesting'):
            list(OpenConnectJSONStream(max_depth=2).feed(b'{"a":{"b":[]}}'))
        parser = OpenConnectJSONStream()
        assert list(parser.feed(b' ', now=1)) == []
        assert parser.pending_since is None
        assert list(parser.feed(b'{', now=2)) == []
        assert list(parser.feed(b'"part', now=8)) == []
        with pytest.raises(OpenConnectError, match='timed out'):
            parser.check_timeout(now=2 + FRAME_TIMEOUT_SECONDS + 0.1)

    def test_good_prefix_is_delivered_but_invalid_tail_is_not(self):
        frames = OpenConnectJSONStream().feed(b'{}not json{}')
        assert next(frames) == {}
        with pytest.raises(OpenConnectError):
            next(frames)


class TestListener:
    def test_construction_never_opens_network(self):
        receiver = OpenConnectListener(queue.Queue())
        assert not receiver.running
        assert receiver.address is None
        assert receiver._thread is None
        receiver.stop()

    def test_default_loopback_stop_closes_client_and_listener(self, listener):
        receiver, _, _ = listener
        address = receiver.address
        assert address[0] == '127.0.0.1'
        with connect(receiver) as client:
            wait_until(lambda: bool(receiver._clients))
            before = time.monotonic()
            receiver.stop()
            assert time.monotonic() - before < 1
            assert client.recv(8192) == b''
            assert not receiver.running
        with pytest.raises(OSError):
            socket.create_connection(address, timeout=0.25)

    def test_fragmented_concatenated_shots_receive_200(self, listener):
        receiver, shots, statuses = listener
        with connect(receiver) as client:
            data = encode(shot(1, '球 🏌')) + encode(shot(2, '球 🏌'))
            for offset in range(0, len(data), 3):
                client.sendall(data[offset:offset + 3])
            assert [reply['Code'] for reply in recv_messages(client, 2)] == [200, 200]
            assert [shots.get(timeout=1)['_open_connect']['shot_number'] for _ in range(2)] == [1, 2]
        assert any(status['status'] == 'connected' and status['connected'] for status in statuses)

    def test_201_player_requires_explicit_selection(self, listener):
        receiver, _, _ = listener
        with connect(receiver) as client:
            client.settimeout(0.15)
            with pytest.raises(socket.timeout):
                client.recv(8192)
            client.settimeout(2)
            receiver.set_player('LH', '7I')
            assert recv_messages(client) == [{'Code': 201, 'Message': 'GSPro Player Information',
                                               'Player': {'Handed': 'LH', 'Club': '7I'}}]
            receiver.set_player('LH', 'PT')
            assert recv_messages(client)[0]['Player'] == {'Handed': 'LH', 'Club': 'PT'}

    def test_heartbeat_ack_and_readiness_but_no_shot(self, listener):
        receiver, shots, statuses = listener
        message = shot()
        message['ShotDataOptions'].update(ContainsBallData=False, IsHeartBeat=True,
                                           LaunchMonitorIsReady=True)
        with connect(receiver) as client:
            client.sendall(encode(message))
            assert recv_messages(client)[0]['Code'] == 200
            assert shots.empty()
        assert any('device ready' in status['message'] for status in statuses)

    def test_bad_schema_501_does_not_poison_following_shot(self, listener):
        receiver, shots, _ = listener
        invalid = shot()
        invalid['Units'] = 'Meters'
        with connect(receiver) as client:
            client.sendall(encode(invalid) + encode(shot()))
            assert [r['Code'] for r in recv_messages(client, 2)] == [501, 200]
            assert shots.qsize() == 1

    def test_malformed_stream_closes_and_does_not_ingest_tail(self, listener):
        receiver, shots, _ = listener
        with connect(receiver) as client:
            client.sendall(b'{bad}' + encode(shot()))
            assert recv_messages(client)[0]['Code'] == 501
            assert client.recv(8192) == b''
            assert shots.empty()
        with connect(receiver) as client:
            client.sendall(encode(shot()))
            assert recv_messages(client)[0]['Code'] == 200
            assert shots.qsize() == 1

    def test_dedupe_per_device_survives_reconnect(self, listener):
        receiver, shots, _ = listener
        with connect(receiver) as client:
            client.sendall(encode(shot(9)) + encode(shot(9)) + encode(shot(8)) + encode(shot(9, 'second')))
            assert [r['Code'] for r in recv_messages(client, 4)] == [200] * 4
        with connect(receiver) as client:
            client.sendall(encode(shot(9)) + encode(shot(10)))
            assert [r['Code'] for r in recv_messages(client, 2)] == [200, 200]
        result = [shots.get(timeout=1) for _ in range(3)]
        assert [p['_open_connect']['shot_number'] for p in result] == [9, 9, 10]
        assert len({p['shotId'] for p in result}) == 3
        assert shots.empty()
        assert receiver.reset_duplicate_history() is False

    def test_explicit_restart_resets_counter_and_identity(self, listener):
        receiver, shots, _ = listener
        with connect(receiver) as client:
            client.sendall(encode(shot(10)))
            assert recv_messages(client)[0]['Code'] == 200
        receiver.stop()
        assert receiver.reset_duplicate_history() is True
        receiver.start(port=0)
        with connect(receiver) as client:
            client.sendall(encode(shot(1)))
            assert recv_messages(client)[0]['Code'] == 200
        first, second = shots.get(timeout=1), shots.get(timeout=1)
        assert first['shotId'] != second['shotId']
        assert first['_open_connect']['session_id'] != second['_open_connect']['session_id']
        assert second['_open_connect']['shot_number'] == 1

    def test_bind_conflict_is_reported_without_disrupting_receiver(self, listener):
        receiver, shots, _ = listener
        statuses = []
        second = OpenConnectListener(queue.Queue(), statuses.append)
        with pytest.raises(OSError):
            second.start(port=receiver.address[1])
        assert not second.running
        assert statuses[-1]['status'] == 'error'
        with connect(receiver) as client:
            client.sendall(encode(shot()))
            assert recv_messages(client)[0]['Code'] == 200
            assert shots.qsize() == 1

    def test_repeated_stop_start_discards_partial_input(self, listener):
        receiver, shots, _ = listener
        for _ in range(5):
            with connect(receiver) as client:
                client.sendall(b'{"incomplete":')
                receiver.stop()
            receiver.start(port=0)
        with connect(receiver) as client:
            client.sendall(encode(shot()))
            assert recv_messages(client)[0]['Code'] == 200
            assert shots.qsize() == 1

    def test_full_queue_does_not_consume_number(self):
        shots = queue.Queue(maxsize=1)
        shots.put({'old': True})
        receiver = OpenConnectListener(shots)
        receiver.start(port=0)
        try:
            with connect(receiver) as client:
                client.sendall(encode(shot()))
                assert recv_messages(client)[0]['Code'] == 501
                shots.get()
                client.sendall(encode(shot()))
                assert recv_messages(client)[0]['Code'] == 200
            assert shots.get()['_open_connect']['shot_number'] == 1
        finally:
            receiver.stop()

    def test_oversized_stream_is_rejected(self, listener):
        receiver, shots, _ = listener
        with connect(receiver) as client:
            client.sendall(b'{"data":"' + b'x' * MAX_MESSAGE_BYTES)
            assert recv_messages(client)[0]['Code'] == 501
            assert client.recv(8192) == b''
        assert shots.empty()

    def test_partial_frame_timeout_only_closes_bad_client(self, listener, monkeypatch):
        from src.connections import open_connect
        monkeypatch.setattr(open_connect, 'FRAME_TIMEOUT_SECONDS', 0.03)
        receiver, shots, _ = listener
        with connect(receiver) as partial, connect(receiver) as healthy:
            partial.sendall(b'{"partial":')
            assert partial.recv(8192) == b''
            healthy.sendall(encode(shot()))
            assert recv_messages(healthy)[0]['Code'] == 200
            assert shots.qsize() == 1
            assert receiver.running

    def test_bounded_client_count(self, listener):
        receiver, _, _ = listener
        clients = [connect(receiver) for _ in range(MAX_CLIENTS)]
        try:
            wait_until(lambda: len(receiver._clients) == MAX_CLIENTS)
            with connect(receiver) as extra:
                assert extra.recv(8192) == b''
            assert len(receiver._clients) == MAX_CLIENTS
        finally:
            for client in clients:
                client.close()

    @pytest.mark.parametrize('host,port', [('8.8.8.8', 921), ('127.0.0.1', True),
                                           ('127.0.0.1', -1), ('127.0.0.1', 65536)])
    def test_invalid_bind_never_opens_socket(self, host, port):
        receiver = OpenConnectListener(queue.Queue())
        with pytest.raises(ValueError):
            receiver.start(host, port)
        assert not receiver.running
