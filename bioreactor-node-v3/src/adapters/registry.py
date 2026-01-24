"""Component adapter registry and discovery"""
from typing import Dict
from .peltier import PeltierAdapter
from .stirrer import StirrerAdapter
from .led import LEDAdapter
from .ring_light import RingLightAdapter
from .pumps import PumpAdapter
from .sensors import (
    TemperatureSensorAdapter,
    ODSensorAdapter,
    EyespyAdapter,
    CO2Adapter
)

# Map v3 component names to adapter classes
COMPONENT_ADAPTERS = {
    'peltier_driver': PeltierAdapter,
    'stirrer': StirrerAdapter,
    'led': LEDAdapter,
    'ring_light': RingLightAdapter,
    'pumps': PumpAdapter,
    'temp_sensor': TemperatureSensorAdapter,
    'optical_density': ODSensorAdapter,
    'eyespy_adc': EyespyAdapter,
    'co2_sensor': CO2Adapter,
}

def get_available_adapters(bioreactor):
    """Get adapter instances for all initialized components

    Args:
        bioreactor: Bioreactor instance from bioreactor_v3

    Returns:
        Dict mapping component names to adapter instances
    """
    if bioreactor is None:
        return {}

    adapters = {}
    for name, adapter_class in COMPONENT_ADAPTERS.items():
        if bioreactor.is_component_initialized(name):
            adapters[name] = adapter_class(bioreactor, name)
    return adapters
