"""
Custom hardware configuration for bioreactor-node-v3

This file allows you to override default configuration settings
for your specific hardware setup. Edit the values below to match
your hardware configuration.
"""
import sys
import os
from pathlib import Path

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
        'i2c': False,
        'temp_sensor': False,  # Disabled - not connected
        'peltier_driver': False,  # Disabled - not connected
        'stirrer': False,  # Disabled - not connected
        'led': False,  # Disabled - not connected
        'ring_light': False,  # Disabled - not connected
        'optical_density': False,  # Disabled - not connected
        'eyespy_adc': False,  # Disabled - not connected
        'co2_sensor': True,  # ENABLED - Atlas Scientific CO2 sensor
        'pumps': False,  # Disabled - not connected
    }

    # ========================================================================
    # CO2 Sensor Configuration
    # ========================================================================
    # Enable CO2 sensor
    CO2_SENSOR_ENABLED = True

    # CO2 sensor type: 'sensair_k33', 'sensair', 'atlas', or 'atlas_i2c'
    CO2_SENSOR_TYPE = 'atlas'  # Atlas Scientific CO2 sensor detected at 0x69

    # I2C bus number (typically 1 for /dev/i2c-1)
    CO2_SENSOR_I2C_BUS = 1

    # I2C address (None uses type-specific default: 0x68 for sensair, 0x69 for atlas)
    CO2_SENSOR_I2C_ADDRESS = None  # Will use 0x68 for sensair_k33

    # ========================================================================
    # Logging
    # ========================================================================
    LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
    LOG_FILE = "bioreactor.log"  # Local directory for testing
    DATA_OUT_FILE = "bioreactor_data.csv"  # Local directory for testing


# Create config instance to be imported
Config = HardwareConfig
