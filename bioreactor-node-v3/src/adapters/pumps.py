"""Pump control adapter"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from .base import ComponentAdapter
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'bioreactor_v3', 'src'))

from io import set_pump_velocity, stop_pump

class PumpControlRequest(BaseModel):
    """Request schema for pump control"""
    pump_name: str = Field(description="Pump identifier (e.g., 'pump1', 'pump2')")
    velocity: float = Field(description="Velocity in mL/s (positive=forward, negative=reverse)")

class PumpStateResponse(BaseModel):
    """Response schema for pump state"""
    status: str
    pump_name: str
    velocity: float
    active: bool
    message: Optional[str] = None

class PumpAdapter(ComponentAdapter):
    """Adapter for stepper pump control"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "actuator",
            "control_type": "stepper",
            "parameters": ["pump_name", "velocity"],
            "available_pumps": ["pump1", "pump2", "pump3", "pump4"],
            "velocity_units": "mL/s",
            "description": "TicUSB stepper pumps for fluid transfer"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return PumpControlRequest

    def get_state_schema(self) -> type[BaseModel]:
        return PumpStateResponse

    async def control(self, request: PumpControlRequest) -> Dict[str, Any]:
        """Control pump velocity"""
        if not self.initialized:
            return {
                "status": "error",
                "pump_name": request.pump_name,
                "velocity": 0.0,
                "active": False,
                "message": "Pumps not initialized"
            }

        try:
            set_pump_velocity(self.bioreactor, request.pump_name, request.velocity)
            return {
                "status": "success",
                "pump_name": request.pump_name,
                "velocity": request.velocity,
                "active": request.velocity != 0,
                "message": f"{request.pump_name} set to {request.velocity} mL/s"
            }
        except Exception as e:
            return {
                "status": "error",
                "pump_name": request.pump_name,
                "velocity": 0.0,
                "active": False,
                "message": str(e)
            }

    async def read_state(self) -> Dict[str, Any]:
        """Read current pump state"""
        if not self.initialized:
            return {
                "status": "error",
                "pump_name": "unknown",
                "velocity": 0.0,
                "active": False,
                "message": "Pumps not initialized"
            }

        try:
            pumps = getattr(self.bioreactor, 'pumps', None)
            if pumps:
                return {
                    "status": "success",
                    "pump_name": "all",
                    "velocity": 0.0,
                    "active": True,
                    "message": "Pumps operational"
                }
            return {
                "status": "error",
                "pump_name": "unknown",
                "velocity": 0.0,
                "active": False,
                "message": "Pumps not found"
            }
        except Exception as e:
            return {
                "status": "error",
                "pump_name": "unknown",
                "velocity": 0.0,
                "active": False,
                "message": str(e)
            }
