"""
Hardware configuration for the bioreactor API.

Edit INIT_COMPONENTS to enable/disable hardware components.
Only enabled components get API endpoints.
"""
import sys
from pathlib import Path
from typing import Optional, Union

# Add bioreactor_v3 to path
BIOREACTOR_V3_PATH = Path(__file__).parent / 'bioreactor_v3' / 'src'
sys.path.insert(0, str(BIOREACTOR_V3_PATH))

from config_default import Config as DefaultConfig


class Config(DefaultConfig):
    """
    Hardware configuration.

    Override default settings here for your specific hardware.
    Only include settings that differ from defaults.
    """

    # ========================================================================
    # Component Initialization Control
    # ========================================================================
    # Set to True to initialize, False to skip.
    # Only initialized components get API endpoints.
    INIT_COMPONENTS = {
        'i2c': True,
        'temp_sensor': True,
        'peltier_driver': True,
        'stirrer': True,
        'led': True,
        'ring_light': True,
        'optical_density': True,
        'eyespy_adc': False,
        'co2_sensor': False,
        'o2_sensor': False,
        'pumps': False,
        'relays': False,
    }

    # Peltier Driver (Raspberry Pi 5 GPIO via lgpio)
    PELTIER_PWM_PIN: int = 21
    PELTIER_DIR_PIN: int = 20
    PELTIER_PWM_FREQ: int = 1000

    # Stirrer (PWM only)
    STIRRER_PWM_PIN: int = 12
    STIRRER_PWM_FREQ: int = 1000
    STIRRER_DEFAULT_DUTY: float = 30.0

    # LED (PWM control)
    LED_PWM_PIN: int = 25
    LED_PWM_FREQ: int = 500

    # Ring Light (Neopixel via pi5neo SPI)
    RING_LIGHT_SPI_DEVICE: str = '/dev/spidev0.0'
    RING_LIGHT_COUNT: int = 32
    RING_LIGHT_SPI_SPEED: int = 800

    # Optical Density (ADS1115 ADC)
    OD_ADC_CHANNELS: dict[str, str] = {
        '135': 'A0',
        'Ref': 'A1',
        '90': 'A2',
    }

    # Eyespy ADC (ADS1114, single-channel per board)
    EYESPY_ADC: dict = {
        'eyespy1': {
            'i2c_address': 0x49,
            'i2c_bus': 1,
            'gain': 1.0,
        },
        'eyespy2': {
            'i2c_address': 0x4a,
            'i2c_bus': 1,
            'gain': 1.0,
        },
    }

    # CO2 Sensor
    CO2_SENSOR_TYPE: str = 'atlas_i2c'
    CO2_SENSOR_I2C_ADDRESS: Optional[int] = None
    CO2_SENSOR_I2C_BUS: int = 1

    # O2 Sensor (Atlas Scientific)
    O2_SENSOR_I2C_ADDRESS: Optional[int] = None
    O2_SENSOR_I2C_BUS: int = 1

    # Pumps (ticUSB protocol)
    PUMPS: dict[str, dict[str, Union[str, int, float]]] = {
        'inflow': {
            'serial': '00473498',
            'step_mode': 3,
            'current_limit': 32,
            'direction': 'forward',
            'steps_per_ml': 10000000.0,
        },
        'outflow': {
            'serial': '00473497',
            'step_mode': 3,
            'current_limit': 32,
            'direction': 'forward',
            'steps_per_ml': 10000000.0,
        },
    }
