"""
Bioreactor API — minimal FastAPI server wrapping bioreactor_v3 hardware.

Start with: HARDWARE_MODE=simulation uvicorn main:app --port 9000
Interactive docs: http://localhost:9000/docs
"""
import os
import sys
import math
import random
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import camera
from auth import verify_token, limiter, RATE_LIMIT
from control import heater, parse_schedule, ScheduleError, HARDWARE_LOCK, InsufficientStorageError
from history import history
from od_sampler import od_sampler

# Where the rolling sensor-history buffer is persisted (survives restarts).
HISTORY_FILE = Path(__file__).parent / 'sensor_history.json'

# Directory where the bioreactor writes its data CSVs (run files live here).
DATA_DIR = Path(__file__).parent / 'bioreactor_v3' / 'src' / 'bioreactor_data'

# Add bioreactor_v3 parent to path so we can import bioreactor_v3.src.*
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
bioreactor = None  # Bioreactor instance (None in simulation mode)
simulation_mode = True
initialized_components: Dict[str, bool] = {}

# Optical density. The sampler always reads every AVAILABLE source (od + eyespy);
# `od_mode` is the shared *display* selection the frontend defaults to (settable via
# POST /api/od/mode). Set in lifespan.
od_mode = 'none'          # display mode: 'od' | 'eyespy' | 'both' | 'none'
od_available = {'od': False, 'eyespy': False}
od_channels = {'od': [], 'eyespy': []}   # source -> ordered channel/board names

# Last commanded LED power (the driver doesn't report it back, so we shadow it here).
led_power = 0.0


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

# -- LED
class LEDControlRequest(BaseModel):
    power: float = Field(ge=0, le=100, description="LED power 0-100%")

class LEDState(BaseModel):
    status: str
    power: float
    active: bool

# -- Peltier
class PeltierControlRequest(BaseModel):
    duty_cycle: float = Field(ge=0, le=100, description="PWM duty cycle 0-100%")
    direction: str = Field(pattern="^(heat|cool|forward|reverse)$", description="heat/cool/forward/reverse")

class PeltierState(BaseModel):
    status: str
    duty_cycle: float
    direction: str
    active: bool

# -- Stirrer
class StirrerControlRequest(BaseModel):
    duty_cycle: float = Field(ge=0, le=100, description="PWM duty cycle 0-100%")

class StirrerState(BaseModel):
    status: str
    duty_cycle: float
    active: bool

# -- Ring Light
class RingLightControlRequest(BaseModel):
    red: int = Field(ge=0, le=255)
    green: int = Field(ge=0, le=255)
    blue: int = Field(ge=0, le=255)
    pixel_index: Optional[int] = Field(None, ge=0, description="Specific pixel or None for all")

class RingLightState(BaseModel):
    status: str
    red: int
    green: int
    blue: int
    active: bool

# -- Pumps
class PumpControlRequest(BaseModel):
    pump_name: str = Field(description="Pump identifier (e.g. 'inflow', 'outflow')")
    velocity: float = Field(description="Flow rate in mL/s (positive=forward, negative=reverse)")

class PumpState(BaseModel):
    status: str
    pump_name: str
    velocity: float
    active: bool

# -- Relays
class RelayControlRequest(BaseModel):
    relay_name: str = Field(description="Relay identifier")
    state: bool = Field(description="True=on, False=off")

class RelayState(BaseModel):
    status: str
    states: Dict[str, bool]

# -- Sensors (response only)
class TemperatureState(BaseModel):
    status: str
    temperature: Optional[float]
    unit: str = "celsius"

class ODState(BaseModel):
    status: str
    voltages: list
    unit: str = "volts"

class EyespyState(BaseModel):
    status: str
    voltages: list
    unit: str = "volts"

class CO2State(BaseModel):
    status: str
    co2_ppm: float
    unit: str = "ppm"

class O2State(BaseModel):
    status: str
    o2_percent: float
    unit: str = "percent"

class AmbientTempState(BaseModel):
    status: str
    temperature: Optional[float]
    unit: str = "celsius"

class PeltierCurrentState(BaseModel):
    status: str
    current: Optional[float]
    unit: str = "amps"

# -- Heater PID run
class HeaterPIDRequest(BaseModel):
    setpoint: float = Field(description="Target bath temperature (°C)")
    kp: float = Field(12.0, description="Proportional gain")
    ki: float = Field(0.015, description="Integral gain")
    kd: float = Field(0.0, description="Derivative gain")


# ---------------------------------------------------------------------------
# Simulation state (tracks what actuators are "set to" in sim mode)
# ---------------------------------------------------------------------------
sim_state = {
    'led_power': 0.0,
    'peltier_duty': 0.0,
    'peltier_direction': 'forward',
    'stirrer_duty': 0.0,
    'ring_r': 0, 'ring_g': 0, 'ring_b': 0,
    'pump_name': '', 'pump_velocity': 0.0,
    'relays': {},
}


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bioreactor, simulation_mode, initialized_components

    hardware_mode = os.getenv("HARDWARE_MODE", "simulation")
    simulation_mode = (hardware_mode != "real")

    logger.info(f"Hardware mode: {hardware_mode}")

    if not simulation_mode:
        try:
            from bioreactor_v3.src.bioreactor import Bioreactor
            from bioreactor_v3.src import io as bio_io
            from bioreactor_v3.src.utils import (
                temperature_pid_controller, measure_and_record_sensors,
            )
            from config import Config
            config = Config()
            bioreactor = Bioreactor(config)
            initialized_components = dict(bioreactor._initialized)
            logger.info(f"Hardware initialized: {initialized_components}")
            # The bioreactor opens a startup data file (header only). The heater
            # engine manages its own per-run files, so release + remove the stray
            # startup CSV now (nothing has written to it yet) so it can't linger as
            # the "latest" download.
            try:
                startup_path = getattr(bioreactor, 'out_file_path', None)
                if getattr(bioreactor, 'out_file', None) is not None:
                    bioreactor.out_file.close()
                bioreactor.writer = None
                bioreactor.out_file = None
                if startup_path and os.path.exists(startup_path):
                    os.remove(startup_path)
            except Exception as e:
                logger.warning(f"Could not release startup data file: {e}")
            heater.configure(
                bio=bioreactor, sim=False, sim_state=None, io_module=bio_io,
                pid_func=temperature_pid_controller, measure_func=measure_and_record_sensors,
                data_dir=str(DATA_DIR),
                max_heat=getattr(config, 'PELTIER_MAX_DUTY_HEAT', 70.0),
                max_cool=getattr(config, 'PELTIER_MAX_DUTY_COOL', 100.0),
                retention_max_mb=getattr(config, 'DATA_RETENTION_MAX_MB', 1000),
                retention_keep=getattr(config, 'DATA_RETENTION_KEEP', 10),
                min_free_mb=getattr(config, 'DATA_MIN_FREE_MB', 500),
                od_power_fn=lambda: od_sampler.led_power,   # live dropdown value
            )
            heater.prune()  # trim old run files on startup
        except Exception as e:
            logger.error(f"Hardware init failed: {e}", exc_info=True)
            bioreactor = None
            simulation_mode = True
    else:
        logger.info("Simulation mode — no hardware")
        # In simulation, pretend all non-infrastructure components are initialized
        from config import Config
        config = Config()
        for name, enabled in config.INIT_COMPONENTS.items():
            if name != 'i2c' and enabled:
                initialized_components[name] = True

    if simulation_mode:
        heater.configure(
            bio=None, sim=True, sim_state=sim_state, io_module=None,
            pid_func=None, measure_func=None, data_dir=str(DATA_DIR),
            max_heat=70.0, max_cool=100.0,
        )

    # Optical-density sources available (from config.py via what actually initialized).
    global od_mode, od_channels, od_available
    od_available = {'od': bool(initialized_components.get('optical_density')),
                    'eyespy': bool(initialized_components.get('eyespy_adc'))}
    od_channels = {
        'od': list(getattr(config, 'OD_ADC_CHANNELS', {}).keys()) if od_available['od'] else [],
        'eyespy': list(getattr(config, 'EYESPY_ADC', {}).keys()) if od_available['eyespy'] else [],
    }
    # Default display mode: both if both available, else whichever, else none.
    if od_available['od'] and od_available['eyespy']:
        od_mode = 'both'
    elif od_available['od']:
        od_mode = 'od'
    elif od_available['eyespy']:
        od_mode = 'eyespy'
    else:
        od_mode = 'none'
    logger.info("Optical density: available=%s default mode=%s channels=%s",
                od_available, od_mode, od_channels)

    # IR-gated OD sampler: pulses the LED per reading (on -> settle -> read -> off),
    # interleaving OD/eyespy when both are present. Its latest reading feeds /api/state
    # and the history buffer (via _read_od). Started before history so OD is available.
    if od_available['od'] or od_available['eyespy']:
        if simulation_mode:
            od_set_led, od_read_fns = (lambda p: None), {}
        else:
            from bioreactor_v3.src.io import (
                set_led as _od_set_led, read_voltage as _od_rv,
                read_eyespy_voltage as _od_rev,
            )
            od_set_led = lambda p: _od_set_led(bioreactor, p)
            od_read_fns = {'od': lambda ch: _od_rv(bioreactor, ch),
                           'eyespy': lambda b: _od_rev(bioreactor, b)}
        od_sampler.configure(
            hw_lock=HARDWARE_LOCK, set_led=od_set_led, read_fns=od_read_fns,
            sources=[('od', od_channels['od']), ('eyespy', od_channels['eyespy'])],
            sim=simulation_mode,
            enabled=getattr(config, 'OD_SAMPLE_ENABLED', True),
            led_power=getattr(config, 'OD_LED_POWER', 10.0),
            settle_s=getattr(config, 'OD_SETTLE_S', 0.5),
            post_read_s=getattr(config, 'OD_POST_READ_S', 0.1),
            period_s=getattr(config, 'OD_PULSE_PERIOD_S', 1.0),
        )
        od_sampler.start()

    # Rolling sensor-history buffer (samples continuously, independent of runs).
    if getattr(config, 'HISTORY_ENABLED', True):
        history.configure(
            sample_fn=_read_signals,
            persist_path=str(HISTORY_FILE),
            interval_s=getattr(config, 'HISTORY_INTERVAL_S', 10),
            window_s=int(getattr(config, 'HISTORY_WINDOW_H', 24)) * 3600,
        )
        history.start()

    yield

    od_sampler.stop()
    history.stop()
    heater.stop()
    if bioreactor:
        bioreactor.finish()
        logger.info("Hardware cleanup complete")


# ---------------------------------------------------------------------------
# Create app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Bioreactor API",
    description="Minimal REST API for bioreactor_v3 hardware control",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_token)],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_component(name: str):
    """Raise 503 if component is not initialized."""
    if not initialized_components.get(name, False):
        raise HTTPException(status_code=503, detail=f"{name} not available")


# ---------------------------------------------------------------------------
# System endpoints (always available)
# ---------------------------------------------------------------------------

@app.get("/health")
@limiter.limit(RATE_LIMIT)
async def health(request: Request):
    return {
        "status": "healthy",
        "hardware_mode": "simulation" if simulation_mode else "real",
        "hardware_available": bioreactor is not None,
        "initialized_components": initialized_components,
    }


@app.get("/api/state")
@limiter.limit(RATE_LIMIT)
async def state(request: Request):
    """Aggregate heater-relevant signals in one call (for the live monitor).

    Returns bath temp, ambient temp, signed peltier current, peltier duty/direction,
    and the current heater-run status. Unavailable components report null.
    """
    import time as _time

    def _sensor(name, reader):
        if not initialized_components.get(name, False):
            return None
        try:
            v = reader()
        except Exception as e:
            logger.warning("state read failed for %s: %s", name, e)
            return None
        if v is not None and isinstance(v, float) and math.isnan(v):
            return None
        return v

    if simulation_mode:
        temperature = round(36.5 + random.uniform(-0.5, 0.5), 2) if initialized_components.get('temp_sensor') else None
        ambient = round(22.0 + random.uniform(-1.0, 1.0), 2) if initialized_components.get('ambient_temp') else None
        current = round(random.uniform(0.0, 0.05), 3) if initialized_components.get('peltier_current') else None
        peltier = {"duty_cycle": sim_state['peltier_duty'],
                   "direction": sim_state['peltier_direction'],
                   "active": sim_state['peltier_duty'] > 0} if initialized_components.get('peltier_driver') else None
    else:
        from bioreactor_v3.src.io import (
            get_temperature, read_ambient_temp, read_peltier_current, get_peltier_state,
        )
        # Serialize bus access against the heater control loop (see control.HARDWARE_LOCK).
        with HARDWARE_LOCK:
            temperature = _sensor('temp_sensor', lambda: get_temperature(bioreactor, sensor_index=0))
            ambient = _sensor('ambient_temp', lambda: read_ambient_temp(bioreactor))
            current = _sensor('peltier_current', lambda: read_peltier_current(bioreactor))
            peltier = None
            forward = True
            if initialized_components.get('peltier_driver'):
                ps = get_peltier_state(bioreactor)
                if ps is not None:
                    duty, forward = ps
                    peltier = {"duty_cycle": duty,
                               "direction": "cool" if forward else "heat",
                               "active": duty > 0}
        # INA228 reads unsigned; sign negative when heating (forward False), per GUI convention
        if current is not None and not forward:
            current = -current

    return {
        "status": "success",
        "timestamp": _time.time(),
        "temperature": temperature,
        "ambient_temp": ambient,
        "peltier_current": current,
        "peltier": peltier,
        "heater": heater.status(),
        "od": _read_od(),
        "od_mode": od_mode,
        "od_channels": od_channels,
        "od_available": od_available,
        "od_sampling": od_sampler.status() if (od_available['od'] or od_available['eyespy']) else None,
        "led": {"power": led_power, "active": led_power > 0} if initialized_components.get('led') else None,
    }


@app.get("/api/capabilities")
@limiter.limit(RATE_LIMIT)
async def capabilities(request: Request):
    """Discover available components and their endpoint patterns."""
    caps = {}
    actuators = ['led', 'peltier_driver', 'stirrer', 'ring_light', 'pumps', 'relays']
    sensors = ['temp_sensor', 'ambient_temp', 'optical_density', 'eyespy_adc', 'co2_sensor', 'o2_sensor', 'peltier_current']

    for name in actuators:
        if initialized_components.get(name):
            caps[name] = {
                "type": "actuator",
                "control": f"/api/{name}/control",
                "state": f"/api/{name}/state",
            }
    for name in sensors:
        if initialized_components.get(name):
            caps[name] = {
                "type": "sensor",
                "state": f"/api/{name}/state",
            }
    return caps


# ---------------------------------------------------------------------------
# LED
# ---------------------------------------------------------------------------

@app.post("/api/led/control", response_model=LEDState)
@limiter.limit(RATE_LIMIT)
async def led_control(request: Request, req: LEDControlRequest):
    require_component('led')
    global led_power
    if simulation_mode:
        sim_state['led_power'] = req.power
        led_power = req.power
        return LEDState(status="success", power=req.power, active=req.power > 0)
    from bioreactor_v3.src.io import set_led
    with HARDWARE_LOCK:
        set_led(bioreactor, req.power)
    led_power = req.power   # shadow it (driver doesn't report last power)
    return LEDState(status="success", power=req.power, active=req.power > 0)


@app.get("/api/led/state", response_model=LEDState)
@limiter.limit(RATE_LIMIT)
async def led_state(request: Request):
    require_component('led')
    if simulation_mode:
        p = sim_state['led_power']
        return LEDState(status="success", power=p, active=p > 0)
    led = getattr(bioreactor, 'led_driver', None)
    power = getattr(led, '_last_power', 0.0) if led else 0.0
    return LEDState(status="success", power=power, active=power > 0)


# ---------------------------------------------------------------------------
# Peltier
# ---------------------------------------------------------------------------

@app.post("/api/peltier_driver/control", response_model=PeltierState)
@limiter.limit(RATE_LIMIT)
async def peltier_control(request: Request, req: PeltierControlRequest):
    require_component('peltier_driver')
    if heater.active:
        raise HTTPException(status_code=409,
                            detail="a heater run (schedule/PID) is active; stop it before manual control")
    if simulation_mode:
        sim_state['peltier_duty'] = req.duty_cycle
        sim_state['peltier_direction'] = req.direction
        return PeltierState(status="success", duty_cycle=req.duty_cycle, direction=req.direction, active=req.duty_cycle > 0)
    from bioreactor_v3.src.io import set_peltier_power
    with HARDWARE_LOCK:
        set_peltier_power(bioreactor, req.duty_cycle, req.direction)
    return PeltierState(status="success", duty_cycle=req.duty_cycle, direction=req.direction, active=req.duty_cycle > 0)


@app.get("/api/peltier_driver/state", response_model=PeltierState)
@limiter.limit(RATE_LIMIT)
async def peltier_state(request: Request):
    require_component('peltier_driver')
    if simulation_mode:
        d = sim_state['peltier_duty']
        return PeltierState(status="success", duty_cycle=d, direction=sim_state['peltier_direction'], active=d > 0)
    from bioreactor_v3.src.io import get_peltier_state
    state = get_peltier_state(bioreactor)
    if state:
        duty, fwd = state
        return PeltierState(status="success", duty_cycle=duty, direction="forward" if fwd else "reverse", active=duty > 0)
    return PeltierState(status="success", duty_cycle=0, direction="forward", active=False)


# ---------------------------------------------------------------------------
# Stirrer
# ---------------------------------------------------------------------------

@app.post("/api/stirrer/control", response_model=StirrerState)
@limiter.limit(RATE_LIMIT)
async def stirrer_control(request: Request, req: StirrerControlRequest):
    require_component('stirrer')
    if simulation_mode:
        sim_state['stirrer_duty'] = req.duty_cycle
        return StirrerState(status="success", duty_cycle=req.duty_cycle, active=req.duty_cycle > 0)
    from bioreactor_v3.src.io import set_stirrer_speed
    set_stirrer_speed(bioreactor, req.duty_cycle)
    return StirrerState(status="success", duty_cycle=req.duty_cycle, active=req.duty_cycle > 0)


@app.get("/api/stirrer/state", response_model=StirrerState)
@limiter.limit(RATE_LIMIT)
async def stirrer_state(request: Request):
    require_component('stirrer')
    if simulation_mode:
        d = sim_state['stirrer_duty']
        return StirrerState(status="success", duty_cycle=d, active=d > 0)
    driver = getattr(bioreactor, 'stirrer_driver', None)
    duty = getattr(driver, '_last_duty', 0.0) if driver else 0.0
    return StirrerState(status="success", duty_cycle=duty, active=duty > 0)


# ---------------------------------------------------------------------------
# Ring Light
# ---------------------------------------------------------------------------

@app.post("/api/ring_light/control", response_model=RingLightState)
@limiter.limit(RATE_LIMIT)
async def ring_light_control(request: Request, req: RingLightControlRequest):
    require_component('ring_light')
    if simulation_mode:
        sim_state['ring_r'] = req.red
        sim_state['ring_g'] = req.green
        sim_state['ring_b'] = req.blue
        active = any([req.red, req.green, req.blue])
        return RingLightState(status="success", red=req.red, green=req.green, blue=req.blue, active=active)
    from bioreactor_v3.src.io import set_ring_light
    set_ring_light(bioreactor, (req.red, req.green, req.blue), pixel=req.pixel_index)
    active = any([req.red, req.green, req.blue])
    return RingLightState(status="success", red=req.red, green=req.green, blue=req.blue, active=active)


@app.get("/api/ring_light/state", response_model=RingLightState)
@limiter.limit(RATE_LIMIT)
async def ring_light_state(request: Request):
    require_component('ring_light')
    if simulation_mode:
        r, g, b = sim_state['ring_r'], sim_state['ring_g'], sim_state['ring_b']
        return RingLightState(status="success", red=r, green=g, blue=b, active=any([r, g, b]))
    from bioreactor_v3.src.io import get_ring_light_color
    color = get_ring_light_color(bioreactor)
    if color:
        r, g, b = color
        return RingLightState(status="success", red=r, green=g, blue=b, active=any([r, g, b]))
    return RingLightState(status="success", red=0, green=0, blue=0, active=False)


# ---------------------------------------------------------------------------
# Pumps
# ---------------------------------------------------------------------------

@app.post("/api/pumps/control", response_model=PumpState)
@limiter.limit(RATE_LIMIT)
async def pumps_control(request: Request, req: PumpControlRequest):
    require_component('pumps')
    if simulation_mode:
        sim_state['pump_name'] = req.pump_name
        sim_state['pump_velocity'] = req.velocity
        return PumpState(status="success", pump_name=req.pump_name, velocity=req.velocity, active=req.velocity != 0)
    from bioreactor_v3.src.io import change_pump
    change_pump(bioreactor, req.pump_name, req.velocity)
    return PumpState(status="success", pump_name=req.pump_name, velocity=req.velocity, active=req.velocity != 0)


@app.get("/api/pumps/state", response_model=PumpState)
@limiter.limit(RATE_LIMIT)
async def pumps_state(request: Request):
    require_component('pumps')
    if simulation_mode:
        return PumpState(status="success", pump_name=sim_state['pump_name'], velocity=sim_state['pump_velocity'], active=sim_state['pump_velocity'] != 0)
    return PumpState(status="success", pump_name="all", velocity=0.0, active=bool(getattr(bioreactor, 'pumps', None)))


# ---------------------------------------------------------------------------
# Relays
# ---------------------------------------------------------------------------

@app.post("/api/relays/control", response_model=RelayState)
@limiter.limit(RATE_LIMIT)
async def relays_control(request: Request, req: RelayControlRequest):
    require_component('relays')
    if simulation_mode:
        sim_state['relays'][req.relay_name] = req.state
        return RelayState(status="success", states=sim_state['relays'])
    from bioreactor_v3.src.io import relay_on, relay_off
    if req.state:
        relay_on(bioreactor, req.relay_name)
    else:
        relay_off(bioreactor, req.relay_name)
    from bioreactor_v3.src.io import get_all_relay_states
    return RelayState(status="success", states=get_all_relay_states(bioreactor))


@app.get("/api/relays/state", response_model=RelayState)
@limiter.limit(RATE_LIMIT)
async def relays_state(request: Request):
    require_component('relays')
    if simulation_mode:
        return RelayState(status="success", states=sim_state['relays'])
    from bioreactor_v3.src.io import get_all_relay_states
    return RelayState(status="success", states=get_all_relay_states(bioreactor))


# ---------------------------------------------------------------------------
# Temperature Sensor
# ---------------------------------------------------------------------------

@app.get("/api/temp_sensor/state", response_model=TemperatureState)
@limiter.limit(RATE_LIMIT)
async def temp_sensor_state(request: Request):
    require_component('temp_sensor')
    if simulation_mode:
        return TemperatureState(status="success", temperature=round(36.5 + random.uniform(-0.5, 0.5), 2))
    from bioreactor_v3.src.io import get_temperature
    temp = get_temperature(bioreactor, sensor_index=0)
    if temp is not None and isinstance(temp, float) and math.isnan(temp):
        temp = None
    return TemperatureState(status="success", temperature=temp)


# ---------------------------------------------------------------------------
# Ambient Temperature Sensor (PCT2075)
# ---------------------------------------------------------------------------

@app.get("/api/ambient_temp/state", response_model=AmbientTempState)
@limiter.limit(RATE_LIMIT)
async def ambient_temp_state(request: Request):
    require_component('ambient_temp')
    if simulation_mode:
        return AmbientTempState(status="success", temperature=round(22.0 + random.uniform(-1.0, 1.0), 2))
    from bioreactor_v3.src.io import read_ambient_temp
    temp = read_ambient_temp(bioreactor)
    if temp is not None and isinstance(temp, float) and math.isnan(temp):
        temp = None
    return AmbientTempState(status="success", temperature=temp)


# ---------------------------------------------------------------------------
# Optical Density
# ---------------------------------------------------------------------------

@app.get("/api/optical_density/state", response_model=ODState)
@limiter.limit(RATE_LIMIT)
async def od_state(request: Request):
    require_component('optical_density')
    if simulation_mode:
        channels = getattr(_get_config(), 'OD_ADC_CHANNELS', {'135': 'A0', 'Ref': 'A1', '90': 'A2'})
        voltages = [round(random.uniform(0.5, 2.5), 4) for _ in channels]
        return ODState(status="success", voltages=voltages)
    from bioreactor_v3.src.io import read_voltage
    voltages = []
    if hasattr(bioreactor, 'cfg') and hasattr(bioreactor.cfg, 'OD_ADC_CHANNELS'):
        for ch_name in bioreactor.cfg.OD_ADC_CHANNELS.keys():
            v = read_voltage(bioreactor, ch_name)
            voltages.append(None if (v is None or (isinstance(v, float) and math.isnan(v))) else v)
    return ODState(status="success", voltages=voltages)


# ---------------------------------------------------------------------------
# Eyespy ADC
# ---------------------------------------------------------------------------

@app.get("/api/eyespy_adc/state", response_model=EyespyState)
@limiter.limit(RATE_LIMIT)
async def eyespy_state(request: Request):
    require_component('eyespy_adc')
    if simulation_mode:
        boards = getattr(_get_config(), 'EYESPY_ADC', {})
        voltages = [round(random.uniform(1.0, 3.0), 4) for _ in boards]
        return EyespyState(status="success", voltages=voltages)
    from bioreactor_v3.src.io import read_eyespy_voltage
    voltages = []
    if hasattr(bioreactor, 'cfg') and hasattr(bioreactor.cfg, 'EYESPY_ADC'):
        for board_name in bioreactor.cfg.EYESPY_ADC.keys():
            v = read_eyespy_voltage(bioreactor, board_name)
            voltages.append(None if (v is None or (isinstance(v, float) and math.isnan(v))) else v)
    return EyespyState(status="success", voltages=voltages)


# ---------------------------------------------------------------------------
# CO2 Sensor
# ---------------------------------------------------------------------------

@app.get("/api/co2_sensor/state", response_model=CO2State)
@limiter.limit(RATE_LIMIT)
async def co2_state(request: Request):
    require_component('co2_sensor')
    if simulation_mode:
        return CO2State(status="success", co2_ppm=round(400 + random.uniform(-20, 20), 1))
    from bioreactor_v3.src.io import read_co2
    ppm = read_co2(bioreactor)
    return CO2State(status="success", co2_ppm=float(ppm) if ppm is not None else 0.0)


# ---------------------------------------------------------------------------
# O2 Sensor
# ---------------------------------------------------------------------------

@app.get("/api/o2_sensor/state", response_model=O2State)
@limiter.limit(RATE_LIMIT)
async def o2_state(request: Request):
    require_component('o2_sensor')
    if simulation_mode:
        return O2State(status="success", o2_percent=round(20.9 + random.uniform(-0.5, 0.5), 2))
    from bioreactor_v3.src.io import read_o2
    pct = read_o2(bioreactor)
    return O2State(status="success", o2_percent=float(pct) if pct is not None else 0.0)


# ---------------------------------------------------------------------------
# Peltier Current Sensor (INA228)
# ---------------------------------------------------------------------------

@app.get("/api/peltier_current/state", response_model=PeltierCurrentState)
@limiter.limit(RATE_LIMIT)
async def peltier_current_state(request: Request):
    require_component('peltier_current')
    if simulation_mode:
        return PeltierCurrentState(status="success", current=round(random.uniform(0.0, 6.0), 3))
    from bioreactor_v3.src.io import read_peltier_current
    current = read_peltier_current(bioreactor)
    if current is not None and isinstance(current, float) and math.isnan(current):
        current = None
    return PeltierCurrentState(status="success", current=current)


# ---------------------------------------------------------------------------
# Heater control engine (schedule + PID) — runs on the Pi, next to the hardware
# ---------------------------------------------------------------------------

@app.post("/api/heater/schedule")
@limiter.limit(RATE_LIMIT)
async def heater_schedule(request: Request):
    """Upload a peltier schedule CSV (duty,direction,hold_s) and start running it.

    Body is the raw CSV text (Content-Type text/plain or text/csv). Same format
    as heater_gui / peltier_schedule_example.csv.
    """
    require_component('peltier_driver')
    raw = await request.body()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="schedule body must be UTF-8 text")
    try:
        steps = parse_schedule(text, max_heat=heater.max_heat, max_cool=heater.max_cool)
    except ScheduleError as e:
        raise HTTPException(status_code=400, detail=f"invalid schedule: {e}")
    try:
        heater.start_schedule(steps)
    except InsufficientStorageError as e:
        raise HTTPException(status_code=507, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    total_hold = round(sum(s['hold_s'] for s in steps), 1)
    return {"status": "success", "mode": "schedule",
            "total_steps": len(steps), "total_duration_s": total_hold,
            **heater.status()}


@app.post("/api/heater/pid")
@limiter.limit(RATE_LIMIT)
async def heater_pid(request: Request, req: HeaterPIDRequest):
    """Start a PID run that holds the bath at `setpoint` °C (heater_gui PID mode)."""
    require_component('peltier_driver')
    if not simulation_mode:
        require_component('temp_sensor')
    try:
        heater.start_pid(req.setpoint, req.kp, req.ki, req.kd)
    except InsufficientStorageError as e:
        raise HTTPException(status_code=507, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "success", "mode": "pid", **heater.status()}


@app.post("/api/heater/stop")
@limiter.limit(RATE_LIMIT)
async def heater_stop(request: Request):
    """Stop any active schedule/PID run and turn the peltier off."""
    status = heater.stop(reason="stopped via API")
    return {"status": "success", **status}


@app.get("/api/heater/status")
@limiter.limit(RATE_LIMIT)
async def heater_status(request: Request):
    """Current heater-run state (mode, step/progress, last sample, abort reason)."""
    return heater.status()


# ---------------------------------------------------------------------------
# Sensor history (rolling 24h buffer for the live plot)
# ---------------------------------------------------------------------------

@app.get("/api/history")
@limiter.limit(RATE_LIMIT)
async def api_history(request: Request, since: int = 0):
    """Rolling history of temp/ambient/current. `?since=<ms>` returns only points
    newer than that timestamp (cheap incremental polling)."""
    return {"status": "success", "interval_s": history.interval_s,
            "od_mode": od_mode, "od_channels": od_channels, "od_available": od_available,
            "points": history.get(since_ms=since)}


class ODModeRequest(BaseModel):
    mode: str = Field(pattern="^(od|eyespy|both|none)$", description="od | eyespy | both")


def _valid_od_modes():
    modes = []
    if od_available['od']:
        modes.append('od')
    if od_available['eyespy']:
        modes.append('eyespy')
    if od_available['od'] and od_available['eyespy']:
        modes.append('both')
    return modes or ['none']


@app.post("/api/od/mode")
@limiter.limit(RATE_LIMIT)
async def set_od_mode(request: Request, req: ODModeRequest):
    """Set the shared optical-density display mode (od | eyespy | both)."""
    global od_mode
    valid = _valid_od_modes()
    if req.mode not in valid:
        raise HTTPException(status_code=400, detail=f"mode must be one of {valid}")
    od_mode = req.mode
    return {"status": "success", "od_mode": od_mode,
            "od_channels": od_channels, "od_available": od_available}


class ODSamplingRequest(BaseModel):
    enabled: Optional[bool] = Field(default=None, description="turn IR-gated OD sampling on/off")
    led_power: Optional[float] = Field(default=None, ge=0, le=100,
                                       description="IR LED %% used for each gated reading")


@app.post("/api/od/sampling")
@limiter.limit(RATE_LIMIT)
async def set_od_sampling(request: Request, req: ODSamplingRequest):
    """Control the IR-gated OD measurement: on/off + per-reading LED power.

    The LED only lights briefly during each gated reading (never steady-on); `enabled`
    gates whether the sampler runs at all, `led_power` sets the illumination level."""
    if not (od_available['od'] or od_available['eyespy']):
        raise HTTPException(status_code=503, detail="No optical-density source available")
    if req.enabled is None and req.led_power is None:
        raise HTTPException(status_code=400, detail="provide 'enabled' and/or 'led_power'")
    cfg = od_sampler.set_config(enabled=req.enabled, led_power=req.led_power)
    return {"status": "success", "od_sampling": cfg}


# ---------------------------------------------------------------------------
# Data files (download the most recent bioreactor run CSV)
# ---------------------------------------------------------------------------

def _list_data_files():
    """Return run CSVs under DATA_DIR (recursive), newest first, with metadata."""
    files = []
    if DATA_DIR.is_dir():
        for p in DATA_DIR.rglob('*.csv'):
            try:
                stat = p.stat()
            except OSError:
                continue
            files.append((p, stat.st_mtime, stat.st_size))
    files.sort(key=lambda t: t[1], reverse=True)
    return files


@app.get("/api/data/list")
@limiter.limit(RATE_LIMIT)
async def data_list(request: Request):
    """List available data CSVs (newest first)."""
    return {"status": "success", "files": [
        {"name": p.relative_to(DATA_DIR).as_posix(),
         "size_bytes": size,
         "modified": mtime}
        for p, mtime, size in _list_data_files()
    ]}


@app.get("/api/data/latest")
@limiter.limit(RATE_LIMIT)
async def data_latest(request: Request):
    """Download the most recently modified data CSV."""
    files = _list_data_files()
    if not files:
        raise HTTPException(status_code=404, detail="no data files found")
    path = files[0][0]
    return FileResponse(str(path), media_type='text/csv', filename=path.name)


# ---------------------------------------------------------------------------
# Camera (Pi camera snapshot via rpicam-still)
# ---------------------------------------------------------------------------

@app.get("/api/camera/snapshot")
@limiter.limit(RATE_LIMIT)
async def camera_snapshot(request: Request,
                          rotation: Optional[int] = None,
                          hflip: Optional[bool] = None,
                          vflip: Optional[bool] = None,
                          zoom: Optional[float] = None):
    """Return a single JPEG frame from the Pi camera.

    Optional query params override the configured defaults:
    rotation (0|180), hflip (bool), vflip (bool), zoom (>=1.0, centered digital zoom).
    """
    config = _get_config()
    if not getattr(config, 'CAMERA_ENABLED', True) or not camera.available():
        raise HTTPException(status_code=503, detail="camera not available")
    rot = int(rotation) if rotation is not None else int(getattr(config, 'CAMERA_ROTATION', 0))
    if rot not in (0, 180):
        raise HTTPException(status_code=400, detail="rotation must be 0 or 180")
    try:
        jpeg = await run_in_threadpool(
            camera.capture_jpeg,
            width=getattr(config, 'CAMERA_WIDTH', 1280),
            height=getattr(config, 'CAMERA_HEIGHT', 720),
            rotation=rot,
            hflip=(bool(getattr(config, 'CAMERA_HFLIP', False)) if hflip is None else hflip),
            vflip=(bool(getattr(config, 'CAMERA_VFLIP', False)) if vflip is None else vflip),
            zoom=(float(getattr(config, 'CAMERA_ZOOM', 1.0)) if zoom is None else zoom),
            quality=getattr(config, 'CAMERA_QUALITY', 90),
        )
    except camera.CameraError as e:
        raise HTTPException(status_code=503, detail=f"camera: {e}")
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _read_signals():
    """Read the three monitor signals (bath temp, ambient, signed peltier current).

    Used by the history sampler thread; guarded by HARDWARE_LOCK in real mode.
    Returns a dict with keys temperature / ambient_temp / peltier_current (None if
    a component is unavailable or the read fails).
    """
    if simulation_mode:
        return {
            "temperature": round(36.5 + random.uniform(-0.5, 0.5), 2) if initialized_components.get('temp_sensor') else None,
            "ambient_temp": round(22.0 + random.uniform(-1.0, 1.0), 2) if initialized_components.get('ambient_temp') else None,
            "peltier_current": round(random.uniform(0.0, 0.05), 3) if initialized_components.get('peltier_current') else None,
            "od": _read_od(),
        }
    from bioreactor_v3.src.io import (
        get_temperature, read_ambient_temp, read_peltier_current, get_peltier_state,
    )

    def _rd(name, fn):
        if not initialized_components.get(name):
            return None
        try:
            v = fn()
        except Exception:
            return None
        if v is not None and isinstance(v, float) and math.isnan(v):
            return None
        return v

    with HARDWARE_LOCK:
        temp = _rd('temp_sensor', lambda: get_temperature(bioreactor, sensor_index=0))
        ambient = _rd('ambient_temp', lambda: read_ambient_temp(bioreactor))
        current = _rd('peltier_current', lambda: read_peltier_current(bioreactor))
        forward = True
        if initialized_components.get('peltier_driver'):
            ps = get_peltier_state(bioreactor)
            if ps is not None:
                _, forward = ps
    if current is not None and not forward:
        current = -current   # sign negative when heating, matching /api/state
    return {"temperature": temp, "ambient_temp": ambient, "peltier_current": current, "od": _read_od()}


def _read_od():
    """Latest IR-gated OD reading from the OD sampler ({channel: volts}, or None if
    no OD source / sampling disabled). The gated measurement (LED on -> read -> off)
    happens on the od_sampler thread, not here."""
    return od_sampler.latest()


def _get_config():
    """Lazy-load config for simulation mode sensor defaults."""
    from config import Config
    return Config()
