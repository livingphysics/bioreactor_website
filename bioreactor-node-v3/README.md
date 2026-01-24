# Bioreactor Node v3

Modular hardware control system with plugin-based architecture and v2 compatibility.

## Overview

Bioreactor Node v3 integrates the modular `bioreactor_v3` hardware abstraction into the distributed control system. It provides:

- **Dynamic API generation**: Endpoints auto-generated from available hardware components
- **Plugin-based architecture**: Add new hardware by creating an adapter class
- **v2 compatibility**: Existing hub code works without changes
- **Git submodule integration**: Hardware code stays DRY and up-to-date
- **HTTP-only communication**: Simpler than SSH, better error handling

## Architecture

### Component Adapter Pattern

Each hardware component from `bioreactor_v3` is wrapped by a `ComponentAdapter` that exposes it via REST API. Adding new hardware requires:

1. Add initialization function to `bioreactor_v3/src/components.py`
2. Create adapter class in `src/adapters/`
3. Register in `src/adapters/registry.py`
4. **Done** - API endpoints are auto-generated

### Directory Structure

```
bioreactor-node-v3/
├── bioreactor_v3/              # Git submodule → ../bioreactor_v3
├── src/
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Node configuration
│   ├── api/
│   │   ├── endpoints.py        # Dynamic v3 endpoints
│   │   ├── legacy.py           # v2 compatibility layer
│   │   ├── experiments.py      # Docker container management
│   │   └── schemas.py          # Pydantic models
│   ├── adapters/
│   │   ├── base.py             # ComponentAdapter base class
│   │   ├── registry.py         # Component adapter mapping
│   │   ├── peltier.py          # Peltier adapter
│   │   ├── stirrer.py          # Stirrer adapter
│   │   ├── led.py              # LED adapter
│   │   ├── ring_light.py       # Ring light adapter
│   │   ├── pumps.py            # Pump adapter
│   │   └── sensors.py          # Temperature, OD, eyespy, CO2 adapters
│   └── container/
│       ├── manager.py          # Docker lifecycle
│       └── client_builder.py  # BioreactorClient generator
├── docker/
│   ├── Dockerfile              # User experiment container
│   └── requirements.txt        # User container dependencies
├── requirements.txt
├── Dockerfile
└── README.md
```

## Quick Start

### Development Mode (No Hardware)

```bash
# Start all services with simulation mode
docker-compose up --build

# Access points:
# - Web Server: http://localhost:8080
# - Bioreactor Hub: http://localhost:8000
# - Bioreactor Node v3: http://localhost:9000
```

### Production Mode (Real Hardware)

```bash
# Edit docker-compose.yml to set HARDWARE_MODE=real
# Ensure /dev/gpiochip4 is available (Raspberry Pi 5)
docker-compose up --build
```

### Local Development

```bash
cd bioreactor-node-v3

# Install dependencies
pip install -r requirements.txt

# Run in simulation mode
export HARDWARE_MODE=simulation
uvicorn src.main:app --reload --port 9000

# Run with real hardware
export HARDWARE_MODE=real
uvicorn src.main:app --reload --port 9000
```

## API Documentation

### v3 Dynamic Endpoints

The v3 API auto-generates endpoints for each initialized hardware component.

**Discover available components:**
```bash
GET /api/v3/capabilities
```

**Control a component (if actuator):**
```bash
POST /api/v3/{component_name}/control
```

**Read component state:**
```bash
GET /api/v3/{component_name}/state
```

**Example - Control peltier:**
```bash
curl -X POST http://localhost:9000/api/v3/peltier_driver/control \
  -H "Content-Type: application/json" \
  -d '{"duty_cycle": 50, "direction": "heat"}'
```

### v2 Legacy Endpoints (Hub Compatibility)

These endpoints maintain compatibility with the existing hub:

```bash
POST /api/led                    # Control LED
POST /api/peltier                # Control peltier
POST /api/ring-light             # Control ring light
POST /api/pump                   # Control pump
POST /api/stirrer                # Control stirrer
GET  /api/sensors/all            # Read all sensors
GET  /api/sensors/photodiodes    # Read OD sensors
GET  /api/sensors/temperature    # Read temperature sensors
GET  /api/status                 # Get hardware status
```

### Experiment Management

```bash
POST   /api/experiments/start               # Start experiment
GET    /api/experiments/{id}/status         # Get status
GET    /api/experiments/{id}/logs           # Get logs
GET    /api/experiments/{id}/download       # Download results
POST   /api/experiments/{id}/stop           # Stop experiment
DELETE /api/experiments/{id}                # Delete experiment
GET    /api/experiments                     # List experiments
```

### Health Check

```bash
GET /health
```

Returns:
```json
{
  "status": "healthy",
  "version": "3.0.0",
  "hardware_mode": "simulation",
  "hardware_available": true,
  "initialized_components": {
    "peltier_driver": true,
    "stirrer": true,
    "led": true
  }
}
```

## Adding New Hardware

**Example: Adding a pH Sensor**

### 1. Add to bioreactor_v3

Edit `bioreactor_v3/src/components.py`:

```python
def init_ph_sensor(config):
    """Initialize pH sensor"""
    try:
        # Initialize hardware
        ph_sensor = PHSensorDriver(config.PH_SENSOR_PIN)
        return {'initialized': True, 'sensor': ph_sensor}
    except Exception as e:
        logger.error(f"pH sensor init failed: {e}")
        return {'initialized': False}

# Register component
COMPONENT_REGISTRY['ph_sensor'] = init_ph_sensor
```

### 2. Create adapter

Create `src/adapters/ph_sensor.py`:

```python
from pydantic import BaseModel
from .base import ComponentAdapter
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'bioreactor_v3', 'src'))
from io import read_ph_sensor

class PHStateResponse(BaseModel):
    status: str
    ph_value: float

class PHSensorAdapter(ComponentAdapter):
    def get_capabilities(self):
        return {
            "type": "sensor",
            "sensor_type": "ph",
            "range": [0, 14],
            "description": "pH sensor"
        }

    def get_control_schema(self):
        return None  # Sensor only

    def get_state_schema(self):
        return PHStateResponse

    async def control(self, request):
        return {"status": "error", "message": "Sensors do not support control"}

    async def read_state(self):
        if not self.initialized:
            return {"status": "error", "ph_value": 0.0}
        try:
            ph = read_ph_sensor(self.bioreactor)
            return {"status": "success", "ph_value": ph}
        except Exception as e:
            return {"status": "error", "ph_value": 0.0, "message": str(e)}
```

### 3. Register adapter

Edit `src/adapters/registry.py`:

```python
from .ph_sensor import PHSensorAdapter

COMPONENT_ADAPTERS = {
    # ... existing adapters
    'ph_sensor': PHSensorAdapter,
}
```

### 4. Done!

The API automatically generates:
- `GET /api/v3/ph_sensor/state` - Read pH value
- Capability info in `GET /api/v3/capabilities`
- User containers get `client.read_ph_sensor()` method

## Configuration

### Environment Variables

- `HARDWARE_MODE` - Set to `real` for hardware, `simulation` for testing (default: `simulation`)
- `LOG_LEVEL` - Logging verbosity: DEBUG, INFO, WARNING, ERROR (default: `INFO`)
- `HOST` - API host (default: `0.0.0.0`)
- `PORT` - API port (default: `9000`)
- `DATA_DIR` - Data directory (default: `/app/data`)
- `LOG_DIR` - Log directory (default: `/app/logs`)

### Hardware Support

- **Raspberry Pi 5**: Full support via GPIO chip 4 (`/dev/gpiochip4`)
- **Raspberry Pi Zero 2 W**: Full support via legacy GPIO
- **Simulation**: No hardware required, API returns mock data

## Docker Configuration

### Node Container

**Volumes:**
- `/var/run/docker.sock` - Docker socket for container management
- `/app/data` - Experiment data persistence
- `/dev/gpiochip4` - GPIO access (Pi 5 only, real mode)

**Privileges:**
- `privileged: true` required for Docker-in-Docker and GPIO

### User Experiment Container

**Base image:** `python:3.11-slim`

**Allowed packages:**
- numpy, pandas, matplotlib
- scikit-learn, requests
- scipy, pillow

**Resource limits:**
- Memory: 512MB
- CPU: 1 core

**Network:** Host mode for direct API access

## Updating bioreactor_v3

The hardware abstraction is a git submodule. To update:

```bash
cd bioreactor-node-v3/bioreactor_v3
git pull origin main
cd ..
git add bioreactor_v3
git commit -m "Update bioreactor_v3 submodule"
```

## Testing

### Manual API Testing

```bash
# Check health
curl http://localhost:9000/health

# Discover components
curl http://localhost:9000/api/v3/capabilities

# Control LED (v3)
curl -X POST http://localhost:9000/api/v3/led/control \
  -H "Content-Type: application/json" \
  -d '{"power": 100}'

# Control LED (v2 legacy)
curl -X POST http://localhost:9000/api/led \
  -H "Content-Type: application/json" \
  -d '{"state": true}'

# Read sensors
curl http://localhost:9000/api/sensors/all
```

### Submit Test Experiment

Through web interface at http://localhost:8080 or via hub API:

```bash
curl -X POST http://localhost:8000/api/experiments/start \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-session-123" \
  -d '{
    "script_content": "from bioreactor_client import Bioreactor\nwith Bioreactor() as reactor:\n    reactor.change_led(True)\n    print(\"Test complete\")"
  }'
```

## Troubleshooting

### Container fails to start

- Check Docker daemon is running
- Verify `/var/run/docker.sock` is mounted
- Check container logs: `docker logs bioreactor-node-v3`

### Hardware not accessible

- Verify `HARDWARE_MODE=real` in docker-compose.yml
- Check GPIO device exists: `ls -l /dev/gpiochip4`
- Ensure container has `privileged: true`
- Check bioreactor_v3 hardware connections

### API returns 503 errors

- Check hardware initialization in logs
- Verify component is in `initialized_components` from `/health`
- Try simulation mode to isolate hardware issues

### Hub cannot connect

- Verify `BIOREACTOR_NODE_API_URL` environment variable
- Check network configuration in docker-compose.yml
- Test connection: `curl http://bioreactor-node:9000/health` (from hub container)

## Migration from v2

The v3 node is a drop-in replacement for v2:

1. **Hub changes**: Only environment variable change (`BIOREACTOR_NODE_API_URL`)
2. **API compatibility**: All v2 endpoints work unchanged
3. **User scripts**: Existing scripts work without modification
4. **Queue system**: No changes required

## Version History

- **v3.0.0** (2026-01-24): Initial release with modular architecture
  - Dynamic API generation
  - Component adapter system
  - v2 compatibility layer
  - HTTP-only communication
  - Git submodule integration
