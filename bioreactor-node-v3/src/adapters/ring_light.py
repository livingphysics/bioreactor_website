"""NeoPixel ring light adapter"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from .base import ComponentAdapter
from bioreactor_v3.src.io import set_ring_light

class RingLightControlRequest(BaseModel):
    """Request schema for ring light control"""
    red: int = Field(ge=0, le=255, description="Red value (0-255)")
    green: int = Field(ge=0, le=255, description="Green value (0-255)")
    blue: int = Field(ge=0, le=255, description="Blue value (0-255)")
    pixel_index: Optional[int] = Field(None, ge=0, le=7, description="Specific pixel (0-7) or None for all")

class RingLightStateResponse(BaseModel):
    """Response schema for ring light state"""
    status: str
    red: int
    green: int
    blue: int
    active: bool
    message: Optional[str] = None

class RingLightAdapter(ComponentAdapter):
    """Adapter for NeoPixel ring light control"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "actuator",
            "control_type": "rgb_addressable",
            "parameters": ["red", "green", "blue", "pixel_index"],
            "color_range": [0, 255],
            "pixel_count": 8,
            "description": "8-pixel NeoPixel RGB ring light"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return RingLightControlRequest

    def get_state_schema(self) -> type[BaseModel]:
        return RingLightStateResponse

    async def control(self, request: RingLightControlRequest) -> Dict[str, Any]:
        """Control ring light color"""
        if not self.initialized:
            return {
                "status": "error",
                "active": False,
                "message": "Ring light not initialized"
            }

        try:
            color = (request.red, request.green, request.blue)
            if request.pixel_index is not None:
                set_ring_light(self.bioreactor, color, pixel=request.pixel_index)
                msg = f"Pixel {request.pixel_index} set to RGB({request.red},{request.green},{request.blue})"
            else:
                set_ring_light(self.bioreactor, color)
                msg = f"All pixels set to RGB({request.red},{request.green},{request.blue})"

            # Store last color for state tracking
            ring_light = getattr(self.bioreactor, 'ring_light', None)
            if ring_light:
                ring_light._last_red = request.red
                ring_light._last_green = request.green
                ring_light._last_blue = request.blue

            return {
                "status": "success",
                "active": any([request.red, request.green, request.blue]),
                "message": msg
            }
        except Exception as e:
            return {
                "status": "error",
                "active": False,
                "message": str(e)
            }

    async def read_state(self) -> Dict[str, Any]:
        """Read current ring light state"""
        if not self.initialized:
            return {
                "status": "error",
                "red": 0,
                "green": 0,
                "blue": 0,
                "active": False,
                "message": "Ring light not initialized"
            }

        try:
            ring_light = getattr(self.bioreactor, 'ring_light', None)
            if ring_light:
                red = getattr(ring_light, '_last_red', 0)
                green = getattr(ring_light, '_last_green', 0)
                blue = getattr(ring_light, '_last_blue', 0)
                return {
                    "status": "success",
                    "red": red,
                    "green": green,
                    "blue": blue,
                    "active": any([red, green, blue]),
                    "message": f"Ring light RGB({red},{green},{blue})"
                }
            return {
                "status": "error",
                "red": 0,
                "green": 0,
                "blue": 0,
                "active": False,
                "message": "Ring light not found"
            }
        except Exception as e:
            return {
                "status": "error",
                "red": 0,
                "green": 0,
                "blue": 0,
                "active": False,
                "message": str(e)
            }
