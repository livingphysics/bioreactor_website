# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

This is a distributed bioreactor control system with three independently containerized components that communicate via REST APIs and SSH:

1. **Web Server** (Port 8080): User interface for uploading scripts and managing experiments
2. **Bioreactor Hub** (Port 8000): Middleware for experiment queuing and orchestration
3. **Bioreactor Node** (Port 9000): Hardware interface and Docker container manager for user experiments

The system implements a **hub-and-spoke architecture** with queue-based experiment serialization (one experiment at a time).

## Development Commands

### Running the Full System

```bash
# Start all three components using Docker Compose
docker-compose up --build

# Access points:
# - Web Server: http://localhost:8080
# - Bioreactor Hub: http://localhost:8000
# - Bioreactor Node: http://localhost:9000
```

### Running Individual Components

#### Web Server
```bash
cd web-server
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8080
```

#### Bioreactor Hub
```bash
cd bioreactor-hub
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

#### Bioreactor Node
```bash
cd bioreactor-node
pip install -r requirements.txt
# For simulation mode (no hardware required)
export HARDWARE_MODE=simulation
uvicorn src.main:app --reload --port 9000
```

### Testing

```bash
# System integration test (requires all components running)
python test_system.py

# Queue system test
python test_queue_system.py

# Component-specific tests (if available)
cd web-server && pytest tests/
cd bioreactor-hub && pytest tests/
cd bioreactor-node && pytest tests/
```

### Building Docker Images

```bash
# Build individual component
docker build -t bioreactor-web-server ./web-server
docker build -t bioreactor-hub ./bioreactor-hub
docker build -t bioreactor-node ./bioreactor-node

# Build user experiment container image
cd bioreactor-node/docker
docker build -t bioreactor-user-experiment .
```

## Architecture

### Communication Flow

```
User → Web Server (FastAPI)
     → Bioreactor Hub (FastAPI + Queue Manager)
     → Bioreactor Node (FastAPI + Docker)
     → User Experiment Container
     → Hardware (via Bioreactor class)
```

### Key Architectural Patterns

**Three-Tier Distributed System:**
- Web Server: User interface and session management
- Hub: Experiment queue persistence and orchestration
- Node: Hardware abstraction and container lifecycle management

**Queue-Based Serialization:**
- Only one experiment runs at a time (prevents hardware conflicts)
- FIFO ordering with user limits (max 5 experiments per user session)
- JSON-based persistence in `bioreactor-hub/data/experiment_queue.json`
- Background worker thread polls and executes queued experiments

**Docker-in-Docker Pattern:**
- Node container has access to host Docker daemon via `/var/run/docker.sock`
- User scripts run in isolated containers with resource limits (512MB, 1 CPU)
- Container network mode is `host` for API access to Node

### Critical Components

#### Queue Manager (`bioreactor-hub/src/queue_manager.py`)
- Manages experiment lifecycle: QUEUED → RUNNING → COMPLETED/FAILED
- Thread-safe operations with `threading.Lock()`
- Methods: `add_experiment()`, `get_next_experiment()`, `start_experiment()`, `complete_experiment()`, `cancel_experiment()`, `pause_experiment()`, `resume_experiment()`, `reorder_experiment()`
- Auto-cleanup removes experiments older than 24 hours on startup

#### Hardware Abstraction (`bioreactor-node/src/bioreactor.py`)
- `Bioreactor` class provides unified interface to all hardware components
- Graceful degradation: tracks component initialization success in `_initialized` dict
- Supports simulation mode for development without hardware
- Components: LEDs, NeoPixel ring light, DS18B20 temperature sensors, ADS7830 photodiode ADCs, INA219 current sensor, PWM peltier control, TicUSB stepper pumps, PWM stirrer
- Context manager support for automatic cleanup

#### SSH Communication (`bioreactor-hub/src/ssh_client.py`)
- Hub → Node communication via SSH for container orchestration
- `BioreactorNodeClient` class wraps Paramiko for command execution
- Used for Docker container management and status polling

#### Container Lifecycle (`bioreactor-node/src/main.py: run_experiment_container()`)
1. Create experiment directory structure in `/app/data/experiments/{id}/`
2. Write user script to disk as `user_script.py`
3. Spawn Docker container with `docker_client.containers.run()`
4. Track container in global `containers` dict
5. Wait for completion with `container.wait()`
6. Store exit code and status
7. Auto-remove container after execution

### API Endpoints

**Bioreactor Hub API:**
- `POST /api/experiments/start` - Queue new experiment
- `GET /api/experiments/{id}/status` - Get experiment status
- `GET /api/queue/status` - Get queue info and wait times
- `GET /api/experiments/user` - Get user's experiments (via X-Session-ID header)
- `POST /api/experiments/{id}/cancel` - Cancel queued experiment
- `POST /api/experiments/{id}/pause` - Pause queued experiment
- `POST /api/experiments/{id}/resume` - Resume paused experiment
- `POST /api/experiments/{id}/reorder` - Change queue position
- `GET /api/experiments/{id}/download` - Download results ZIP

**Bioreactor Node API (Hardware Control):**
- `POST /api/led` - Control main LED (on/off)
- `POST /api/ring-light` - Control NeoPixel ring light (color, pixel index)
- `POST /api/peltier` - Temperature control (power, direction)
- `POST /api/pump` - Pump control (name, velocity in mL/s)
- `POST /api/stirrer` - Stirrer control (duty cycle)
- `GET /api/sensors/all` - Read all sensors
- `GET /api/sensors/photodiodes` - Optical density (OD) readings
- `GET /api/sensors/temperature` - Temperature sensor readings
- `GET /api/status` - Hardware component status

**Bioreactor Node API (Experiment Management):**
- `POST /api/experiments/start` - Start user experiment container
- `GET /api/experiments/{id}/status` - Get container status
- `POST /api/experiments/{id}/stop` - Stop running experiment

### User Experiment Containers

**Container Specification:**
- Base Image: `python:3.11-slim`
- Allowed Packages: numpy, pandas, matplotlib, scikit-learn, requests, scipy, pillow
- Network: Host mode for API access (`host.docker.internal:9000`)
- Volumes:
  - User script: `/app/user_script.py` (read-only)
  - Output directory: `/app/output` (read-write)
- Environment: `BIOREACTOR_NODE_API_URL`, `EXPERIMENT_ID`
- Resource Limits: 512MB memory, 1 CPU core

**User Script API:**
User scripts interact with hardware via `BioreactorClient` class (injected into container), which makes HTTP calls to Node API endpoints.

## Configuration

### Environment Variables

**Web Server:**
- `BIOREACTOR_HUB_API_URL` - Hub API URL (default: http://bioreactor-hub:8000)

**Bioreactor Hub:**
- `BIOREACTOR_NODE_HOST` - Node hostname for SSH (default: bioreactor-node)
- `BIOREACTOR_NODE_PORT` - SSH port (default: 22)
- `BIOREACTOR_NODE_USERNAME` - SSH username (default: pi)
- `SSH_KEY_PATH` - Path to SSH private key (default: /app/ssh_keys/id_rsa)

**Bioreactor Node:**
- `HARDWARE_MODE` - Set to `simulation` for testing without hardware, `real` for production
- `LOG_LEVEL` - Logging verbosity (default: INFO)

### Data Persistence

- Hub queue: `bioreactor-hub/data/experiment_queue.json`
- Experiment data: `bioreactor-node/data/experiments/{experiment_id}/`
- User uploads: `web-server/uploads_tmp/`

## Important Development Notes

### Session Management
- User tracking via `X-Session-ID` header (UUID-based, cookie-stored)
- Not cryptographic authentication - for internal/research use
- Web Server generates and propagates session IDs to Hub

### Queue State Machine
```
QUEUED ───────────────> RUNNING ───────> COMPLETED
  │                         │
  ↓                         ↓
PAUSED                   FAILED
  │
  ↓ (resume)
QUEUED
  │
  ↓ (cancel)
CANCELLED
```

### Hardware Mode Behavior
- **Simulation Mode**: Hardware initialization skipped, API returns mock data
- **Real Mode**: Requires actual hardware, initialization errors tracked in `_initialized` dict
- Hardware class methods check `_initialized` before executing, return NaN for unavailable components

### Docker Socket Access
Node container must have access to Docker daemon:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
privileged: true
```

### Thread Safety
- Hub's `QueueManager` uses `threading.Lock()` for all queue operations
- Node's `containers` dict is accessed by background worker and API handlers (potential race condition - be careful)

### Common Issues

1. **Container fails to start**: Check Docker daemon is running, verify `/var/run/docker.sock` is mounted
2. **SSH connection fails**: Verify SSH keys in `bioreactor-hub/ssh_keys/`, check Node is running on port 22
3. **Hardware not accessible**: Set `HARDWARE_MODE=simulation` or check GPIO permissions and hardware connections
4. **Queue not persisting**: Check write permissions on `bioreactor-hub/data/` directory

## File Structure

```
bioreactor_website/
├── web-server/           # User interface component
│   ├── src/main.py      # FastAPI app with route handlers
│   ├── templates/       # Jinja2 HTML templates
│   └── requirements.txt
├── bioreactor-hub/      # Orchestration middleware
│   ├── src/main.py      # FastAPI app with queue worker
│   ├── src/queue_manager.py  # Queue persistence logic
│   ├── src/ssh_client.py     # SSH to Node
│   └── requirements.txt
├── bioreactor-node/     # Hardware interface
│   ├── src/main.py      # FastAPI app with hardware endpoints
│   ├── src/bioreactor.py     # Hardware abstraction class
│   ├── docker/          # User experiment container files
│   │   └── bioreactor_client.py  # API client for user scripts
│   └── requirements.txt
├── docker-compose.yml   # Full system orchestration
├── test_system.py       # Integration tests
└── test_queue_system.py # Queue system tests
```
