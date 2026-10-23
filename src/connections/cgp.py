"""CGP Draft 2 device discovery and explicitly started client lifecycle.

Discovery names are untrusted advertisements. Addresses are discovered, not
saved settings. No persistent key, credential, or trust database is created.
Transport imports are lazy so existing Nova users do not require aioquic.
"""

import asyncio
import ipaddress
import threading
from collections import OrderedDict
from dataclasses import dataclass

SERVICE_TYPE = "_common-golf._udp.local."


@dataclass(frozen=True)
class CGPDevice:
    name: str
    host: str
    port: int
    service_name: str = ""
    vendor: str = ""
    model: str = ""
    serial: str = ""

    def __post_init__(self):
        if not self.name or not self.host:
            raise ValueError("CGP device requires a name and discovered address")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("CGP device port must be between 1 and 65535")
        if not self.service_name:
            object.__setattr__(self, "service_name", f"{self.name}.{SERVICE_TYPE}")


def _device_from_info(info):
    addresses = (info.parsed_scoped_addresses() if hasattr(info, "parsed_scoped_addresses")
                 else info.parsed_addresses())
    addresses = [address for address in addresses
                 if not ipaddress.ip_address(address.split("%")[0]).is_unspecified
                 and not ipaddress.ip_address(address.split("%")[0]).is_multicast]
    if not addresses:
        return None
    addresses.sort(key=lambda address: ":" in address)
    def txt(name):
        value = info.properties.get(name.encode(), b"")
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else ""
    return CGPDevice(info.name.removesuffix("." + SERVICE_TYPE), addresses[0], info.port,
                     info.name, txt("vendor"), txt("model"), txt("serial"))


async def _discover(timeout):
    from zeroconf import ServiceListener
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    found, tasks, removed = {}, set(), set()
    zc = AsyncZeroconf()

    async def resolve(name):
        try:
            info = AsyncServiceInfo(SERVICE_TYPE, name)
            if await info.async_request(zc.zeroconf, 1500) and name not in removed:
                device = _device_from_info(info)
                if device is not None:
                    found[name] = device
        except (OSError, TypeError, ValueError):
            pass

    def resolved(task):
        tasks.discard(task)
        if not task.cancelled():
            task.exception()  # Retrieve resolver errors during library shutdown races.

    class Listener(ServiceListener):
        def add_service(self, zeroconf, type_, name):
            removed.discard(name)
            task = asyncio.create_task(resolve(name))
            tasks.add(task)
            task.add_done_callback(resolved)

        def update_service(self, zeroconf, type_, name):
            self.add_service(zeroconf, type_, name)

        def remove_service(self, zeroconf, type_, name):
            removed.add(name)
            found.pop(name, None)

    browser = None
    try:
        browser = AsyncServiceBrowser(zc.zeroconf, SERVICE_TYPE, listener=Listener())
        await asyncio.sleep(timeout)
    finally:
        try:
            if browser is not None:
                await browser.async_cancel()
        finally:
            pending = list(tasks)
            for task in pending:
                task.cancel()
            try:
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            finally:
                await zc.async_close()
    return sorted(found.values(), key=lambda device: (device.name.casefold(), device.service_name))


def discover(timeout=3.0):
    """Return discovered devices. Run this bounded call off the Tk thread."""
    if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not 0 < timeout <= 30:
        raise ValueError("CGP discovery timeout must be between 0 and 30 seconds")
    return asyncio.run(_discover(timeout))


class CGPClient:
    """One selected connection; separate clients may coexist independently.

    Reconnection is explicit after rediscovery. Status callbacks execute on
    the worker thread and must not touch Tk. Only the selected service name
    should be persisted, not resolved addresses or transient peer fingerprints.
    """

    discover = staticmethod(discover)

    def __init__(self, shot_queue, on_status=None, measurement_ids=None):
        self.shot_queue = shot_queue
        self.on_status = on_status
        self._measurement_ids = measurement_ids if measurement_ids is not None else OrderedDict()
        self._thread = None
        self._loop = None
        self._task = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._connected = False

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _status(self, status, message, **extra):
        if status in {"connected", "connecting", "disconnected", "error"}:
            self._connected = status == "connected"
        if self.on_status is not None:
            try:
                self.on_status({"source": "cgp", "status": status, "connected": self._connected,
                                "message": message, **extra})
            except Exception:
                pass

    def start(self, device):
        if not isinstance(device, CGPDevice):
            raise TypeError("Select a discovered CGPDevice before connecting")
        self.stop()
        with self._lock:
            if self.is_running:
                raise RuntimeError("The previous CGP connection is still closing")
            self._stop.clear()
            self._thread = threading.Thread(target=self._worker, args=(device,), name="SPS-CGP", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            loop, task, thread = self._loop, self._task, self._thread
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.5)

    def _worker(self, device):
        async def run():
            with self._lock:
                self._loop, self._task = asyncio.get_running_loop(), asyncio.current_task()
            if self._stop.is_set():
                return
            from .cgp_transport import connect_client
            self._status("connecting", f"Connecting to {device.name} (CGP Draft 2)")
            await connect_client(device, self.shot_queue, self._status, self._measurement_ids)
        failed = False
        try:
            asyncio.run(run())
        except asyncio.CancelledError:
            pass
        except ImportError as exc:
            failed = True
            self._status("error", f"CGP requires aioquic and zeroconf: {exc}")
        except Exception as exc:
            if not self._stop.is_set():
                failed = True
                self._status("error", f"CGP connection failed: {exc or type(exc).__name__}")
        finally:
            with self._lock:
                self._loop = self._task = None
            if not failed:
                self._status("disconnected", "CGP disconnected")
