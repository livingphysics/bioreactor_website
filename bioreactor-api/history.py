"""
Rolling sensor-history buffer + long-term daily archive for the bioreactor API.

A background thread samples the monitor signals (bath temp, ambient temp, signed
peltier current, and the OD channels when sampling is on) every `interval_s`.

Two layers:
  * In-memory ring buffer — the last `window_s` seconds (default 24h). This is what
    GET /api/history serves; the frontend is unchanged.
  * On-disk daily archive — every sample is APPENDED (never rewritten) as one
    truncated JSON line to `history/YYYY-MM-DD.jsonl`. A new file starts each local
    day; files older than `retention_days` (default 365) are pruned. Appending only
    the new bytes keeps SD-card writes tiny (~MB/day) vs rewriting a whole file.

On startup the ring buffer is reloaded from the most recent daily files (falling
back once to the legacy single-file `sensor_history.json` if present), so the live
view survives a restart. Independent of runs — it logs continuously.
"""
import os
import glob
import json
import time
import logging
import threading
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _num(v, ndigits=None):
    """Keep finite numbers (optionally rounded), drop None/NaN/non-numeric -> None."""
    if not (isinstance(v, (int, float)) and v == v):
        return None
    return round(float(v), ndigits) if ndigits is not None else v


class HistoryBuffer:
    def __init__(self):
        self._lock = threading.Lock()
        self._buf = deque()
        self._thread = None
        self._stop = threading.Event()
        self._sample_fn = None
        self._dir = None                 # daily-archive directory
        self._legacy_path = None         # old single-file buffer (one-time migration)
        self._interval = 10.0
        self._window_s = 24 * 3600       # in-memory window served to the frontend
        self._retention_days = 365       # daily archive files kept on disk
        # open append handle for the current day's file
        self._cur_date = None
        self._cur_file = None
        self._last_prune = 0.0
        self._archive_fail = 0        # consecutive archive-append failures
        self._last_fail_log = 0.0     # throttle the failure warning

    @property
    def interval_s(self) -> float:
        return self._interval

    def configure(self, *, sample_fn, archive_dir, interval_s=10.0,
                  window_s=24 * 3600, retention_days=365, legacy_path=None):
        self._sample_fn = sample_fn
        self._dir = archive_dir
        self._legacy_path = legacy_path
        self._interval = max(1.0, float(interval_s))
        self._window_s = max(60, int(window_s))
        self._retention_days = max(1, int(retention_days))
        self._buf = deque(maxlen=int(self._window_s / self._interval) + 120)
        if self._dir:
            try:
                os.makedirs(self._dir, exist_ok=True)
            except Exception as e:
                logger.error("history: cannot create archive dir %s: %s", self._dir, e)
                self._dir = None
        self._load_recent()

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        if self._sample_fn is None:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="history")
        self._thread.start()
        logger.info("History sampler started (every %.0fs, %dh live window, %dd archive)",
                    self._interval, self._window_s // 3600, self._retention_days)

    def stop(self):
        self._stop.set()
        t = self._thread
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=3.0)
        self._close_file()

    def _run(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self._sample_once()
            except Exception as e:
                logger.error("history sample failed: %s", e)
            if time.time() - self._last_prune >= 3600:   # prune old daily files hourly
                try:
                    self._prune()
                except Exception as e:
                    logger.warning("history prune failed: %s", e)
            self._stop.wait(max(0.0, self._interval - (time.time() - t0)))

    # -------------------------------------------------------------------- sampling
    def _sample_once(self):
        data = self._sample_fn()
        if not data:
            return
        now_ms = int(time.time() * 1000)
        pt = {
            "t": now_ms,
            "temp": _num(data.get("temperature"), 3),
            "ambient": _num(data.get("ambient_temp"), 3),
            "current": _num(data.get("peltier_current"), 4),
        }
        od = data.get("od")
        if isinstance(od, dict):
            pt["od"] = {k: _num(v, 5) for k, v in od.items()}   # truncate ADC readings
        with self._lock:
            self._buf.append(pt)
            self._evict()
        self._append_archive(pt, now_ms)

    def _append_archive(self, pt, now_ms):
        """Append one JSON line to today's daily file (opening/rotating as needed)."""
        if not self._dir:
            return
        date = datetime.fromtimestamp(now_ms / 1000).strftime("%Y-%m-%d")
        try:
            if date != self._cur_date or self._cur_file is None:
                self._close_file()
                os.makedirs(self._dir, exist_ok=True)   # self-heal a transiently-missing dir
                self._cur_file = open(os.path.join(self._dir, f"{date}.jsonl"), "a")
                self._cur_date = date
            self._cur_file.write(json.dumps(pt, separators=(",", ":")) + "\n")
            self._cur_file.flush()   # durable to the OS every sample; OS coalesces disk writes
            if self._archive_fail:
                logger.info("history archive recovered after %d failed sample(s)", self._archive_fail)
                self._archive_fail = 0
        except Exception as e:
            # Throttle: warn on the first failure, then at most every 5 min, so a full
            # disk / missing dir doesn't spam a warning every sample. Reopen next tick
            # (with the makedirs above) so a transient failure self-heals.
            self._archive_fail += 1
            now = time.time()
            if self._archive_fail == 1 or now - self._last_fail_log >= 300:
                logger.warning("history archive append failing (%d sample(s)): %s",
                               self._archive_fail, e)
                self._last_fail_log = now
            self._close_file()       # force a clean reopen next tick

    def _close_file(self):
        if self._cur_file is not None:
            try:
                self._cur_file.close()
            except Exception:
                pass
        self._cur_file = None
        self._cur_date = None

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

    # ------------------------------------------------------------------ archive I/O
    def _load_recent(self):
        """Repopulate the in-memory window from the newest daily files (or the legacy
        single-file buffer, once) so the live view survives a restart."""
        cutoff = int(time.time() * 1000) - self._window_s * 1000
        recent = []
        if self._dir:
            days_needed = int(self._window_s / 86400) + 2   # enough files to cover the window
            for path in sorted(glob.glob(os.path.join(self._dir, "*.jsonl")))[-days_needed:]:
                try:
                    with open(path) as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                p = json.loads(line)
                            except Exception:
                                continue
                            if isinstance(p, dict) and p.get("t", 0) >= cutoff:
                                recent.append(p)
                except Exception as e:
                    logger.warning("history load %s failed: %s", os.path.basename(path), e)
        # Bridge in legacy single-file-buffer points that predate the archive, so the
        # live window stays full during the first 24h after upgrading (before the daily
        # archive has accumulated a full window). Only points older than the archive's
        # earliest are added, so there's no overlap; they age out of the window
        # naturally, and once the archive covers the whole window this contributes
        # nothing.
        if self._legacy_path and os.path.exists(self._legacy_path):
            try:
                with open(self._legacy_path) as f:
                    obj = json.load(f)
                earliest = min((p["t"] for p in recent), default=float("inf"))
                legacy = [p for p in obj.get("points", [])
                          if isinstance(p, dict) and cutoff <= p.get("t", 0) < earliest]
                if legacy:
                    recent = legacy + recent
                    logger.info("History: bridged %d legacy points into the live window", len(legacy))
            except Exception as e:
                logger.warning("legacy history load failed: %s", e)
        recent.sort(key=lambda p: p.get("t", 0))
        with self._lock:
            self._buf.extend(recent)   # deque maxlen bounds it
        logger.info("History: loaded %d recent points", len(recent))

    def _prune(self):
        """Delete daily archive files older than retention_days."""
        self._last_prune = time.time()
        if not self._dir:
            return
        cutoff = datetime.now().date() - timedelta(days=self._retention_days)
        for path in glob.glob(os.path.join(self._dir, "*.jsonl")):
            name = os.path.basename(path)[:-6]   # strip ".jsonl"
            try:
                day = datetime.strptime(name, "%Y-%m-%d").date()
            except ValueError:
                continue   # not a dated archive file
            if day < cutoff:
                try:
                    os.remove(path)
                    logger.info("History: pruned archive %s", name)
                except Exception as e:
                    logger.warning("prune %s failed: %s", name, e)


# Module-level singleton used by main.py
history = HistoryBuffer()
