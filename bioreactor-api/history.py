"""
Rolling sensor-history ring buffer for the bioreactor API.

A background thread samples the monitor signals (bath temp, ambient temp, signed
peltier current) every `interval_s` and keeps the last `window_s` seconds in
memory. The buffer is persisted to a JSON file periodically (and on stop) and
reloaded on startup, so history survives an API restart or a reboot.

Served read-only via GET /api/history (optionally ?since=<ms> for incremental
fetches). Independent of runs — it logs continuously whether or not a schedule/
PID run is active.
"""
import os
import json
import time
import logging
import threading
from collections import deque

logger = logging.getLogger(__name__)


def _num(v):
    """Keep finite numbers, drop None/NaN/non-numeric -> None."""
    return v if (isinstance(v, (int, float)) and v == v) else None


class HistoryBuffer:
    def __init__(self):
        self._lock = threading.Lock()
        self._buf = deque()
        self._thread = None
        self._stop = threading.Event()
        self._sample_fn = None
        self._path = None
        self._interval = 10.0
        self._window_s = 24 * 3600
        self._last_persist = 0.0

    @property
    def interval_s(self) -> float:
        return self._interval

    def configure(self, *, sample_fn, persist_path, interval_s=10.0, window_s=24 * 3600):
        self._sample_fn = sample_fn
        self._path = persist_path
        self._interval = max(1.0, float(interval_s))
        self._window_s = max(60, int(window_s))
        self._buf = deque(maxlen=int(self._window_s / self._interval) + 120)
        self._load()

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        if self._sample_fn is None:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="history")
        self._thread.start()
        logger.info("History sampler started (every %.0fs, %dh window)",
                    self._interval, self._window_s // 3600)

    def stop(self):
        self._stop.set()
        t = self._thread
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=3.0)
        self._persist()

    def _run(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self._sample_once()
            except Exception as e:
                logger.error("history sample failed: %s", e)
            if time.time() - self._last_persist >= 60:
                self._persist()
            self._stop.wait(max(0.0, self._interval - (time.time() - t0)))

    # -------------------------------------------------------------------- sampling
    def _sample_once(self):
        data = self._sample_fn()
        if not data:
            return
        pt = {
            "t": int(time.time() * 1000),
            "temp": _num(data.get("temperature")),
            "ambient": _num(data.get("ambient_temp")),
            "current": _num(data.get("peltier_current")),
        }
        od = data.get("od")
        if isinstance(od, dict):
            pt["od"] = {k: _num(v) for k, v in od.items()}
        with self._lock:
            self._buf.append(pt)
            self._evict()

    def _evict(self):
        cutoff = int(time.time() * 1000) - self._window_s * 1000
        while self._buf and self._buf[0]["t"] < cutoff:
            self._buf.popleft()

    def get(self, since_ms=0):
        with self._lock:
            self._evict()
            if since_ms and since_ms > 0:
                return [p for p in self._buf if p["t"] > since_ms]
            return list(self._buf)

    # ------------------------------------------------------------------ persistence
    def _persist(self):
        if not self._path:
            return
        try:
            with self._lock:
                pts = list(self._buf)
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"interval_s": self._interval, "points": pts}, f)
            os.replace(tmp, self._path)   # atomic
            self._last_persist = time.time()
        except Exception as e:
            logger.warning("history persist failed: %s", e)

    def _load(self):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path) as f:
                obj = json.load(f)
            cutoff = int(time.time() * 1000) - self._window_s * 1000
            pts = [p for p in obj.get("points", [])
                   if isinstance(p, dict) and p.get("t", 0) >= cutoff]
            with self._lock:
                self._buf.extend(pts)
            logger.info("History: loaded %d points from disk", len(pts))
        except Exception as e:
            logger.warning("history load failed: %s", e)


# Module-level singleton used by main.py
history = HistoryBuffer()
