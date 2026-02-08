"""Legacy v2-compatible endpoints for existing hub integration"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'bioreactor_v3', 'src'))

from src.adapters.registry import get_available_adapters

def create_legacy_router(bioreactor) -> APIRouter:
    """v2-compatible endpoints for existing hub integration

    Args:
        bioreactor: Bioreactor instance from bioreactor_v3

    Returns:
        FastAPI router with v2-compatible endpoints
    """
    router = APIRouter(prefix="/api", tags=["legacy_v2"])
    adapters = get_available_adapters(bioreactor)

    # LED control
    class LEDRequest(BaseModel):
        state: bool

    @router.post("/led")
    async def control_led_v2(request: LEDRequest):
        """Legacy LED control (v2 compatible)"""
        if 'led' not in adapters:
            raise HTTPException(status_code=503, detail="LED not available")

        from src.adapters.led import LEDControlRequest
        v3_req = LEDControlRequest(power=100.0 if request.state else 0.0)
        return await adapters['led'].control(v3_req)

    # Peltier control
    class PeltierRequest(BaseModel):
        power: int
        forward: bool

    @router.post("/peltier")
    async def control_peltier_v2(request: PeltierRequest):
        """Legacy peltier control (v2 compatible)"""
        if 'peltier_driver' not in adapters:
            raise HTTPException(status_code=503, detail="Peltier not available")

        from src.adapters.peltier import PeltierControlRequest
        direction = "forward" if request.forward else "reverse"
        v3_req = PeltierControlRequest(duty_cycle=float(request.power), direction=direction)
        return await adapters['peltier_driver'].control(v3_req)

    # Ring light control
    class RingLightRequest(BaseModel):
        red: int
        green: int
        blue: int
        pixel_index: Optional[int] = None

    @router.post("/ring-light")
    async def control_ring_light_v2(request: RingLightRequest):
        """Legacy ring light control (v2 compatible)"""
        if 'ring_light' not in adapters:
            raise HTTPException(status_code=503, detail="Ring light not available")

        from src.adapters.ring_light import RingLightControlRequest
        v3_req = RingLightControlRequest(
            red=request.red,
            green=request.green,
            blue=request.blue,
            pixel_index=request.pixel_index
        )
        return await adapters['ring_light'].control(v3_req)

    # Pump control
    class PumpRequest(BaseModel):
        name: str
        velocity: float

    @router.post("/pump")
    async def control_pump_v2(request: PumpRequest):
        """Legacy pump control (v2 compatible)"""
        if 'pumps' not in adapters:
            raise HTTPException(status_code=503, detail="Pumps not available")

        from src.adapters.pumps import PumpControlRequest
        v3_req = PumpControlRequest(pump_name=request.name, velocity=request.velocity)
        return await adapters['pumps'].control(v3_req)

    # Stirrer control
    class StirrerRequest(BaseModel):
        duty_cycle: float

    @router.post("/stirrer")
    async def control_stirrer_v2(request: StirrerRequest):
        """Legacy stirrer control (v2 compatible)"""
        if 'stirrer' not in adapters:
            raise HTTPException(status_code=503, detail="Stirrer not available")

        from src.adapters.stirrer import StirrerControlRequest
        v3_req = StirrerControlRequest(duty_cycle=request.duty_cycle)
        return await adapters['stirrer'].control(v3_req)

    # Sensor endpoints
    @router.get("/sensors/all")
    async def get_all_sensors_v2():
        """Legacy get all sensors (v2 compatible)"""
        result = {"status": "success"}

        if 'temp_sensor' in adapters:
            temp_data = await adapters['temp_sensor'].read_state()
            result['vial_temperatures'] = temp_data.get('temperatures', [])

        if 'optical_density' in adapters:
            od_data = await adapters['optical_density'].read_state()
            result['photodiodes'] = od_data.get('voltages', [])

        if 'co2_sensor' in adapters:
            co2_data = await adapters['co2_sensor'].read_state()
            result['co2_ppm'] = co2_data.get('co2_ppm', 0.0)

        return result

    @router.get("/sensors/photodiodes")
    async def get_photodiodes_v2():
        """Legacy get photodiodes (v2 compatible)"""
        if 'optical_density' not in adapters:
            raise HTTPException(status_code=503, detail="Optical density sensors not available")

        od_data = await adapters['optical_density'].read_state()
        return {
            "status": "success",
            "readings": od_data.get('voltages', [])
        }

    @router.get("/sensors/temperature")
    async def get_temperature_v2():
        """Legacy get temperatures (v2 compatible)"""
        if 'temp_sensor' not in adapters:
            raise HTTPException(status_code=503, detail="Temperature sensors not available")

        temp_data = await adapters['temp_sensor'].read_state()
        return {
            "status": "success",
            "temperatures": temp_data.get('temperatures', [])
        }

    @router.get("/status")
    async def get_status_v2():
        """Legacy status endpoint (v2 compatible)"""
        return {
            "status": "operational",
            "hardware_available": bioreactor is not None,
            "initialized_components": bioreactor._initialized if bioreactor else {},
            "api_version": "v3_with_v2_compat"
        }

    return router
