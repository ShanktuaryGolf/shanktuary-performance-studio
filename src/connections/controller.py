"""Exclusive, explicitly started inputs with generation-safe delivery."""
import queue
import threading
import uuid
from collections import OrderedDict
from copy import deepcopy


class _InputQueue:
    def __init__(self, owner, generation, source):
        self.owner, self.generation, self.source = owner, generation, source

    def put(self, shot, block=True, timeout=None):
        owner = self.owner
        with owner._lock:
            if owner._generation != self.generation or not owner._active:
                return
            if owner.queue.qsize() >= 256:
                owner._status.update(state="error", message="Input queue full; shot not accepted", shot_received=False)
                raise queue.Full("Input queue full")
            payload = deepcopy(shot)
            payload["_input_generation"] = self.generation
            payload["_source"] = self.source
            owner.queue.put_nowait(payload)
            owner._status.update(state="ready", message="Test shot received", shot_received=True)

    put_nowait = put


class SourceConnections:
    """Does not open sockets on construction. Stop invalidates queued old input."""
    def __init__(self, queue, on_status=None):
        self.queue = queue
        self._lock = threading.RLock()
        self._operation = threading.Lock()
        self._generation = uuid.uuid4().hex
        self._source = None
        self._active = False
        self._client = None
        self._measurement_ids = OrderedDict()
        self._player = None
        self._on_status = on_status
        self._status = dict(state="idle", message="Not connected", shot_received=False)

    def snapshot(self):
        with self._lock:
            return dict(self._status, source=self._source)

    def stop(self):
        with self._lock:
            self._generation = uuid.uuid4().hex
            self._active = False
            self._status = dict(state="idle", message="Stopped", shot_received=False)
        threading.Thread(target=self._close, daemon=True).start()

    def _close(self):
        with self._operation:
            with self._lock:
                if self._active:  # a newer start owns cleanup
                    return
                client, self._client = self._client, None
            if client:
                client.stop()

    def select_source(self, source):
        self.stop()
        with self._lock:
            self._source = source

    def accepts(self, shot):
        with self._lock:
            return self._active and shot.get("_input_generation") == self._generation

    def input_queue(self, source):
        with self._lock:
            return _InputQueue(self, self._generation, source)

    def active_for(self, source):
        with self._lock:
            return self._active and self._source in (source, "both")

    def start(self, source, options=None):
        options = dict(options or {})
        self.select_source(source)
        with self._lock:
            self._active = True
            generation = self._generation
            self._status.update(state="connecting", message="Connecting…")
        def status(value):
            with self._lock:
                if generation != self._generation:
                    return
                if isinstance(value, dict):
                    self._status.update(value)
                    mapped = {"connected": "connected", "connecting": "connecting", "error": "error", "disconnected": "idle", "listening": "listening", "stopped": "idle"}.get(value.get("status"))
                    if mapped:
                        self._status["state"] = mapped
                    if self._status.get("state") in ("error", "idle") or (mapped == "listening" and not value.get("connected")):
                        self._status["shot_received"] = False
                    if self._status.get("shot_received") and self._status.get("state") not in ("error", "idle"):
                        self._status["state"] = "ready"
                else:
                    self._status["message"] = str(value)
        def run():
            with self._operation:
                with self._lock:
                    if generation != self._generation or not self._active:
                        return
                    old, self._client = self._client, None
                if old:
                    old.stop()
                if source in ("nova", "gspro", "both"):
                    return
                try:
                    sink = _InputQueue(self, generation, source)
                    if source == "open_connect":
                        from .open_connect import OpenConnectListener
                        client = OpenConnectListener(sink, on_status=status)
                    elif source == "cgp":
                        from .cgp import CGPClient
                        client = CGPClient(sink, on_status=status, measurement_ids=self._measurement_ids)
                    else:
                        raise ValueError("Unknown connection source")
                    with self._lock:
                        if generation != self._generation or not self._active:
                            return
                        self._client = client
                    if source == "open_connect":
                        if self._player:
                            client.set_player(*self._player)
                        client.start(host=options.get("host", "127.0.0.1"), port=options.get("port", 921))
                    else:
                        client.start(options["device"])
                except Exception as exc:
                    status(dict(state="error", message=str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def start_open_connect(self, host="127.0.0.1", port=921):
        self.start("open_connect", dict(host=host, port=port))

    def start_cgp(self, device):
        self.start("cgp", dict(device=device))

    def update_player(self, handed, club):
        with self._lock:
            if self._player == (handed, club):
                return
            self._player = (handed, club)
            client = self._client
        if client and hasattr(client, "set_player"):
            client.set_player(handed=handed, club=club)


class StudioConnectionSetup:
    """Wizard-facing adapter; legacy worker lifecycle stays owned by Studio."""
    def __init__(self, connections, settings_module, wake=None, legacy_status=None):
        self.connections = connections
        self.settings_module = settings_module
        self.wake = wake or (lambda: None)
        self.legacy_status = legacy_status or (lambda source: {})
        self.settings = settings_module.load_settings()

    def select_source(self, source):
        if self.settings.get("source_locked") and source != self.settings["source"]:
            raise ValueError("Source is locked by SPS_SHOT_SOURCE")
        self.connections.select_source(source)
        self.settings["source"] = source
        self.wake()

    def start(self, source, options=None):
        self.select_source(source)
        options = dict(options or {})
        kwargs = {"source": source}
        for key in ("db_path", "ogc_enrichment", "ogc_club_estimates"):
            if key in options:
                kwargs[key] = options[key]
        if source == "open_connect":
            kwargs.update(open_connect_port=options.get("port", 921),
                          open_connect_lan=options.get("host", "127.0.0.1") != "127.0.0.1")
        self.settings = self.settings_module.save_settings(**kwargs)
        if source in ("nova", "gspro", "both"):
            self.legacy_status(source).update(connected=False, last_message="Connecting…")
        self.connections.start(source, options)
        self.wake()

    def stop(self):
        self.connections.stop()
        self.wake()

    def snapshot(self):
        status = self.connections.snapshot()
        source = status.get("source")
        if status["state"] != "idle" and source in ("nova", "gspro", "both"):
            legacy = self.legacy_status(source)
            if not legacy.get("connected"):
                with self.connections._lock:
                    self.connections._status.update(shot_received=False, state="connecting")
                message = legacy.get("last_message") or "Waiting for connection"
                if source == "gspro" and legacy.get("db_found") is False:
                    message = "GSPro database not found. Choose its file, then start reading."
                status.update(shot_received=False, state="connecting", message=message)
            elif not status["shot_received"]:
                status.update(state="connected", message="Connected. Hit a test shot.")
        return status

    def save_selection(self, source, always_show=False):
        self.settings = self.settings_module.save_settings(
            source=source, onboarded=True, always_show_splash=always_show)
        return dict(self.settings)


def club_code(name):
    """Only recognized bag names produce protocol club identifiers."""
    text = str(name or "").strip().upper()
    fixed = {"DRIVER": "DR", "PUTTER": "PT", "PW": "PW", "GW": "GW", "AW": "GW", "SW": "SW", "LW": "LW"}
    if text in fixed:
        return fixed[text]
    parts = text.split()
    if len(parts) == 2 and parts[0].isdigit() and 1 <= int(parts[0]) <= 9:
        prefix = {"IRON": "I", "WOOD": "W", "HYBRID": "H"}.get(parts[1])
        if prefix:
            return prefix + parts[0]
    return None
