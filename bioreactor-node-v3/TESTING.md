# Testing Bioreactor Node v3 with CO2 Sensor Only

This guide helps you test the bioreactor-node-v3 system on hardware with only the CO2 sensor active.

## Prerequisites

- Raspberry Pi 5 or Pi Zero 2 W (or compatible)
- CO2 sensor connected via I2C (Senseair K33 or Atlas Scientific)
- Docker and Docker Compose installed
- I2C enabled on the Pi

## Step 1: Verify I2C and CO2 Sensor Hardware

First, make sure I2C is enabled and the sensor is detected:

```bash
# Check if I2C is enabled
ls -l /dev/i2c-*

# Should show something like /dev/i2c-1

# Install i2c-tools if needed
sudo apt-get install -y i2c-tools

# Scan I2C bus for connected devices
i2cdetect -y 1

# You should see your CO2 sensor at address 0x68 (Senseair) or 0x69 (Atlas)
```

Example output:
```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
60: -- -- -- -- -- -- -- -- 68 -- -- -- -- -- -- --
70: -- -- -- -- -- -- -- --
```

If you see `68` (or your sensor's address), the sensor is detected!

## Step 2: Configure Hardware Settings

The `config_hardware.py` file is already set up for CO2 sensor only. Verify the settings:

```bash
cd bioreactor-node-v3
cat config_hardware.py
```

Key settings to verify:
- `CO2_SENSOR_ENABLED = True`
- `CO2_SENSOR_TYPE = 'sensair_k33'` (or 'atlas' if using Atlas sensor)
- `CO2_SENSOR_I2C_BUS = 1`
- All other components disabled (since you don't have them connected)

**If using Atlas Scientific CO2 sensor**, edit the file:
```bash
nano config_hardware.py
```
Change:
```python
CO2_SENSOR_TYPE = 'atlas'  # or 'atlas_i2c'
```

## Step 3: Test CO2 Sensor Directly (Without Docker)

Before running Docker, test the sensor directly on the hardware:

```bash
cd bioreactor-node-v3

# Install dependencies (if not already installed)
pip3 install smbus2 lgpio

# Make test script executable
chmod +x test_co2.py

# Run test
python3 test_co2.py
```

Expected output:
```
============================================================
CO2 Sensor Test
============================================================

Configuration:
  CO2_SENSOR_ENABLED: True
  CO2_SENSOR_TYPE: sensair_k33
  CO2_SENSOR_I2C_BUS: 1
  CO2_SENSOR_I2C_ADDRESS: auto

Initializing bioreactor...
✓ Bioreactor initialized

Component initialization status:
  ✓ co2_sensor: True

✓ CO2 sensor initialized successfully

Testing CO2 reading...
  Attempt 1: ✓ CO2 = 450 ppm
  Attempt 2: ✓ CO2 = 452 ppm
  Attempt 3: ✓ CO2 = 451 ppm

Cleaning up...
✓ Test complete!
```

If this works, your hardware is ready! If it fails, troubleshoot the I2C connection.

## Step 4: Configure Docker Compose for Real Hardware

Edit the main `docker-compose.yml` to use real hardware mode:

```bash
cd /home/david/Documents/GitHub/bioreactor_website
nano docker-compose.yml
```

Find the `bioreactor-node` service and change:
```yaml
environment:
  - HARDWARE_MODE=real  # Change from "simulation" to "real"
```

Also ensure the I2C device is mounted (add if not present):
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - ./bioreactor-node-v3/data:/app/data
  - /dev/gpiochip4:/dev/gpiochip4  # Pi 5 GPIO
  - /dev/i2c-1:/dev/i2c-1          # I2C bus for CO2 sensor
```

For Pi Zero 2 W, you may need `/dev/gpiochip0` instead of `/dev/gpiochip4`.

## Step 5: Build and Start the System

```bash
cd /home/david/Documents/GitHub/bioreactor_website

# Build all services
docker-compose build

# Start all services
docker-compose up
```

Watch the logs - you should see:
```
bioreactor-node-v3  | ============================================================
bioreactor-node-v3  | Starting Bioreactor Node v3
bioreactor-node-v3  | ============================================================
bioreactor-node-v3  | Hardware mode: real
bioreactor-node-v3  | Initializing hardware...
bioreactor-node-v3  | ✓ Hardware initialized successfully
bioreactor-node-v3  | Initialized components:
bioreactor-node-v3  |   ✓ co2_sensor
bioreactor-node-v3  | ============================================================
bioreactor-node-v3  | Bioreactor Node v3 ready
bioreactor-node-v3  | ============================================================
```

## Step 6: Test the API

Open a new terminal and test the API endpoints:

```bash
# Health check
curl http://localhost:9000/health

# Should show:
# {
#   "status": "healthy",
#   "version": "3.0.0",
#   "hardware_mode": "real",
#   "hardware_available": true,
#   "initialized_components": {
#     "co2_sensor": true
#   }
# }

# Check capabilities (shows available components)
curl http://localhost:9000/api/v3/capabilities

# Should show only co2_sensor

# Read CO2 sensor (v3 API)
curl http://localhost:9000/api/v3/co2_sensor/state

# Should return:
# {
#   "status": "success",
#   "co2_ppm": 450.0,
#   "unit": "ppm"
# }

# Read all sensors (v2 legacy API)
curl http://localhost:9000/api/sensors/all

# Should return:
# {
#   "status": "success",
#   "co2_ppm": 450.0
# }
```

## Step 7: Test Through Web Interface

1. Open browser to http://localhost:3000
2. You should see the web interface
3. Upload a simple test script:

```python
from bioreactor_client import Bioreactor

with Bioreactor() as reactor:
    # Read CO2
    co2_data = reactor.client.read_co2_sensor()
    print(f"CO2 reading: {co2_data}")

    # Try legacy API
    sensors = reactor.client._request("GET", "/api/sensors/all")
    print(f"All sensors: {sensors}")

    print("Test complete!")
```

4. Submit the script
5. Check the experiment status - it should queue and execute
6. View the logs to see the CO2 reading

## Step 8: Test Queue System

Submit multiple experiments to test the queue:

```bash
# Submit experiment 1
curl -X POST http://localhost:8000/api/experiments/start \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-session-1" \
  -d '{
    "script_content": "from bioreactor_client import Bioreactor\nwith Bioreactor() as r:\n    co2 = r.client.read_co2_sensor()\n    print(f\"CO2: {co2}\")"
  }'

# Submit experiment 2
curl -X POST http://localhost:8000/api/experiments/start \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-session-1" \
  -d '{
    "script_content": "import time\nfrom bioreactor_client import Bioreactor\nwith Bioreactor() as r:\n    for i in range(5):\n        co2 = r.client.read_co2_sensor()\n        print(f\"Reading {i+1}: CO2 = {co2}\")\n        time.sleep(2)"
  }'

# Check queue status
curl http://localhost:8000/api/queue/status
```

You should see experiments queue up and execute one at a time.

## Troubleshooting

### CO2 sensor not detected in I2C scan

- Check wiring connections
- Verify sensor power supply
- Try a different I2C address (some sensors have configurable addresses)
- Check if I2C is enabled: `sudo raspi-config` → Interface Options → I2C

### Docker permission denied for I2C

Add your user to the i2c group:
```bash
sudo usermod -aG i2c $USER
sudo chmod 666 /dev/i2c-1
```

### Container fails to start

Check logs:
```bash
docker logs bioreactor-node-v3
```

Common issues:
- I2C device not mounted: Add `/dev/i2c-1:/dev/i2c-1` to volumes
- Permission denied: Add `privileged: true` to docker-compose.yml
- smbus2 import error: Rebuild container with `docker-compose build`

### CO2 readings are None or error

- Check I2C bus number (might be /dev/i2c-0 instead of /dev/i2c-1)
- Verify sensor type in config_hardware.py
- Check sensor I2C address matches config
- Test sensor with `i2cget -y 1 0x68` (replace 0x68 with your address)

### Other components show errors

This is expected! Since only CO2 sensor is connected, other components will fail to initialize. They should show:
- `✗ component_name: False` in initialization logs
- Not appear in `/api/v3/capabilities`
- Return 503 errors if accessed via legacy API

This is normal and won't affect CO2 sensor operation.

## Running in Background

To run the system in the background:

```bash
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Success Indicators

You'll know everything is working when:

1. ✓ `test_co2.py` reads valid CO2 values
2. ✓ Docker containers all start successfully
3. ✓ Health endpoint shows `co2_sensor: true`
4. ✓ Capabilities endpoint shows only `co2_sensor`
5. ✓ API returns valid CO2 readings
6. ✓ Experiments can read CO2 sensor successfully
7. ✓ Queue system processes experiments one at a time

## Next Steps

Once CO2 sensor is working:

- Add more sensors as you connect them (edit `config_hardware.py`)
- Monitor CO2 levels over time with periodic experiments
- Create data logging scripts that save to `/app/output`
- Integrate with other systems via the REST API

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review container logs: `docker-compose logs`
3. Test sensor directly with `test_co2.py`
4. Verify I2C with `i2cdetect -y 1`
5. Check GitHub issues for similar problems
