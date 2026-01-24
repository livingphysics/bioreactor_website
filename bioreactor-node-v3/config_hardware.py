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
    # CO2 Sensor Configuration
    # ========================================================================
    # Enable CO2 sensor
    CO2_SENSOR_ENABLED = True

    # CO2 sensor type: 'sensair_k33', 'sensair', 'atlas', or 'atlas_i2c'
    CO2_SENSOR_TYPE = 'sensair_k33'

    # I2C bus number (typically 1 for /dev/i2c-1)
    CO2_SENSOR_I2C_BUS = 1

    # I2C address (None uses type-specific default: 0x68 for sensair, 0x69 for atlas)
    CO2_SENSOR_I2C_ADDRESS = None  # Will use 0x68 for sensair_k33

    # ========================================================================
    # Disable other components (since only CO2 sensor is connected)
    # ========================================================================
    # Temperature sensors
    TEMP_SENSOR_ENABLED = False

    # Optical density
    OPTICAL_DENSITY_ENABLED = False

    # Peltier
    PELTIER_ENABLED = False

    # Stirrer
    STIRRER_ENABLED = False

    # LED
    LED_ENABLED = False

    # Ring light
    RING_LIGHT_ENABLED = False

    # Pumps
    PUMPS_ENABLED = False

    # Eyespy ADC
    EYESPY_ADC_ENABLED = False

    # ========================================================================
    # Logging
    # ========================================================================
    LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
    LOG_FILE = "/app/logs/bioreactor.log"
    DATA_OUT_FILE = "/app/data/bioreactor_data.csv"


# Create config instance to be imported
Config = HardwareConfig
