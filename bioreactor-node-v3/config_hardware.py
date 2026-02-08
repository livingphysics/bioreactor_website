"""
Custom hardware configuration for bioreactor-node-v3

This file allows you to override default configuration settings
for your specific hardware setup. Edit the values below to match
your hardware configuration.
"""
import sys
import os
from pathlib import Path
from typing import Optional, Union

# Add bioreactor_v3 to path
BIOREACTOR_V3_PATH = Path(__file__).parent / 'bioreactor_v3' / 'src'
sys.path.insert(0, str(BIOREACTOR_V3_PATH))

from config_default import Config as DefaultConfig


class HardwareConfig(DefaultConfig):
    """
    Custom hardware configuration

    Override default settings here for your specific hardware.
    Only include settings that differ from defaults.
    """

    # ========================================================================
    # Component Initialization Control
    # ========================================================================
    # CRITICAL: This dictionary controls which components are initialized
    # Set to True to initialize, False to skip
    INIT_COMPONENTS = {
        'i2c': True,
        'temp_sensor': True,  # Enabled
        'peltier_driver': True,  # Disabled - not connected
        'stirrer': True,  # Disabled - not connected
        'led': True,  # Disabled - not connected
        'ring_light': True,  # Disabled - not connected
        'optical_density': True,  # Disabled - not connected
        'eyespy_adc': False,  # Disabled - not connected
        'co2_sensor': False,  # ENABLED - Atlas Scientific CO2 sensor
        'pumps': False,  # Disabled - not connected
    }

    # Peltier Driver Configuration (Raspberry Pi 5 GPIO via lgpio)
    PELTIER_PWM_PIN: int = 21  # BCM pin for PWM output
    PELTIER_DIR_PIN: int = 20  # BCM pin for direction control
    PELTIER_PWM_FREQ: int = 1000  # PWM frequency in Hz

    # Stirrer Configuration (PWM only)
    STIRRER_PWM_PIN: int = 12  # BCM pin for stirrer PWM output
    STIRRER_PWM_FREQ: int = 1000  # PWM frequency in Hz
    STIRRER_DEFAULT_DUTY: float = 30.0  # Default duty cycle (0-100)

    # LED Configuration (PWM control)
    LED_PWM_PIN: int = 25  # BCM pin for LED PWM output
    LED_PWM_FREQ: int = 500  # PWM frequency in Hz

    # Ring Light Configuration (Neopixel, using pi5neo)
    RING_LIGHT_SPI_DEVICE: str = '/dev/spidev0.0'  # SPI device path
    RING_LIGHT_COUNT: int = 32  # Number of LEDs in the ring
    RING_LIGHT_SPI_SPEED: int = 800  # SPI speed in kHz

    # Optical Density (OD) Configuration (ADS1115 ADC)
    OD_ADC_CHANNELS: dict[str, str] = {
        '135': 'A0',
        'Ref': 'A1',
        '90': 'A2',
    }  # Dictionary mapping channel names to ADS1115 pins (A0-A3)
    
    # Eyespy ADC Configuration (ADS1114, based on pioreactor pattern)
    # Supports multiple eyespy boards, each at a different I2C address
    # Each eyespy board is a single-channel ADS1114 ADC
    EYESPY_ADC: dict = {
        'eyespy1': {
            'i2c_address': 0x49,  # I2C address (default for eyespy/pd2)
            'i2c_bus': 1,  # I2C bus number (typically 1 for /dev/i2c-1)
            'gain': 1.0,  # PGA gain: 2/3, 1.0, 2.0, 4.0, 8.0, 16.0 (default: 1.0 = ±4.096 V)
        },
        # Add more eyespy boards as needed:
        'eyespy2': {
            'i2c_address': 0x4a,  # Different I2C address
            'i2c_bus': 1,
            'gain': 1.0,
        },
    }
    
    # CO2 Sensor Configuration
    # CO2_SENSOR_TYPE options:
    #   - 'sensair' or'sensair_k33' (default): Senseair K33 sensor over I2C (default address: 0x68)
    #   - 'atlas' or 'atlas_i2c': Atlas Scientific CO2 sensor over I2C using atlas_i2c library (default address: 0x69)
    # Enable/disable via INIT_COMPONENTS['co2_sensor']
    CO2_SENSOR_TYPE: str = 'atlas_i2c'
    CO2_SENSOR_I2C_ADDRESS: Optional[int] = None  # I2C address for CO2 sensor (None = use type-specific default: 0x68 for sensair_k33, 0x69 for atlas)
    CO2_SENSOR_I2C_BUS: int = 1  # I2C bus number (typically 1 for /dev/i2c-1)
    
    # O2 Sensor Configuration (Atlas Scientific)
    # Enable/disable via INIT_COMPONENTS['o2_sensor']
    O2_SENSOR_I2C_ADDRESS: Optional[int] = None  # I2C address for O2 sensor (None = use default: 0x6C)
    O2_SENSOR_I2C_BUS: int = 1  # I2C bus number (typically 1 for /dev/i2c-1)
    
    # Pump Configuration (ticUSB protocol)
    # Default configuration: 2 pumps (inflow and outflow)
    # Add more pumps by extending the PUMPS dictionary
    # Each pump requires a serial number (from TicUSB device)
    # Direction: 'forward' or 'reverse' - determines velocity sign in change_pump
    # steps_per_ml: Conversion factor for this specific pump (calibrate per pump)
    PUMPS: dict[str, dict[str, Union[str, int, float]]] = {
        'inflow': {
            'serial': '00473498',  # Replace with your pump's serial number
            'step_mode': 3,  # Step mode (0-3, typically 3 for microstepping)
            'current_limit': 32,  # Current limit in units (check TicUSB docs)
            'direction': 'forward',  # Direction: 'forward' or 'reverse'
            'steps_per_ml': 10000000.0,  # Steps per ml conversion factor (calibrate for this pump)
        },
        'outflow': {
            'serial': '00473497',  # Replace with your pump's serial number
            'step_mode': 3,
            'current_limit': 32,
            'direction': 'forward',  # Direction: 'forward' or 'reverse'
            'steps_per_ml': 10000000.0,  # Steps per ml conversion factor (calibrate for this pump)
        },
        # Add more pumps as needed:
        # 'pump_3': {
        #     'serial': '00473504',
        #     'step_mode': 3,
        #     'current_limit': 32,
        #     'direction': 'forward',
        #     'steps_per_ml': 10000000.0,
        # },
    }

# Create config instance to be imported
Config = HardwareConfig
