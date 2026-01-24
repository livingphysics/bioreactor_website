#!/usr/bin/env python3
"""
Quick test script to verify CO2 sensor is working

Run this before starting docker-compose to verify hardware initialization.
"""
import sys
from pathlib import Path

# Add bioreactor_v3 to path
BIOREACTOR_V3_PATH = Path(__file__).parent / 'bioreactor_v3' / 'src'
sys.path.insert(0, str(BIOREACTOR_V3_PATH))

# Import custom config
try:
    from config_hardware import Config
    print("✓ Using custom hardware configuration")
except ImportError:
    from config_default import Config
    print("⚠ Using default configuration (CO2 sensor may be disabled)")

from bioreactor import Bioreactor
from io import read_co2

def main():
    print("\n" + "="*60)
    print("CO2 Sensor Test")
    print("="*60 + "\n")

    # Show configuration
    print("Configuration:")
    print(f"  CO2_SENSOR_ENABLED: {Config.CO2_SENSOR_ENABLED}")
    print(f"  CO2_SENSOR_TYPE: {Config.CO2_SENSOR_TYPE}")
    print(f"  CO2_SENSOR_I2C_BUS: {Config.CO2_SENSOR_I2C_BUS}")
    print(f"  CO2_SENSOR_I2C_ADDRESS: {Config.CO2_SENSOR_I2C_ADDRESS or 'auto'}")
    print()

    if not Config.CO2_SENSOR_ENABLED:
        print("⚠ CO2 sensor is disabled in config!")
        print("  Edit config_hardware.py and set CO2_SENSOR_ENABLED = True")
        return 1

    # Initialize bioreactor
    print("Initializing bioreactor...")
    try:
        config = Config()
        bioreactor = Bioreactor(config)
        print("✓ Bioreactor initialized")
    except Exception as e:
        print(f"✗ Bioreactor initialization failed: {e}")
        return 1

    # Check if CO2 sensor initialized
    print()
    print("Component initialization status:")
    for component, status in bioreactor._initialized.items():
        symbol = "✓" if status else "✗"
        print(f"  {symbol} {component}: {status}")
    print()

    if not bioreactor.is_component_initialized('co2_sensor'):
        print("✗ CO2 sensor not initialized!")
        print("  Check I2C bus and sensor connection")
        print("  Try: i2cdetect -y 1")
        bioreactor.finish()
        return 1

    print("✓ CO2 sensor initialized successfully")
    print()

    # Test reading CO2
    print("Testing CO2 reading...")
    try:
        for i in range(3):
            co2_ppm = read_co2(bioreactor)
            if co2_ppm is None:
                print(f"  Attempt {i+1}: ✗ Failed to read CO2 sensor")
            else:
                print(f"  Attempt {i+1}: ✓ CO2 = {co2_ppm} ppm")

            if i < 2:
                import time
                time.sleep(1)
    except Exception as e:
        print(f"✗ Error reading CO2: {e}")
        bioreactor.finish()
        return 1

    # Cleanup
    print()
    print("Cleaning up...")
    bioreactor.finish()
    print("✓ Test complete!")
    print()

    return 0


if __name__ == "__main__":
    exit(main())
