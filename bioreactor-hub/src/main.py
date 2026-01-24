"""
Bioreactor Hub - Experiment Forwarding Service
Forwards experiment scripts to bioreactor-node for execution.
"""

import os
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
import uvicorn

from .ssh_client import BioreactorNodeClient
from .http_client import BioreactorNodeHTTPClient
from .queue_manager import QueueManager, ExperimentStatus
import threading
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
node_client: Optional[BioreactorNodeHTTPClient] = None
queue_manager: Optional[QueueManager] = None
queue_worker_thread: Optional[threading.Thread] = None
queue_worker_stop = threading.Event()

# Pydantic models
class ExperimentRequest(BaseModel):
    script_content: str
    config: Optional[Dict[str, Any]] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    global node_client, queue_manager, queue_worker_thread, queue_worker_stop
    
    # Startup
    logger.info("Starting Bioreactor Hub...")

    # Initialize HTTP client for bioreactor-node v3
    node_api_url = os.getenv("BIOREACTOR_NODE_API_URL", "http://bioreactor-node:9000")
    logger.info(f"Connecting to bioreactor-node at {node_api_url}")

    node_client = BioreactorNodeHTTPClient(node_api_url)

    # Test HTTP connection
    if node_client.test_connection():
        logger.info("✓ HTTP connection to bioreactor-node v3 established")
    else:
        logger.warning("✗ Failed to connect to bioreactor-node - experiments will fail")
    
    queue_manager = QueueManager(data_dir="/app/data")
    queue_worker_stop.clear()
    queue_worker_thread = threading.Thread(target=queue_worker, daemon=True)
    queue_worker_thread.start()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Bioreactor Hub...")
    queue_worker_stop.set()
    if queue_worker_thread:
        queue_worker_thread.join(timeout=5)
    logger.info("Shutdown complete")

# Background worker to process the experiment queue
def queue_worker():
    while not queue_worker_stop.is_set():
        try:
            # Only one experiment can run at a time
            running = any(
                exp.status == ExperimentStatus.RUNNING
                for exp in queue_manager.experiments.values()
            )
            if not running:
                next_exp = queue_manager.get_next_experiment()
                if next_exp:
                    # Mark as running
                    queue_manager.start_experiment(next_exp.experiment_id)
                    # Forward to node
                    result = node_client.forward_experiment(next_exp.experiment_id, next_exp.script_content)
                    exit_code = result.get("exit_code", 1 if not result.get("success") else 0)
                    error_message = result.get("error")
                    queue_manager.complete_experiment(next_exp.experiment_id, exit_code, error_message)
            time.sleep(2)
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
            time.sleep(5)

# Create FastAPI app
app = FastAPI(
    title="Bioreactor Hub API",
    description="Experiment forwarding service to bioreactor-node",
    version="1.0.0",
    lifespan=lifespan
)

# Dependency functions
def get_node_client() -> BioreactorNodeClient:
    if node_client is None:
        raise HTTPException(status_code=503, detail="Node client not available")
    return node_client

def get_queue_manager() -> QueueManager:
    if queue_manager is None:
        raise HTTPException(status_code=503, detail="Queue manager not available")
    return queue_manager

# Helper to get user session id (for now, from header or generate random)
def get_user_session_id(x_session_id: Optional[str] = Header(None)) -> str:
    if x_session_id:
        return x_session_id
    # Generate a random session id for now
    return str(uuid.uuid4())

# Experiment management endpoints
@app.post("/api/experiments/start")
async def queue_experiment(
    request: ExperimentRequest,
    queue: QueueManager = Depends(get_queue_manager),
    user_session_id: str = Depends(get_user_session_id)
):
    """Queue a new experiment"""
    result = queue.add_experiment(user_session_id, request.script_content)
    if result["success"]:
        return {
            "experiment_id": result["experiment_id"],
            "status": "queued",
            "queue_position": result["queue_position"],
            "message": "Experiment added to queue"
        }
    else:
        raise HTTPException(status_code=400, detail=result["error"])

@app.get("/api/experiments/{experiment_id}/status")
async def get_experiment_status(
    experiment_id: str,
    queue: QueueManager = Depends(get_queue_manager)
):
    status = queue.get_experiment_status(experiment_id)
    if status:
        return {"experiment": status}
    else:
        raise HTTPException(status_code=404, detail="Experiment not found")

@app.get("/api/queue/status")
async def get_queue_status(
    queue: QueueManager = Depends(get_queue_manager)
):
    return queue.get_queue_status()

@app.get("/api/experiments/user")
async def get_user_experiments(
    queue: QueueManager = Depends(get_queue_manager),
    user_session_id: str = Depends(get_user_session_id)
):
    return {"experiments": queue.get_user_experiments(user_session_id)}

@app.post("/api/experiments/{experiment_id}/cancel")
async def cancel_experiment(
    experiment_id: str,
    queue: QueueManager = Depends(get_queue_manager)
):
    success = queue.cancel_experiment(experiment_id)
    if success:
        return {"success": True, "message": f"Experiment {experiment_id} cancelled."}
    else:
        raise HTTPException(status_code=400, detail="Unable to cancel experiment (may not be queued)")

@app.post("/api/experiments/{experiment_id}/pause")
async def pause_experiment(
    experiment_id: str,
    queue: QueueManager = Depends(get_queue_manager)
):
    success = queue.pause_experiment(experiment_id)
    if success:
        return {"success": True, "message": f"Experiment {experiment_id} paused."}
    else:
        raise HTTPException(status_code=400, detail="Unable to pause experiment (may not be queued)")

@app.post("/api/experiments/{experiment_id}/resume")
async def resume_experiment(
    experiment_id: str,
    queue: QueueManager = Depends(get_queue_manager)
):
    success = queue.resume_experiment(experiment_id)
    if success:
        return {"success": True, "message": f"Experiment {experiment_id} resumed."}
    else:
        raise HTTPException(status_code=400, detail="Unable to resume experiment (may not be paused)")

@app.post("/api/experiments/{experiment_id}/reorder")
async def reorder_experiment(
    experiment_id: str,
    new_position: int,
    queue: QueueManager = Depends(get_queue_manager)
):
    success = queue.reorder_experiment(experiment_id, new_position)
    if success:
        return {"success": True, "message": f"Experiment {experiment_id} moved to position {new_position}."}
    else:
        raise HTTPException(status_code=400, detail="Unable to reorder experiment (invalid id or position)")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    ) 
