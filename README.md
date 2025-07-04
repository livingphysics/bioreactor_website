# Bioreactor Control System

A distributed system for running user experiments on bioreactor hardware with proper isolation, security, and queue management.

## Architecture

This project consists of three main components:

### 1. Web Server (`web-server/`)
- **Purpose**: User interface for uploading scripts and managing experiments
- **Technology**: FastAPI web server with Jinja2 templates
- **Deployment**: Runs on user's local machine or cloud server
- **Features**: 
  - Script upload interface with queue position display
  - Experiment monitoring with real-time status updates
  - Queue status and admin controls
  - User session management
  - Result download
  - SSH communication with bioreactor-hub

### 2. Bioreactor Hub (`bioreactor-hub/`)
- **Purpose**: Middleware service for experiment queuing and orchestration
- **Technology**: FastAPI server with persistent queue management
- **Deployment**: Runs on intermediate server (bioreactor_hub machine)
- **Features**:
  - Persistent experiment queue with JSON file storage
  - FIFO queue management (one experiment at a time)
  - User session tracking and limits (max 5 experiments per user)
  - Admin controls (cancel, pause, resume, reorder)
  - Background worker for automatic experiment execution
  - Hardware abstraction API
  - SSH communication with bioreactor-node

### 3. Bioreactor Node (`bioreactor-node/`)
- **Purpose**: Direct hardware interface running on bioreactor hardware
- **Technology**: FastAPI server with hardware drivers
- **Deployment**: Runs directly on bioreactor hardware (bioreactor_node machine)
- **Features**:
  - Hardware abstraction REST API
  - SSH server for secure communication
  - Hardware drivers and interfaces
  - Status monitoring
  - Container management for experiment execution

## Queue System

The system implements a sophisticated queue management system:

### Features
- **Persistent Queue**: Experiments survive system restarts
- **FIFO Ordering**: First-in, first-out experiment execution
- **User Limits**: Maximum 5 experiments per user session
- **Real-time Status**: Live updates on queue position and wait times
- **Admin Controls**: Cancel, pause, resume, and reorder experiments
- **Automatic Execution**: Background worker processes queue automatically

### Queue States
- **Queued**: Waiting in line for execution
- **Running**: Currently executing on bioreactor hardware
- **Completed**: Successfully finished
- **Failed**: Execution failed with error
- **Cancelled**: User/admin cancelled the experiment
- **Paused**: Temporarily paused (can be resumed)

## Communication Flow

```
User Upload → Web Server → Bioreactor Hub (Queue) → Background Worker → Bioreactor Node
User Script → Container → REST API → Bioreactor Hub → SSH → Bioreactor Node
```

## Web Interface

### Pages
1. **Home** (`/`): Overview and navigation
2. **Upload** (`/upload`): Submit new experiments with queue position display
3. **My Experiments** (`/my-experiments`): View all user experiments
4. **Queue Status** (`/queue`): Admin interface for queue management
5. **Experiment Status** (`/experiment/{id}`): Individual experiment details

### Features
- **Session Management**: Automatic user session tracking
- **Real-time Updates**: Auto-refresh every 30 seconds
- **Admin Controls**: Available to all users (configurable)
- **Responsive Design**: Works on desktop and mobile devices

## Deployment

### For Local Development
```bash
# Clone the entire repository
git clone <your-repo-url>
cd bioreactor_website

# Create data directories for persistence
mkdir -p bioreactor-hub/data
mkdir -p bioreactor-node/data

# Run all components locally using Docker Compose
docker-compose up
```

### For Production Deployment

#### Deploy Web Server Only
```bash
# Clone and deploy web-server component
git clone <your-repo-url>
cd bioreactor_website/web-server
# Follow web-server deployment instructions
```

#### Deploy Bioreactor Hub Only
```bash
# Clone and deploy bioreactor-hub component
git clone <your-repo-url>
cd bioreactor_website/bioreactor-hub
# Follow bioreactor-hub deployment instructions
```

#### Deploy Bioreactor Node Only
```bash
# Clone and deploy bioreactor-node component
git clone <your-repo-url>
cd bioreactor_website/bioreactor-node
# Follow bioreactor-node deployment instructions
```

## API Endpoints

### Bioreactor Hub API
- `POST /api/experiments/start` - Queue new experiment
- `GET /api/experiments/{id}/status` - Get experiment status
- `GET /api/queue/status` - Get queue status
- `GET /api/experiments/user` - Get user's experiments
- `POST /api/experiments/{id}/cancel` - Cancel experiment
- `POST /api/experiments/{id}/pause` - Pause experiment
- `POST /api/experiments/{id}/resume` - Resume experiment
- `POST /api/experiments/{id}/reorder` - Reorder experiment

### Web Server API
- `GET /` - Home page
- `GET /upload` - Upload form
- `POST /upload` - Submit experiment
- `GET /queue` - Queue status page
- `GET /my-experiments` - User experiments page
- `GET /experiment/{id}` - Experiment status page

## Security Features

- **Container Isolation**: Each user experiment runs in its own Docker container
- **Hardware Abstraction**: Users can only access hardware through controlled APIs
- **Package Restrictions**: Only whitelisted Python packages allowed in user containers
- **Network Isolation**: Containers have limited network access
- **Resource Limits**: CPU, memory, and disk usage limits per experiment
- **Queue Limits**: Maximum experiments per user to prevent abuse

## Testing

Run the test script to verify the queue system:

```bash
python test_queue_system.py
```

This will test:
- Queue status checking
- Experiment submission
- Status monitoring
- Admin controls (pause, resume, cancel)
- User experiment listing

## Development

Each component can be developed independently. See individual README files in each directory for specific development instructions.

## License

[Add your license information here]
