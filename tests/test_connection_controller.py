import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.connections.controller import SourceConnections, StudioConnectionSetup


def wait_for(predicate):
    for _ in range(200):
        if predicate():
            return
        time.sleep(.005)
    assert predicate()


def test_no_listener_on_construction():
    c = SourceConnections(queue.Queue())
    assert c._client is None and not c.active_for('nova')
    assert c.snapshot()['state'] == 'idle'


def test_stale_sources_and_queued_generation_rejected():
    q = queue.Queue(); c = SourceConnections(q)
    c.start('nova'); old = c.input_queue('nova')
    old.put({'type':'shot'}); shot = q.get_nowait()
    assert c.accepts(shot)
    c.start('gspro'); old.put({'type':'shot'})
    assert q.empty() and not c.accepts(shot)
    c.input_queue('gspro').put({'type':'shot'})
    assert c.accepts(q.get_nowait())


def test_stop_invalidates_and_resets_readiness():
    q = queue.Queue(); c = SourceConnections(q); c.start('nova')
    sink = c.input_queue('nova'); sink.put({'type':'shot'})
    assert c.snapshot()['shot_received']
    c.stop(); sink.put({'type':'shot'})
    assert q.qsize() == 1 and not c.snapshot()['shot_received']


def test_bounded_queue_reports_failure():
    q = queue.Queue(); c = SourceConnections(q); c.start('nova')
    sink = c.input_queue('nova')
    for _ in range(256): sink.put({'type':'shot'})
    with pytest.raises(queue.Full): sink.put({'type':'shot'})
    assert q.qsize() == 256 and c.snapshot()['state'] == 'error'


def test_payload_copy_keeps_native_immutable():
    q = queue.Queue(); c = SourceConnections(q); c.start('nova')
    shot = {'nested':{'value':0}}
    c.input_queue('nova').put(shot)
    received = q.get_nowait(); received['nested']['value'] = 9
    assert shot == {'nested':{'value':0}}


@pytest.mark.parametrize("status,expected", [("disconnected", "idle"), ("listening", "listening")])
def test_status_disconnection_overrides_test_shot(monkeypatch,status,expected):
    callbacks = []
    class Client:
        def __init__(self, sink, on_status): self.sink=sink; callbacks.append(on_status)
        def start(self, **kwargs): self.sink.put({'type':'shot'})
        def stop(self): pass
    import src.connections.open_connect as module
    monkeypatch.setattr(module,'OpenConnectListener',Client)
    c=SourceConnections(queue.Queue());c.start_open_connect()
    wait_for(lambda:c.snapshot()['shot_received'])
    callbacks[0]({'status':status,'message':'gone','connected':False})
    assert c.snapshot()['state']==expected and not c.snapshot()['shot_received']
    c.stop()


def test_stale_start_does_not_close_new_client(monkeypatch):
    clients=[]
    class Client:
        def __init__(self,sink,on_status): self.closed=False;clients.append(self)
        def start(self,**kwargs): pass
        def stop(self): self.closed=True
    import src.connections.open_connect as module
    monkeypatch.setattr(module,'OpenConnectListener',Client)
    c=SourceConnections(queue.Queue())
    with c._operation:
        c.start_open_connect(); c.start_open_connect()
    wait_for(lambda:len(clients)==1)
    assert not clients[0].closed
    c.stop();wait_for(lambda:clients[0].closed)


def settings():
    values={'source':'nova','source_locked':False}
    def save(**kwargs): values.update(kwargs);return dict(values)
    return SimpleNamespace(load_settings=lambda:dict(values),save_settings=save)


def test_adapter_select_never_starts_and_saves_only_on_finish():
    q=queue.Queue();c=SourceConnections(q);s=settings(); legacy={}
    adapter=StudioConnectionSetup(c,s,legacy_status=lambda source:legacy)
    adapter.select_source('gspro')
    assert not c.active_for('gspro')
    adapter.start('gspro',{'db_path':'/tmp/test.db'})
    assert c.active_for('gspro') and not adapter.snapshot()['shot_received']
    legacy['connected']=True
    c.input_queue('gspro').put({'type':'shot'})
    assert adapter.snapshot()['state']=='ready'
    adapter.save_selection('gspro',True)
    assert s.load_settings()['onboarded'] and s.load_settings()['always_show_splash']
    adapter.stop()


def test_source_lock_is_respected():
    s=settings();s.save_settings(source_locked=True)
    adapter=StudioConnectionSetup(SourceConnections(queue.Queue()),s)
    with pytest.raises(ValueError):adapter.select_source('open_connect')


def test_switch_to_legacy_closes_external_client(monkeypatch):
    clients=[]
    class Client:
        def __init__(self,sink,on_status): self.closed=False;clients.append(self)
        def start(self,**kwargs): pass
        def stop(self): self.closed=True
    import src.connections.open_connect as module
    monkeypatch.setattr(module,'OpenConnectListener',Client)
    c=SourceConnections(queue.Queue());c.start_open_connect()
    wait_for(lambda:len(clients)==1)
    c.start('nova');wait_for(lambda:clients[0].closed)
    assert c.active_for('nova')
    c.stop()


def test_legacy_disconnect_requires_new_test_shot():
    c=SourceConnections(queue.Queue()); legacy={}
    adapter=StudioConnectionSetup(c,settings(),legacy_status=lambda source:legacy)
    adapter.start('nova'); legacy['connected']=True
    c.input_queue('nova').put({'type':'shot'})
    assert adapter.snapshot()['state']=='ready'
    legacy['connected']=False
    assert not adapter.snapshot()['shot_received']
    legacy['connected']=True
    assert adapter.snapshot()['state']=='connected'
    assert not adapter.snapshot()['shot_received']
    adapter.stop()
