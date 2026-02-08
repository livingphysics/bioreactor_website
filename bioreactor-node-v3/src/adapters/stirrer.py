"""Stirrer motor control adapter"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from .base import ComponentAdapter
from bioreactor_v3.src.io import set_stirrer_speed, stop_stirrer

class StirrerControlRequest(BaseModel):
    """Request schema for stirrer control"""
    duty_cycle: float = Field(ge=0, le=100, description="PWM duty cycle (0-100%)")

class StirrerStateResponse(BaseModel):
    """Response schema for stirrer state"""
    status: str
    duty_cycle: float
    active: bool
    message: Optional[str] = None

class StirrerAdapter(ComponentAdapter):
    """Adapter for stirrer motor control"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "actuator",
            "control_type": "pwm",
            "parameters": ["duty_cycle"],
            "duty_range": [0, 100],
            "description": "Magnetic stirrer motor via PWM"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return StirrerControlRequest

    def get_state_schema(self) -> type[BaseModel]:
        return StirrerStateResponse

    async def control(self, request: StirrerControlRequest) -> Dict[str, Any]:
        """Control stirrer speed"""
        if not self.initialized:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "active": False,
                "message": "Stirrer not initialized"
            }

        try:
            set_stirrer_speed(self.bioreactor, request.duty_cycle)
            return {
                "status": "success",
                "duty_cycle": request.duty_cycle,
                "active": request.duty_cycle > 0,
                "message": f"Stirrer set to {request.duty_cycle}%"
            }
        except Exception as e:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "active": False,
                "message": str(e)
            }

    async def read_state(self) -> Dict[str, Any]:
        """Read current stirrer state"""
        if not self.initialized:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "active": False,
                "message": "Stirrer not initialized"
            }

        try:
            stirrer = getattr(self.bioreactor, 'stirrer', None)
            if stirrer:
                duty = getattr(stirrer, '_last_duty', 0.0)
                return {
                    "status": "success",
                    "duty_cycle": duty,
                    "active": duty > 0
                }
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "active": False,
                "message": "Stirrer not found"
            }
        except Exception as e:
            return {
                "status": "error",
                "duty_cycle": 0.0,
                "active": False,
                "message": str(e)
            }
