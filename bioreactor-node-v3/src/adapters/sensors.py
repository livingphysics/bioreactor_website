"""Sensor adapters for temperature, OD, eyespy, and CO2"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from .base import ComponentAdapter
from bioreactor_v3.src.io import get_temperature, read_voltage, read_eyespy_voltage, read_co2

# Temperature Sensor Adapter
class TemperatureStateResponse(BaseModel):
    """Response schema for temperature sensors"""
    status: str
    temperatures: List[float]
    unit: str = "celsius"
    message: Optional[str] = None

class TemperatureSensorAdapter(ComponentAdapter):
    """Adapter for DS18B20 temperature sensors"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "sensor",
            "sensor_type": "temperature",
            "count": 8,
            "unit": "celsius",
            "description": "DS18B20 temperature sensors (one per vial)"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return None  # Sensor only, no control

    def get_state_schema(self) -> type[BaseModel]:
        return TemperatureStateResponse

    async def control(self, request: BaseModel) -> Dict[str, Any]:
        """Not applicable for sensors"""
        return {"status": "error", "message": "Sensors do not support control operations"}

    async def read_state(self) -> Dict[str, Any]:
        """Read all temperature sensors"""
        if not self.initialized:
            return {
                "status": "error",
                "temperatures": [],
                "message": "Temperature sensors not initialized"
            }

        try:
            # Read all 8 temperature sensors
            temps = []
            for i in range(8):
                temp = get_temperature(self.bioreactor, sensor_index=i)
                temps.append(temp if temp is not None else float('nan'))
            return {
                "status": "success",
                "temperatures": temps,
                "unit": "celsius"
            }
        except Exception as e:
            return {
                "status": "error",
                "temperatures": [],
                "message": str(e)
            }


# Optical Density Sensor Adapter
class ODStateResponse(BaseModel):
    """Response schema for optical density sensors"""
    status: str
    voltages: List[float]
    unit: str = "volts"
    message: Optional[str] = None

class ODSensorAdapter(ComponentAdapter):
    """Adapter for ADS7830 photodiode array (optical density)"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "sensor",
            "sensor_type": "optical_density",
            "count": 8,
            "unit": "volts",
            "description": "Photodiode array for turbidity measurement"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return None

    def get_state_schema(self) -> type[BaseModel]:
        return ODStateResponse

    async def control(self, request: BaseModel) -> Dict[str, Any]:
        return {"status": "error", "message": "Sensors do not support control operations"}

    async def read_state(self) -> Dict[str, Any]:
        """Read photodiode voltages"""
        if not self.initialized:
            return {
                "status": "error",
                "voltages": [],
                "message": "Optical density sensors not initialized"
            }

        try:
            # Read all OD channels - assumes channels are named in config
            voltages = []
            # Try to read from configured channels
            if hasattr(self.bioreactor, 'cfg') and hasattr(self.bioreactor.cfg, 'OD_ADC_CHANNELS'):
                for channel_name in self.bioreactor.cfg.OD_ADC_CHANNELS.keys():
                    voltage = read_voltage(self.bioreactor, channel_name)
                    voltages.append(voltage if voltage is not None else float('nan'))
            return {
                "status": "success",
                "voltages": voltages,
                "unit": "volts"
            }
        except Exception as e:
            return {
                "status": "error",
                "voltages": [],
                "message": str(e)
            }


# Eyespy ADC Adapter
class EyespyStateResponse(BaseModel):
    """Response schema for eyespy ADC"""
    status: str
    voltages: List[float]
    unit: str = "volts"
    message: Optional[str] = None

class EyespyAdapter(ComponentAdapter):
    """Adapter for ADS1115 high-precision ADC (eyespy)"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "sensor",
            "sensor_type": "adc",
            "channels": 4,
            "resolution": "16-bit",
            "unit": "volts",
            "description": "ADS1115 high-precision ADC for custom sensors"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return None

    def get_state_schema(self) -> type[BaseModel]:
        return EyespyStateResponse

    async def control(self, request: BaseModel) -> Dict[str, Any]:
        return {"status": "error", "message": "Sensors do not support control operations"}

    async def read_state(self) -> Dict[str, Any]:
        """Read ADC channels"""
        if not self.initialized:
            return {
                "status": "error",
                "voltages": [],
                "message": "Eyespy ADC not initialized"
            }

        try:
            # Read all eyespy boards
            voltages = []
            if hasattr(self.bioreactor, 'cfg') and hasattr(self.bioreactor.cfg, 'EYESPY_ADC'):
                for board_name in self.bioreactor.cfg.EYESPY_ADC.keys():
                    voltage = read_eyespy_voltage(self.bioreactor, board_name)
                    voltages.append(voltage if voltage is not None else float('nan'))
            return {
                "status": "success",
                "voltages": voltages,
                "unit": "volts"
            }
        except Exception as e:
            return {
                "status": "error",
                "voltages": [],
                "message": str(e)
            }


# CO2 Sensor Adapter
class CO2StateResponse(BaseModel):
    """Response schema for CO2 sensor"""
    status: str
    co2_ppm: float
    unit: str = "ppm"
    message: Optional[str] = None

class CO2Adapter(ComponentAdapter):
    """Adapter for CO2 sensor"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "type": "sensor",
            "sensor_type": "co2",
            "unit": "ppm",
            "description": "CO2 concentration sensor"
        }

    def get_control_schema(self) -> Optional[type[BaseModel]]:
        return None

    def get_state_schema(self) -> type[BaseModel]:
        return CO2StateResponse

    async def control(self, request: BaseModel) -> Dict[str, Any]:
        return {"status": "error", "message": "Sensors do not support control operations"}

    async def read_state(self) -> Dict[str, Any]:
        """Read CO2 concentration"""
        if not self.initialized:
            return {
                "status": "error",
                "co2_ppm": 0.0,
                "message": "CO2 sensor not initialized"
            }

        try:
            co2_ppm = read_co2(self.bioreactor)
            if co2_ppm is None:
                return {
                    "status": "error",
                    "co2_ppm": 0.0,
                    "message": "Failed to read CO2 sensor"
                }
            return {
                "status": "success",
                "co2_ppm": float(co2_ppm),
                "unit": "ppm"
            }
        except Exception as e:
            return {
                "status": "error",
                "co2_ppm": 0.0,
                "message": str(e)
            }
