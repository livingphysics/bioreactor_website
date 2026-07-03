"""
Heater control engine for the bioreactor API.

Runs a background control loop (1 Hz) that drives the peltier either by stepping
through an uploaded schedule (`duty,direction,hold_s` CSV) or by holding a PID
temperature setpoint, logging each sample to a fresh bioreactor data CSV. It
mirrors hardware_testing/heater_gui.py's schedule runner and safety cutoffs:
abort (peltier off) if the bath temperature reads NaN for 15 consecutive samples
or leaves the [2, 60] °C window.

The loop lives here (on the Pi, next to the hardware) rather than on the remote
monitor so that a dropped network link can never strand the heater — the safety
supervision runs locally regardless of the tunnel/droplet.

Also works in simulation mode (no `Bioreactor`): it advances the schedule/PID in
software and reflects state into the API's sim_state dict so the UI can be
developed without a Pi. No data file is written in simulation.
"""
import os
import csv
import time
import random
import logging
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)

# Safety window for an unattended run — mirror heater_gui.py constants.
TEMP_MAX_C = 60.0
TEMP_MIN_C = 2.0
MAX_NAN_SAMPLES = 15
SAMPLE_PERIOD_S = 1.0


class ScheduleError(ValueError):
    """Raised when an uploaded schedule fails to parse or validate."""


def parse_schedule(text: str, max_heat: float = 70.0, max_cool: float = 100.0) -> List[Dict[str, Any]]:
    """Parse a heater schedule CSV into a list of steps.

    Format (same as hardware_testing/peltier_schedule_example.csv): lines of
    ``duty,direction,hold_s`` with optional ``#`` comment lines and an optional
    ``duty,direction,hold_s`` header row. duty is 0-100 (capped per direction),
    direction is ``heat`` or ``cool``, hold_s > 0.

    Returns [{'duty': float, 'direction': str, 'hold_s': float}, ...].
    Raises ScheduleError on any malformed/out-of-range row.
    """
    steps: List[Dict[str, Any]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split(',')]
        if parts and parts[0].lower() == 'duty':
            continue  # header row
        if len(parts) < 3:
            raise ScheduleError(f"line {lineno}: expected 'duty,direction,hold_s', got {raw!r}")
        try:
            duty = float(parts[0])
            direction = parts[1].lower()
            hold_s = float(parts[2])
        except ValueError:
            raise ScheduleError(f"line {lineno}: could not parse numbers in {raw!r}")
        if direction not in ('heat', 'cool'):
            raise ScheduleError(f"line {lineno}: direction must be 'heat' or 'cool', got {parts[1]!r}")
        if hold_s <= 0:
            raise ScheduleError(f"line {lineno}: hold_s must be > 0, got {hold_s}")
        limit = max_heat if direction == 'heat' else max_cool
        if not (0.0 <= duty <= limit):
            raise ScheduleError(f"line {lineno}: duty {duty} out of range [0, {limit}] for '{direction}'")
        steps.append({'duty': duty, 'direction': direction, 'hold_s': hold_s})
    if not steps:
        raise ScheduleError("no schedule steps found")
    return steps


class HeaterController:
    """Single background control loop for schedule / PID heater runs.

    Thread-safe: `start_*`, `stop`, and `status` may be called from FastAPI
    request threads; the control loop runs on its own daemon thread. All shared
    state is guarded by a re-entrant lock.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        # Dependencies (set via configure()).
        self._bio = None
        self._sim = True
        self._sim_state: Optional[dict] = None
        self._io = None                       # bioreactor_v3.src.io module
        self._pid: Optional[Callable] = None  # temperature_pid_controller
        self._measure: Optional[Callable] = None  # measure_and_record_sensors
        self._data_dir: Optional[str] = None
        self._max_heat = 70.0
        self._max_cool = 100.0

        self._reset_state()

    # ------------------------------------------------------------------ setup
    def configure(self, *, bio, sim, sim_state, io_module, pid_func, measure_func,
                  data_dir, max_heat, max_cool):
        with self._lock:
            self._bio = bio
            self._sim = sim
            self._sim_state = sim_state
            self._io = io_module
            self._pid = pid_func
            self._measure = measure_func
            self._data_dir = data_dir
            self._max_heat = max_heat
            self._max_cool = max_cool

    @property
    def max_heat(self) -> float:
        return self._max_heat

    @property
    def max_cool(self) -> float:
        return self._max_cool

    def _reset_state(self):
        self.mode = 'idle'            # 'idle' | 'schedule' | 'pid'
        self.active = False
        self.steps: Optional[List[Dict[str, Any]]] = None
        self.step_idx = -1
        self.seg_end: Optional[float] = None
        self.run_t0: Optional[float] = None
        self.setpoint: Optional[float] = None
        self.gains: Optional[Dict[str, float]] = None
        self.data_file: Optional[str] = None
        self.completed = False
        self.aborted = False
        self.abort_reason: Optional[str] = None
        self.nan_count = 0
        self.last: Dict[str, Any] = {}

    # ---------------------------------------------------------------- control
    def start_schedule(self, steps: List[Dict[str, Any]]):
        with self._lock:
            if self.active:
                raise RuntimeError("a heater run is already active")
            self._reset_state()
            self.mode = 'schedule'
            self.steps = steps
            self.step_idx = -1
            self.seg_end = None
            self._begin()

    def start_pid(self, setpoint: float, kp: float, ki: float, kd: float):
        with self._lock:
            if self.active:
                raise RuntimeError("a heater run is already active")
            self._reset_state()
            self.mode = 'pid'
            self.setpoint = float(setpoint)
            self.gains = {'kp': float(kp), 'ki': float(ki), 'kd': float(kd)}
            # Clear any PID integrator state left on the bioreactor from a prior run.
            if self._bio is not None:
                for attr in ('_temp_integral', '_temp_last_error',
                             '_temp_last_time', '_temp_last_derivative'):
                    if hasattr(self._bio, attr):
                        delattr(self._bio, attr)
            self._begin()

    def _begin(self):
        """Start the loop. Caller must hold the lock."""
        self.active = True
        self.run_t0 = time.time()
        self.nan_count = 0
        self.completed = False
        self.aborted = False
        self.abort_reason = None
        if not self._sim:
            self._open_data_file()
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="heater-control")
        self._thread.start()
        logger.info("Heater run started: mode=%s", self.mode)

    def stop(self, reason: Optional[str] = None) -> dict:
        """Stop any active run and turn the peltier off. Safe to call when idle."""
        with self._lock:
            was_active = self.active
            self.active = False
            if reason and was_active:
                self.abort_reason = reason
            thread = self._thread
        self._stop_evt.set()
        if thread and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=3.0)
        self._all_off()
        if not self._sim:
            self._close_data_file()
        if was_active:
            logger.info("Heater run stopped%s", f" ({reason})" if reason else "")
        return self.status()

    # ---------------------------------------------------------------- data IO
    def _open_data_file(self):
        os.makedirs(self._data_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        suffix = 'peltier_schedule' if self.mode == 'schedule' else 'pid_run'
        path = os.path.join(self._data_dir, f"{ts}_{suffix}.csv")
        f = open(path, 'w', newline='')
        writer = csv.DictWriter(f, fieldnames=self._bio.fieldnames)
        writer.writeheader()
        # measure_and_record_sensors() writes through these bioreactor attributes.
        self._bio.out_file = f
        self._bio.out_file_path = path
        self._bio.writer = writer
        self.data_file = path

    def _close_data_file(self):
        if self._bio is None:
            return
        f = getattr(self._bio, 'out_file', None)
        if f is not None:
            try:
                f.flush()
                f.close()
            except Exception:
                pass
        self._bio.writer = None
        self._bio.out_file = None

    # ------------------------------------------------------------- actuation
    def _apply_peltier(self, duty: float, direction: str):
        if self._sim:
            self._sim_state['peltier_duty'] = duty
            self._sim_state['peltier_direction'] = direction
            return
        if duty <= 0:
            self._io.stop_peltier(self._bio)
        else:
            self._io.set_peltier_power(self._bio, duty, forward=direction)

    def _all_off(self):
        try:
            if self._sim:
                if self._sim_state is not None:
                    self._sim_state['peltier_duty'] = 0.0
            elif self._io is not None and self._bio is not None:
                self._io.stop_peltier(self._bio)
        except Exception as e:
            logger.error("Failed to stop peltier: %s", e)

    # ----------------------------------------------------------------- loop
    def _run(self):
        while not self._stop_evt.is_set():
            tick_start = time.time()
            try:
                self._tick()
            except Exception as e:
                logger.error("Heater control tick error: %s", e, exc_info=True)
            if not self.active:
                break
            self._stop_evt.wait(max(0.0, SAMPLE_PERIOD_S - (time.time() - tick_start)))

    def _tick(self):
        with self._lock:
            if not self.active:
                return
            if self.mode == 'schedule':
                self._advance_schedule()
                if not self.active:   # schedule just completed
                    return
            elif self.mode == 'pid':
                self._pid_step()
            self._sample_and_supervise()

    def _advance_schedule(self):
        now = time.time()
        if self.seg_end is not None and now < self.seg_end:
            return  # still holding the current step
        self.step_idx += 1
        if self.step_idx >= len(self.steps):
            self._finish(completed=True)
            return
        step = self.steps[self.step_idx]
        self._apply_peltier(step['duty'], step['direction'])
        self.seg_end = now + step['hold_s']

    def _pid_step(self):
        if self._sim:
            return  # no thermal model in simulation
        self._pid(self._bio, setpoint=self.setpoint, **self.gains)

    def _sample_and_supervise(self):
        if self._sim:
            duty = float(self._sim_state.get('peltier_duty', 0.0))
            direction = self._sim_state.get('peltier_direction', 'heat')
            temp = round(24.0 + random.uniform(-0.3, 0.3), 3)
            ambient = round(22.0 + random.uniform(-0.3, 0.3), 3)
            # unsigned supply current, signed negative for heating (matches GUI convention)
            current = round((duty / 100.0) * 5.0 * (1 if direction == 'cool' else -1), 3)
            self.last = {'temperature': temp, 'ambient_temp': ambient,
                         'peltier_current': current, 'peltier_duty': duty,
                         'direction': direction}
            return

        elapsed = time.time() - self.run_t0
        try:
            data = self._measure(self._bio, elapsed=elapsed)
        except Exception as e:
            logger.error("measure_and_record_sensors failed: %s", e)
            data = {}

        temp = data.get('temperature', float('nan'))
        ambient = data.get('ambient_temp', float('nan'))
        raw_current = data.get('peltier_current', float('nan'))
        forward = data.get('peltier_forward', 1.0)
        # INA228 reads unsigned; sign negative when heating (forward == 0), per GUI.
        current = raw_current if (forward != forward or forward) else -raw_current
        self.last = {
            'temperature': temp,
            'ambient_temp': ambient,
            'peltier_current': current,
            'peltier_duty': data.get('peltier_duty', float('nan')),
            'direction': 'cool' if forward else 'heat',
        }

        # Safety supervision (mirror heater_gui._tick)
        if temp != temp:  # NaN
            self.nan_count += 1
            if self.nan_count >= MAX_NAN_SAMPLES:
                self._finish(completed=False,
                             abort=f"no valid bath temperature for {self.nan_count} samples")
        else:
            self.nan_count = 0
            if temp > TEMP_MAX_C or temp < TEMP_MIN_C:
                self._finish(completed=False,
                             abort=f"bath {temp:.1f} °C outside [{TEMP_MIN_C:.0f}, {TEMP_MAX_C:.0f}] °C")

    def _finish(self, completed: bool, abort: Optional[str] = None):
        """End the run from inside the control thread. Caller holds the lock."""
        self.active = False
        self.completed = completed
        if abort:
            self.aborted = True
            self.abort_reason = abort
            logger.warning("Heater run aborted: %s", abort)
        self._stop_evt.set()
        self._all_off()
        if not self._sim:
            self._close_data_file()

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        with self._lock:
            st: Dict[str, Any] = {
                'active': self.active,
                'mode': self.mode,
                'completed': self.completed,
                'aborted': self.aborted,
                'abort_reason': self.abort_reason,
                'data_file': os.path.basename(self.data_file) if self.data_file else None,
                'last': self.last,
            }
            if self.run_t0 is not None:
                st['elapsed_s'] = round(time.time() - self.run_t0, 1)
            if self.mode == 'schedule' and self.steps is not None:
                st['step'] = min(max(0, self.step_idx + 1), len(self.steps))
                st['total_steps'] = len(self.steps)
                if 0 <= self.step_idx < len(self.steps):
                    st['current_step'] = self.steps[self.step_idx]
                st['remaining_steps'] = max(0, len(self.steps) - self.step_idx - 1)
                if self.seg_end is not None and self.active:
                    st['step_remaining_s'] = round(self.seg_end - time.time(), 1)
            if self.mode == 'pid':
                st['setpoint'] = self.setpoint
                st['gains'] = self.gains
            return st


# Module-level singleton used by main.py
heater = HeaterController()
