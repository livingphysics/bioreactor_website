"""LED control adapter"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from .base import ComponentAdapter
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'bioreactor_v3', 'src'))

from io import set_led_power

class LEDControlRequest(BaseModel):
    """Request schema for LED control"""
    power: float = Field(ge=0, le=100, description="LED power (0-100%)")

class LEDStateResponse(BaseModel):
    """Response schema for LED state"""
    status: str
    power: float
    active: bool
    message: Optional[str] = None

class LEDAdapter(ComponentAdapter):
    """Adapter for main LED control"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "actuator",
            "control_type": "pwm",
            "parameters": ["power"],
            "power_range": [0, 100],
            "description": "Main illumination LED"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return LEDControlRequest

    def get_state_schema(self) -> type[BaseModel]:
        return LEDStateResponse

    async def control(self, request: LEDControlRequest) -> Dict[str, Any]:
        """Control LED power"""
        if not self.initialized:
            return {
                "status": "error",
                "power": 0.0,
                "active": False,
                "message": "LED not initialized"
            }

        try:
            set_led_power(self.bioreactor, request.power)
            return {
                "status": "success",
                "power": request.power,
                "active": request.power > 0,
                "message": f"LED set to {request.power}%"
            }
        except Exception as e:
            return {
                "status": "error",
                "power": 0.0,
                "active": False,
                "message": str(e)
            }

    async def read_state(self) -> Dict[str, Any]:
        """Read current LED state"""
        if not self.initialized:
            return {
                "status": "error",
                "power": 0.0,
                "active": False,
                "message": "LED not initialized"
            }

        try:
            led = getattr(self.bioreactor, 'led', None)
            if led:
                power = getattr(led, '_last_power', 0.0)
                return {
                    "status": "success",
                    "power": power,
                    "active": power > 0
                }
            return {
                "status": "error",
                "power": 0.0,
                "active": False,
                "message": "LED not found"
            }
        except Exception as e:
            return {
                "status": "error",
                "power": 0.0,
                "active": False,
                "message": str(e)
            }
