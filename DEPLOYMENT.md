# Bioreactor System Deployment Guide (v3)

This guide explains how to deploy the three-component bioreactor system using the v3 architecture.

## System Architecture

The bioreactor system uses a **hub-and-spoke architecture** with three Docker-based components:

```
┌─────────────┐      HTTP API      ┌──────────────┐      HTTP API      ┌─────────────────┐
│             │◄──────────────────►│              │◄──────────────────►│                 │
│ Web Server  │                    │     Hub      │                    │  Node (Pi 5)    │
│  (Port 3000)│                    │ (Port 8000)  │                    │  (Port 9000)    │
└─────────────┘                    └──────────────┘                    └─────────────────┘
   │                                     │                                    │
   ├─ User Interface                    ├─ Queue Manager                     ├─ Hardware Control
   ├─ Experiment Upload                 ├─ Experiment Orchestration          ├─ V3 API Adapters
   ├─ Live Dashboard (SSE)              ├─ State Persistence                 └─ Docker-in-Docker
   └─ Session Management                └─ HTTP Forwarding                        User Containers
```

**Communication:** All components communicate via HTTP REST APIs (no SSH required).

**Deployment:** Docker Compose for orchestration, all services run in containers.

## Prerequisites

- **Docker & Docker Compose** installed on all machines
- **Raspberry Pi 5** for the bioreactor-node (recommended)
- **Network connectivity** between all components (HTTP ports open)
- **Git** for cloning the repository

## Component Overview

### 1. **Bioreactor Node (bioreactor-node-v3)**
- **Location:** Runs on Raspberry Pi 5 with bioreactor hardware
- **Port:** 9000
- **Purpose:**
  - Hardware interface using v3 modular adapters
  - Runs user experiment containers via Docker-in-Docker
  - Dynamic API endpoints based on available hardware
- **Hardware Support:**
  - CO2 sensor (Atlas Scientific I2C)
  - Temperature sensors (DS18B20)
  - Optical density (ADS7830 ADC)
  - Eyespy ADC (ADS1115)
  - Pumps (TicUSB steppers)
  - Stirrer (PWM motor)
  - Peltier driver (PWM H-bridge)

### 2. **Bioreactor Hub**
- **Location:** Can run anywhere (same machine as node or separate server)
- **Port:** 8000
- **Purpose:**
  - Experiment queue management (FIFO, one at a time)
  - State persistence (JSON-based)
  - HTTP forwarding to node
  - Background worker for experiment execution

### 3. **Web Server**
- **Location:** Can run anywhere (same machine or separate)
- **Port:** 3000
- **Purpose:**
  - User interface for experiment upload
  - Live dashboard with Server-Sent Events (SSE)
  - Session-based user tracking
  - Experiment result downloads

---

## Quick Start (All-in-One Deployment)

For local development or single-machine deployment:

```bash
# Clone the repository
git clone <your-repo-url>
cd bioreactor_website

# Start all three components
docker compose up --build

# Access the services:
# - Web Server:  http://localhost:3000
# - Hub API:     http://localhost:8000
# - Node API:    http://localhost:9000
```

This starts:
- Web Server → Hub → Node (all communicating via HTTP)
- Shared Docker network for inter-container communication
- Volume mounts for data persistence

---

## Production Deployment

### 1. Deploy Bioreactor Node (Raspberry Pi 5)

The node must run on the Raspberry Pi 5 with hardware access.

#### Step 1: Clone Repository
```bash
ssh pi@<raspberry-pi-ip>
cd ~
git clone <your-repo-url>
cd bioreactor_website/bioreactor-node-v3
```

#### Step 2: Configure Hardware
Edit `config_hardware.py` to enable available hardware:

```python
INIT_COMPONENTS = {
    'co2_sensor': True,      # Atlas Scientific CO2 sensor (I2C)
    'temp_sensor': True,     # DS18B20 temperature sensors
    'optical_density': True, # ADS7830 photodiode ADC
    'eyespy_adc': True,      # ADS1115 high-precision ADC
    'pumps': True,           # TicUSB stepper pumps
    'stirrer': True,         # PWM stirrer motor
    'peltier_driver': True,  # PWM peltier driver
    'led': False,            # Optional LED indicator
    'ring_light': False,     # Optional NeoPixel ring
}

# CO2 sensor configuration
CO2_SENSOR_TYPE = 'atlas'  # or 'sensair_k33'
CO2_SENSOR_I2C_ADDRESS = 0x69

# Hardware mode
HARDWARE_MODE = 'real'  # or 'simulation' for testing
```

#### Step 3: Build Container
```bash
cd /home/pi/bioreactor_website
docker compose build bioreactor-node
```

#### Step 4: Run Node
```bash
# Using docker-compose (recommended)
docker compose up -d bioreactor-node

# Or standalone:
docker run -d \
  --name bioreactor-node-v3 \
  --privileged \
  -p 9000:9000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v ./bioreactor-node-v3/data:/app/data \
  -v /dev/gpiochip4:/dev/gpiochip4 \
  -v /dev/i2c-1:/dev/i2c-1 \
  -e HARDWARE_MODE=real \
  bioreactor-node-v3
```

**Important Volume Mounts:**
- `/var/run/docker.sock` - Required for Docker-in-Docker
- `/dev/gpiochip4` - Raspberry Pi 5 GPIO access
- `/dev/i2c-1` - I2C bus for sensors
- `./data` - Experiment data persistence

**Environment Variables:**
- `HARDWARE_MODE`: `real` or `simulation`
- `LOG_LEVEL`: `INFO`, `DEBUG`, `WARNING`, `ERROR`

#### Step 5: Verify Node
```bash
# Check if node is running
curl http://localhost:9000/api/status

# Check available hardware capabilities
curl http://localhost:9000/api/v3/capabilities

# Test CO2 sensor
curl http://localhost:9000/api/v3/co2_sensor/state
```

---

### 2. Deploy Bioreactor Hub

The hub can run on the same Pi as the node or on a separate server.

#### Step 1: Configure Environment
```bash
cd bioreactor-hub

# Create environment file (optional, has defaults)
cat > .env << EOF
BIOREACTOR_NODE_API_URL=http://bioreactor-node:9000
LOG_LEVEL=INFO
EOF
```

**If deploying hub on separate machine:**
```bash
# Update docker-compose.yml or use environment variable
export BIOREACTOR_NODE_API_URL=http://<raspberry-pi-ip>:9000
```

#### Step 2: Build and Run
```bash
cd /home/pi/bioreactor_website

# Using docker-compose (recommended)
docker compose up -d bioreactor-hub

# Or standalone:
docker run -d \
  --name bioreactor-hub \
  -p 8000:8000 \
  -v ./bioreactor-hub/data:/app/data \
  -e BIOREACTOR_NODE_API_URL=http://bioreactor-node:9000 \
  bioreactor-hub
```

**Volume Mounts:**
- `./data` - Queue persistence (experiment_queue.json)

**Environment Variables:**
- `BIOREACTOR_NODE_API_URL`: Node API endpoint (default: `http://bioreactor-node:9000`)

#### Step 3: Verify Hub
```bash
# Check hub status
curl http://localhost:8000/api/queue/status

# Should return:
# {
#   "total_queued": 0,
#   "total_running": 0,
#   "queue": []
# }
```

---

### 3. Deploy Web Server

The web server can run anywhere with network access to the hub.

#### Step 1: Configure Environment
```bash
cd web-server

# Create environment file (optional, has defaults)
cat > .env << EOF
BIOREACTOR_HUB_API_URL=http://bioreactor-hub:8000
BIOREACTOR_NODE_API_URL=http://bioreactor-node:9000
EOF
```

**If deploying web server on separate machine:**
```bash
export BIOREACTOR_HUB_API_URL=http://<hub-ip>:8000
export BIOREACTOR_NODE_API_URL=http://<node-ip>:9000
```

#### Step 2: Build and Run
```bash
cd /home/pi/bioreactor_website

# Using docker-compose (recommended)
docker compose up -d web-server

# Or standalone:
docker run -d \
  --name bioreactor-web-server \
  -p 3000:3000 \
  -v ./web-server/config:/app/config \
  -v ./web-server/uploads_tmp:/app/uploads_tmp \
  -v ./bioreactor-node-v3/data:/app/node_data:ro \
  -e BIOREACTOR_HUB_API_URL=http://bioreactor-hub:8000 \
  -e BIOREACTOR_NODE_API_URL=http://bioreactor-node:9000 \
  bioreactor-web-server
```

**Volume Mounts:**
- `./config` - Dashboard settings
- `./uploads_tmp` - Temporary file uploads
- `./bioreactor-node-v3/data` - Read-only access to experiment data (for dashboard CSV reading)

#### Step 3: Access Web Interface
```bash
# Open in browser
http://localhost:3000

# Or from another machine
http://<server-ip>:3000
```

---

## Docker Compose Configuration

The provided `docker-compose.yml` orchestrates all three components:

```yaml
services:
  web-server:
    build: ./web-server
    ports: ["3000:3000"]
    environment:
      - BIOREACTOR_HUB_API_URL=http://bioreactor-hub:8000
      - BIOREACTOR_NODE_API_URL=http://bioreactor-node:9000
    volumes:
      - ./web-server/uploads_tmp:/app/uploads_tmp
      - ./web-server/config:/app/config
      - ./bioreactor-node-v3/data:/app/node_data:ro
    networks:
      - bioreactor-network

  bioreactor-hub:
    build: ./bioreactor-hub
    ports: ["8000:8000"]
    environment:
      - BIOREACTOR_NODE_API_URL=http://bioreactor-node:9000
    volumes:
      - ./bioreactor-hub/data:/app/data
    networks:
      - bioreactor-network

  bioreactor-node:
    build: ./bioreactor-node-v3
    ports: ["9000:9000"]
    privileged: true
    environment:
      - HARDWARE_MODE=real
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./bioreactor-node-v3/data:/app/data
      - /dev/gpiochip4:/dev/gpiochip4
      - /dev/i2c-1:/dev/i2c-1
    networks:
      - bioreactor-network

networks:
  bioreactor-network:
    driver: bridge
```

**Network Architecture:**
- All containers share `bioreactor-network` bridge network
- Containers can reference each other by service name
- External access via published ports

---

## User Experiment Containers

User scripts run in isolated Docker containers managed by the node.

### Container Specification
- **Base Image:** `python:3.11-slim`
- **Allowed Packages:** numpy, pandas, matplotlib, scikit-learn, requests, scipy, pillow
- **Network:** Host mode (access to node API at `localhost:9000`)
- **Resource Limits:** 512MB memory, 1 CPU core
- **Volumes:**
  - `/app/user_script.py` - User's uploaded script (read-only)
  - `/app/output` - Output directory for CSV and logs (read-write)

### Environment Variables in User Containers
- `BIOREACTOR_NODE_API_URL`: Node API endpoint
- `EXPERIMENT_ID`: Unique experiment identifier
- `OUTPUT_DIR`: Output directory path (`/app/output`)

### User Script Example (V3 API)
```python
from bioreactor_client import Bioreactor, measure_all_data, write_data_to_csv
import time

bioreactor = Bioreactor()
max_duration = 300  # 5 minutes
interval = 10       # Measure every 10 seconds

start_time = time.time()
next_measurement_time = start_time

while True:
    current_time = time.time()
    elapsed = current_time - start_time

    if elapsed >= max_duration:
        break

    if current_time >= next_measurement_time:
        # Get all sensors + control states
        data = measure_all_data(bioreactor, include_controls=True)
        write_data_to_csv(data)

        print(f"CO2: {data.get('co2_ppm')} ppm")
        print(f"Temperature: {data.get('temperature')}°C")

        next_measurement_time += interval

    time.sleep(0.1)

print("Experiment complete!")
```

### V3 CSV Output Format
```csv
timestamp,co2_ppm,temperature,od_voltages,eyespy_voltages,stirrer_duty,peltier_duty,peltier_direction
2026-01-25T20:35:11.103915,633.0,25.4,[0.12,0.15,0.18],[],0.0,0.0,forward
```

**Columns:**
- `timestamp`: ISO 8601 format with microseconds
- `co2_ppm`: CO2 concentration (ppm)
- `temperature`: Single temperature reading (°C)
- `od_voltages`: List of optical density voltages
- `eyespy_voltages`: List of eyespy ADC voltages
- `stirrer_duty`: Stirrer duty cycle (0-100%)
- `peltier_duty`: Peltier duty cycle (0-100%)
- `peltier_direction`: "heat", "cool", "forward", or "reverse"

---

## Queue System

The hub manages a **FIFO queue** with experiment serialization.

### Queue States
```
QUEUED → RUNNING → COMPLETED
  ↓         ↓          ↓
PAUSED   FAILED   CANCELLED
```

### Queue Limits
- **Max experiments per user:** 5 active (queued/running)
- **Auto-cleanup:** Experiments older than 24 hours removed
- **Persistence:** Queue saved to `bioreactor-hub/data/experiment_queue.json`

### Queue Operations
```bash
# View queue status
curl http://localhost:8000/api/queue/status

# Cancel experiment
curl -X POST http://localhost:8000/api/experiments/{id}/cancel

# Pause experiment
curl -X POST http://localhost:8000/api/experiments/{id}/pause

# Resume experiment
curl -X POST http://localhost:8000/api/experiments/{id}/resume

# Reorder experiment
curl -X POST http://localhost:8000/api/experiments/{id}/reorder?new_position=0
```

---

## Live Dashboard

The web server provides a real-time dashboard using Server-Sent Events (SSE).

### Data Sources
- **During experiment:** Reads from experiment CSV file
- **No experiment:** Reads directly from hardware API
- **Display:** Shows "Data Source: CSV" or "Data Source: Hardware"

### Dashboard Configuration
Edit via web UI at `http://localhost:3000/settings`:
- Enable/disable sensor displays (CO2, temperature, OD, etc.)
- Adjust update interval (default: 2 seconds)
- Configure CSV file path

### Accessing Dashboard
```bash
# Navigate to:
http://localhost:3000/dashboard

# SSE endpoint (for custom clients):
http://localhost:3000/api/live-data
```

---

## Testing the Deployment

### 1. Health Checks
```bash
# Node health
curl http://localhost:9000/api/status

# Hub health
curl http://localhost:8000/api/queue/status

# Web server (open in browser)
http://localhost:3000
```

### 2. Test Experiment Upload
```bash
# Create test script
cat > test_experiment.py << 'EOF'
from bioreactor_client import Bioreactor, measure_all_data, write_data_to_csv
import time

bioreactor = Bioreactor()
data = measure_all_data(bioreactor)
write_data_to_csv(data)
print(f"CO2: {data.get('co2_ppm')} ppm")
EOF

# Upload via web interface
# Navigate to http://localhost:3000/upload
# Or use API:
curl -X POST http://localhost:8000/api/experiments/start \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-user" \
  -d '{"script_content": "'"$(cat test_experiment.py)"'"}'
```

### 3. Monitor Experiment
```bash
# Check queue status
curl http://localhost:8000/api/queue/status

# Watch logs
docker logs -f bioreactor-node-v3

# View in web UI
http://localhost:3000/my-experiments
```

### 4. Download Results
```bash
# Via web UI:
http://localhost:3000/my-experiments → Download button

# Or via API:
curl -O http://localhost:8000/api/experiments/{id}/download
```

---

## Troubleshooting

### Common Issues

#### 1. **Node container fails to start**
```bash
# Check Docker daemon
sudo systemctl status docker

# Check Docker socket permissions
ls -la /var/run/docker.sock

# Check GPIO/I2C device access
ls -la /dev/gpiochip4 /dev/i2c-1

# Review logs
docker logs bioreactor-node-v3
```

#### 2. **Hub can't connect to Node**
```bash
# Check network connectivity
docker network inspect bioreactor_website_bioreactor-network

# Verify node is accessible
curl http://bioreactor-node:9000/api/status

# Check environment variables
docker exec bioreactor-hub env | grep NODE
```

#### 3. **Dashboard shows "Data Source: Unknown"**
```bash
# Check experiment is running
curl http://localhost:8000/api/queue/status

# Verify CSV file exists
ls -la bioreactor-node-v3/data/experiments/{id}/output/

# Check web-server logs
docker logs bioreactor_website-web-server-1
```

#### 4. **Hardware sensors not working**
```bash
# Check hardware configuration
cat bioreactor-node-v3/config_hardware.py

# Test I2C devices
i2cdetect -y 1

# Check capabilities
curl http://localhost:9000/api/v3/capabilities

# Test specific sensor
curl http://localhost:9000/api/v3/co2_sensor/state
```

#### 5. **Experiment fails with exit code 1**
```bash
# Get experiment ID from web UI or queue
EXPERIMENT_ID=<id>

# Check container logs
cat bioreactor-node-v3/data/experiments/$EXPERIMENT_ID/output/container_logs.txt

# Check user script
cat bioreactor-node-v3/data/experiments/$EXPERIMENT_ID/user_script.py

# Verify output directory permissions
ls -la bioreactor-node-v3/data/experiments/$EXPERIMENT_ID/
```

---

## Performance Tuning

### Resource Limits
Adjust in `docker-compose.yml`:
```yaml
services:
  bioreactor-node:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
```

### Experiment Container Limits
Edit `bioreactor-node-v3/src/api/experiments.py`:
```python
mem_limit="1g"     # Default: 512m
cpu_quota=200000   # Default: 100000 (1 CPU)
```

---

## Security Considerations

### 1. Network Security
- Use firewalls to restrict port access
- Consider VPN for remote access
- Use reverse proxy with HTTPS (nginx/traefik)

### 2. Container Security
- User containers run without `--privileged` flag
- Limited package whitelist
- Resource limits prevent DoS

### 3. Data Security
- Queue persistence in JSON (consider encryption)
- Experiment data readable by web-server (read-only mount)
- Session IDs are UUID-based (not cryptographic)

---

## Backup and Recovery

### Data Backup
```bash
# Backup experiment data
tar -czf bioreactor_backup_$(date +%Y%m%d).tar.gz \
  bioreactor-node-v3/data \
  bioreactor-hub/data \
  web-server/config

# Automated daily backup
0 2 * * * /home/pi/backup.sh
```

### Recovery
```bash
# Restore from backup
tar -xzf bioreactor_backup_20260125.tar.gz

# Restart services
docker compose restart
```

---

## Updating the System

```bash
# Pull latest code
git pull origin main

# Rebuild containers
docker compose build

# Restart with new images
docker compose down
docker compose up -d

# Verify all services
docker compose ps
```

---

## Support and Documentation

- **API Documentation:** See `/api/docs` on each component
- **CLAUDE.md:** Development guidance for AI assistants
- **README.md:** Project overview
- **GitHub Issues:** Report bugs and request features
