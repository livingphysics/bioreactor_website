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
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from auth import verify_token, limiter, RATE_LIMIT

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
            from config import Config
            config = Config()
            bioreactor = Bioreactor(config)
            initialized_components = dict(bioreactor._initialized)
            logger.info(f"Hardware initialized: {initialized_components}")
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

    yield

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


@app.get("/api/capabilities")
@limiter.limit(RATE_LIMIT)
async def capabilities(request: Request):
    """Discover available components and their endpoint patterns."""
    caps = {}
    actuators = ['led', 'peltier_driver', 'stirrer', 'ring_light', 'pumps', 'relays']
    sensors = ['temp_sensor', 'optical_density', 'eyespy_adc', 'co2_sensor', 'o2_sensor']

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
    if simulation_mode:
        sim_state['led_power'] = req.power
        return LEDState(status="success", power=req.power, active=req.power > 0)
    from bioreactor_v3.src.io import set_led
    set_led(bioreactor, req.power)
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
    if simulation_mode:
        sim_state['peltier_duty'] = req.duty_cycle
        sim_state['peltier_direction'] = req.direction
        return PeltierState(status="success", duty_cycle=req.duty_cycle, direction=req.direction, active=req.duty_cycle > 0)
    from bioreactor_v3.src.io import set_peltier_power
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
# Helper
# ---------------------------------------------------------------------------

def _get_config():
    """Lazy-load config for simulation mode sensor defaults."""
    from config import Config
    return Config()
