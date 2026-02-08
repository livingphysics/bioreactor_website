#!/bin/bash
# Quick test script for CO2 sensor on current hardware

set -e

echo "============================================================"
echo "Bioreactor Node v3 - Quick Test (CO2 Sensor Only)"
echo "============================================================"
echo

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "⚠ Warning: Not running on Raspberry Pi"
    echo "  This test is designed for Raspberry Pi hardware"
    echo
fi

# Check for I2C
if [ ! -e /dev/i2c-1 ]; then
    echo "✗ /dev/i2c-1 not found"
    echo "  Enable I2C in raspi-config"
    exit 1
fi
echo "✓ I2C device found: /dev/i2c-1"

# Check for i2c-tools
if ! command -v i2cdetect &> /dev/null; then
    echo "⚠ i2c-tools not installed"
    echo "  Installing i2c-tools..."
    sudo apt-get update -qq
    sudo apt-get install -y i2c-tools
fi
echo "✓ i2c-tools installed"

# Scan I2C bus
echo
echo "Scanning I2C bus..."
i2cdetect -y 1
echo

# Check for CO2 sensor at common addresses
CO2_FOUND=false
if i2cdetect -y 1 | grep -q " 68 "; then
    echo "✓ Device found at 0x68 (likely Senseair K33)"
    CO2_FOUND=true
fi
if i2cdetect -y 1 | grep -q " 69 "; then
    echo "✓ Device found at 0x69 (likely Atlas Scientific)"
    CO2_FOUND=true
fi

if [ "$CO2_FOUND" = false ]; then
    echo "⚠ No CO2 sensor found at 0x68 or 0x69"
    echo "  Check sensor wiring and power"
    echo
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check Python dependencies
echo
echo "Checking Python dependencies..."
if ! python3 -c "import smbus2" 2>/dev/null; then
    echo "⚠ smbus2 not installed"
    echo "  Installing smbus2..."
    pip3 install smbus2
fi
echo "✓ Python dependencies installed"

# Run test script
echo
echo "============================================================"
echo "Running CO2 sensor test..."
echo "============================================================"
echo

python3 test_co2.py

echo
echo "============================================================"
echo "Next steps:"
echo "============================================================"
echo
echo "If the test passed:"
echo "  1. Edit docker-compose.yml and set HARDWARE_MODE=real"
echo "  2. Add I2C device to volumes:"
echo "     - /dev/i2c-1:/dev/i2c-1"
echo "  3. Run: docker-compose up --build"
echo
echo "If the test failed:"
echo "  1. Check I2C wiring"
echo "  2. Verify sensor power supply"
echo "  3. Check config_hardware.py settings"
echo "  4. See TESTING.md for detailed troubleshooting"
echo
