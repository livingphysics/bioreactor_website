"""
Relay controller for the bioreactor API.

Thin layer over the RelayDriver (which stores each relay's state, so toggle + GET
work). Maps the API's open/closed/toggle commands to the driver's energized bool:

    closed = energized (driver ON)   -- e.g. NO contact closed
    open   = de-energized (OFF)      -- the boot state

and manages the timed "command-wait-toggle" action: run a command now, then toggle
the relay after a delay (a one-shot timed pulse). Hardware access is delegated to
injected set/get fns (serialized on HARDWARE_LOCK in real mode), so this module runs
unchanged in simulation.
"""
import time
import logging
import threading

logger = logging.getLogger(__name__)


class RelayController:
    _CMD_ENERGIZED = {'open': False, 'closed': True}   # command -> driver state
    COMMANDS = ('open', 'closed', 'toggle')

    def __init__(self):
        self._lock = threading.Lock()
        self._set_fn = None        # set_fn(name, energized: bool)
        self._get_fn = None        # get_fn() -> {name: energized bool}
        self._names = []
        self._timers = {}          # name -> (Timer, fire_at_epoch)

    def configure(self, *, set_fn, get_fn, names):
        self._set_fn = set_fn
        self._get_fn = get_fn
        self._names = list(names)

    # ----------------------------------------------------------------- helpers
    def _energized(self, name) -> bool:
        return bool((self._get_fn() or {}).get(name, False))

    def _cancel_timer(self, name):
        with self._lock:
            entry = self._timers.pop(name, None)
        if entry:
            entry[0].cancel()

    # --------------------------------------------------------------------- API
    def apply(self, name, command) -> str:
        """Run one command ('open'|'closed'|'toggle'). Supersedes any pending timed
        toggle on that relay. Returns the new state string ('open'|'closed')."""
        if name not in self._names:
            raise KeyError(name)
        self._cancel_timer(name)          # a fresh command wins over a scheduled toggle
        if command == 'toggle':
            target = not self._energized(name)
        elif command in self._CMD_ENERGIZED:
            target = self._CMD_ENERGIZED[command]
        else:
            raise ValueError(f"bad relay command {command!r} (use {'/'.join(self.COMMANDS)})")
        self._set_fn(name, target)
        return 'closed' if target else 'open'

    def timed(self, name, command, duration_s) -> str:
        """command-wait-toggle: run `command` now, then toggle after `duration_s`."""
        state = self.apply(name, command)     # also cancels any prior timer
        duration_s = float(duration_s)
        if duration_s > 0:
            t = threading.Timer(duration_s, self._fire_toggle, args=(name,))
            t.daemon = True
            with self._lock:
                self._timers[name] = (t, time.time() + duration_s)
            t.start()
        return state

    def _fire_toggle(self, name):
        with self._lock:
            self._timers.pop(name, None)
        try:
            self.apply(name, 'toggle')
            logger.info("Relay %s: timed toggle fired", name)
        except Exception as e:
            logger.error("relay timed toggle failed for %s: %s", name, e)

    def states(self) -> dict:
        g = self._get_fn() or {}
        return {n: ('closed' if g.get(n, False) else 'open') for n in self._names}

    def status(self) -> dict:
        now = time.time()
        with self._lock:
            pending = {n: round(max(0.0, fire_at - now), 1) for n, (_, fire_at) in self._timers.items()}
        return {'states': self.states(), 'pending': pending}

    def stop(self):
        with self._lock:
            timers = [e[0] for e in self._timers.values()]
            self._timers.clear()
        for t in timers:
            t.cancel()


# Module-level singleton used by main.py
relay_controller = RelayController()
