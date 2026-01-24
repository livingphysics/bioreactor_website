"""Peltier temperature control adapter"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from .base import ComponentAdapter
import sys
import os

# Add bioreactor_v3 to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'bioreactor_v3', 'src'))

from io import set_peltier_power, stop_peltier

class PeltierControlRequest(BaseModel):
    """Request schema for peltier control"""
    duty_cycle: float = Field(ge=0, le=100, description="PWM duty cycle (0-100%)")
    direction: str = Field(pattern="^(heat|cool|forward|reverse)$", description="Heating or cooling direction")

class PeltierStateResponse(BaseModel):
    """Response schema for peltier state"""
    status: str
    duty_cycle: float
    direction: str
    active: bool
    message: Optional[str] = None

class PeltierAdapter(ComponentAdapter):
    """Adapter for Peltier temperature control"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "actuator",
            "control_type": "pwm_directional",
            "parameters": ["duty_cycle", "direction"],
            "duty_range": [0, 100],
            "directions": ["heat", "cool", "forward", "reverse"],
            "description": "Thermoelectric temperature control via PWM"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return PeltierControlRequest

    def get_state_schema(self) -> type[BaseModel]:
        return PeltierStateResponse

    async def control(self, request: PeltierControlRequest) -> Dict[str, Any]:
        """Control peltier power and direction"""
        if not self.initialized:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "direction": "forward",
                "active": False,
                "message": "Peltier not initialized"
            }

        try:
            set_peltier_power(self.bioreactor, request.duty_cycle, request.direction)
            return {
                "status": "success",
                "duty_cycle": request.duty_cycle,
                "direction": request.direction,
                "active": request.duty_cycle > 0,
                "message": f"Peltier set to {request.duty_cycle}% {request.direction}"
            }
        except Exception as e:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "direction": "forward",
                "active": False,
                "message": str(e)
            }

    async def read_state(self) -> Dict[str, Any]:
        """Read current peltier state"""
        if not self.initialized:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "direction": "forward",
                "active": False,
                "message": "Peltier not initialized"
            }

        try:
            driver = getattr(self.bioreactor, 'peltier_driver', None)
            if driver:
                return {
                    "status": "success",
                    "duty_cycle": getattr(driver, '_last_duty', 0.0),
                    "direction": "forward" if getattr(driver, '_last_forward', True) else "reverse",
                    "active": getattr(driver, '_last_duty', 0.0) > 0
                }
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "direction": "forward",
                "active": False,
                "message": "Peltier driver not found"
            }
        except Exception as e:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "direction": "forward",
                "active": False,
                "message": str(e)
            }
