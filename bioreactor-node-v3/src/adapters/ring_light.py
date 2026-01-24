"""NeoPixel ring light adapter"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from .base import ComponentAdapter
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'bioreactor_v3', 'src'))

from io import set_ring_light_color, set_ring_light_pixel

class RingLightControlRequest(BaseModel):
    """Request schema for ring light control"""
    red: int = Field(ge=0, le=255, description="Red value (0-255)")
    green: int = Field(ge=0, le=255, description="Green value (0-255)")
    blue: int = Field(ge=0, le=255, description="Blue value (0-255)")
    pixel_index: Optional[int] = Field(None, ge=0, le=7, description="Specific pixel (0-7) or None for all")

class RingLightStateResponse(BaseModel):
    """Response schema for ring light state"""
    status: str
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
            if request.pixel_index is not None:
                set_ring_light_pixel(
                    self.bioreactor,
                    request.pixel_index,
                    request.red,
                    request.green,
                    request.blue
                )
                msg = f"Pixel {request.pixel_index} set to RGB({request.red},{request.green},{request.blue})"
            else:
                set_ring_light_color(
                    self.bioreactor,
                    request.red,
                    request.green,
                    request.blue
                )
                msg = f"All pixels set to RGB({request.red},{request.green},{request.blue})"

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
                "active": False,
                "message": "Ring light not initialized"
            }

        try:
            ring_light = getattr(self.bioreactor, 'ring_light', None)
            if ring_light:
                return {
                    "status": "success",
                    "active": True,
                    "message": "Ring light operational"
                }
            return {
                "status": "error",
                "active": False,
                "message": "Ring light not found"
            }
        except Exception as e:
            return {
                "status": "error",
                "active": False,
                "message": str(e)
            }
