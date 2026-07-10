"""
Timed-dose pump controller for the bioreactor API.

Runs a periodic media-exchange regime on a background thread. Every `interval`
seconds it doses once:

    OUTFLOW on for  interval * duty            seconds
    INFLOW  on for  inflow_ratio * interval * duty  seconds   (default 0.95x)

both at a fixed flow rate, then idles for the rest of the interval. Inflow runs
slightly less than outflow, so each cycle nets a small removal. `duty` is a 0-1
fraction internally (0-100 % at the API).

Both the manual `POST /api/pumps/run` and program `pump` tracks just call
`set_regime()`; this thread owns the timing. Hardware access is delegated to the
injected `run_fn` / `stop_fn` (which serialize on HARDWARE_LOCK in real mode), so
this module stays hardware-agnostic and runs unchanged in simulation.
"""
import time
import logging
import threading

logger = logging.getLogger(__name__)


class PumpController:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop_evt = threading.Event()
        self._wake = threading.Event()          # set to interrupt a sleep (regime change / stop)
        self._run_fn = None                     # run_fn(name, ml_per_sec)
        self._stop_fn = None                    # stop_fn(name)
        self._rate = 1.0                        # ml/sec while a pump is ON
        self._inflow_ratio = 0.95
        self._inflow_name = 'inflow'
        self._outflow_name = 'outflow'
        # regime (guarded by _lock)
        self._interval_s = 0.0
        self._duty = 0.0                        # 0-1 fraction
        self._active = False
        self._phase = 'idle'                    # 'idle' | 'dosing' | 'wait'

    # -------------------------------------------------------------- configuration
    def configure(self, *, run_fn, stop_fn, rate_ml_per_sec=1.0, inflow_ratio=0.95,
                  inflow_name='inflow', outflow_name='outflow'):
        self._run_fn = run_fn
        self._stop_fn = stop_fn
        self._rate = float(rate_ml_per_sec)
        self._inflow_ratio = float(inflow_ratio)
        self._inflow_name = inflow_name
        self._outflow_name = outflow_name

    def start(self):
        if self._run_fn is None:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="pump-controller")
        self._thread.start()
        logger.info("Pump controller started (rate=%.3g ml/s, inflow ratio=%.2f)",
                    self._rate, self._inflow_ratio)

    def stop(self):
        self._stop_evt.set()
        self._wake.set()
        t = self._thread
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=3.0)
        self._stop_both()

    # ---------------------------------------------------------------- regime API
    def set_regime(self, interval_s, duty_pct):
        """Start (or update) continuous cycling: dose every `interval_s` seconds at
        `duty_pct` (0-100). duty 0 or interval <= 0 turns cycling off."""
        interval_s = float(interval_s)
        duty = max(0.0, min(float(duty_pct), 100.0)) / 100.0
        with self._lock:
            self._interval_s = interval_s
            self._duty = duty
            self._active = duty > 0.0 and interval_s > 0.0
        self._wake.set()   # apply immediately (interrupt any in-progress sleep)

    def off(self):
        with self._lock:
            self._active = False
            self._duty = 0.0
        self._wake.set()
        self._stop_both()

    def status(self):
        with self._lock:
            return {
                'active': self._active,
                'interval_s': round(self._interval_s, 3),
                'duty': round(self._duty * 100.0, 1),        # 0-100 %
                'phase': self._phase if self._active else 'off',
                'rate_ml_per_sec': self._rate,
            }

    # ------------------------------------------------------------------- internals
    def _set_phase(self, p):
        with self._lock:
            self._phase = p

    def _stop_one(self, name):
        try:
            if self._stop_fn:
                self._stop_fn(name)
        except Exception as e:
            logger.warning("pump stop(%s) failed: %s", name, e)

    def _stop_both(self):
        self._stop_one(self._inflow_name)
        self._stop_one(self._outflow_name)

    def _wait(self, secs) -> bool:
        """Sleep up to `secs`, returning True if interrupted (regime change / stop)."""
        if secs <= 0:
            return self._wake.is_set() or self._stop_evt.is_set()
        interrupted = self._wake.wait(timeout=secs)
        return interrupted or self._stop_evt.is_set()

    def _run(self):
        while not self._stop_evt.is_set():
            self._wake.clear()
            with self._lock:
                active, interval, duty = self._active, self._interval_s, self._duty
            if not active:
                self._set_phase('idle')
                self._stop_both()
                self._wait(1.0)
                continue

            on_out = interval * duty
            on_in = self._inflow_ratio * on_out
            t0 = time.monotonic()

            # Dose: both pumps ON; inflow stops first, outflow runs a touch longer.
            self._set_phase('dosing')
            try:
                self._run_fn(self._outflow_name, self._rate)
                self._run_fn(self._inflow_name, self._rate)
            except Exception as e:
                logger.error("pump start failed: %s", e)
                self._stop_both()
                self._wait(1.0)
                continue

            interrupted = self._wait(on_in)
            self._stop_one(self._inflow_name)
            if not interrupted:
                interrupted = self._wait(on_out - on_in)
            self._stop_one(self._outflow_name)
            if interrupted:
                continue   # regime changed/stopped — pumps are off; re-read at top

            # Idle for the remainder of the interval (accounting for call overhead).
            self._set_phase('wait')
            self._wait(interval - (time.monotonic() - t0))

        self._stop_both()


# Module-level singleton used by main.py
pump_controller = PumpController()
