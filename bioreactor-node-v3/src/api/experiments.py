"""Experiment management endpoints for Docker container execution"""
import os
import logging
import uuid
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import docker

logger = logging.getLogger(__name__)

# Global instances
docker_client: Optional[docker.DockerClient] = None
containers: Dict[str, Dict] = {}

# Pydantic models
class ExperimentRequest(BaseModel):
    """Request to start an experiment"""
    script_content: str
    experiment_id: Optional[str] = None

class ExperimentStatus(BaseModel):
    """Experiment status response"""
    experiment_id: str
    status: str  # starting, running, completed, failed, stopped
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None


def initialize_docker():
    """Initialize Docker client"""
    global docker_client
    try:
        docker_client = docker.from_env()
        logger.info("Docker client initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Docker client: {e}")
        docker_client = None
        return False


def create_experiments_router() -> APIRouter:
    """Create experiments API router

    Returns:
        FastAPI router with experiment management endpoints
    """
    router = APIRouter(prefix="/api/experiments", tags=["experiments"])

    @router.post("/start")
    async def start_experiment(request: ExperimentRequest, background_tasks: BackgroundTasks):
        """Start a new experiment"""
        if not docker_client:
            raise HTTPException(status_code=503, detail="Docker not available")

        # Generate experiment ID if not provided
        experiment_id = request.experiment_id or str(uuid.uuid4())

        # Create experiment directory
        data_dir = Path("/app/data")
        experiment_dir = data_dir / "experiments" / experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)

        # Save user script
        script_file = experiment_dir / "user_script.py"
        with open(script_file, 'w') as f:
            f.write(request.script_content)

        # Create output directory
        output_dir = experiment_dir / "output"
        output_dir.mkdir(exist_ok=True)

        try:
            # Start container in background
            background_tasks.add_task(run_experiment_container, experiment_id, script_file, output_dir)

            # Store experiment info
            containers[experiment_id] = {
                "status": "starting",
                "start_time": datetime.now(),
                "script_file": str(script_file),
                "output_dir": str(output_dir),
                "container": None
            }

            logger.info(f"Started experiment: {experiment_id}")
            return {
                "status": "success",
                "experiment_id": experiment_id,
                "message": "Experiment started"
            }

        except Exception as e:
            logger.error(f"Failed to start experiment {experiment_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{experiment_id}/status")
    async def get_experiment_status(experiment_id: str):
        """Get experiment status"""
        if experiment_id not in containers:
            raise HTTPException(status_code=404, detail="Experiment not found")

        container_info = containers[experiment_id]

        # Check if container is still running
        if container_info.get("container"):
            try:
                container_info["container"].reload()
                if container_info["status"] == "running":
                    # Check if container has exited
                    container_data = docker_client.api.inspect_container(container_info["container"].id)
                    if container_data['State']['Status'] == 'exited':
                        container_info["status"] = "completed"
                        container_info["end_time"] = datetime.now()
                        container_info["exit_code"] = container_data['State']['ExitCode']
            except Exception as e:
                logger.error(f"Error checking container status: {e}")

        return {
            "status": "success",
            "experiment": {
                "experiment_id": experiment_id,
                "status": container_info["status"],
                "start_time": container_info["start_time"].isoformat() if container_info.get("start_time") else None,
                "end_time": container_info["end_time"].isoformat() if container_info.get("end_time") else None,
                "exit_code": container_info.get("exit_code"),
                "error_message": container_info.get("error_message")
            }
        }

    @router.get("/{experiment_id}/logs")
    async def get_experiment_logs(experiment_id: str, tail: int = 100):
        """Get experiment logs"""
        if experiment_id not in containers:
            raise HTTPException(status_code=404, detail="Experiment not found")

        container_info = containers[experiment_id]
        container = container_info.get("container")

        if container is None:
            return {"status": "success", "logs": "No container logs available"}

        try:
            logs = container.logs(tail=tail, timestamps=True)
            return {"status": "success", "logs": logs.decode('utf-8')}
        except Exception as e:
            logger.error(f"Failed to get logs for experiment {experiment_id}: {e}")
            return {"status": "error", "logs": f"Error retrieving logs: {e}"}

    @router.get("/{experiment_id}/results")
    async def get_experiment_results(experiment_id: str):
        """Get experiment results"""
        if experiment_id not in containers:
            raise HTTPException(status_code=404, detail="Experiment not found")

        container_info = containers[experiment_id]
        output_dir = Path(container_info["output_dir"])

        results = {
            "experiment_id": experiment_id,
            "output_files": [],
            "exit_code": container_info.get("exit_code")
        }

        # Check for output files
        if output_dir.exists():
            for file_path in output_dir.rglob("*"):
                if file_path.is_file():
                    results["output_files"].append(str(file_path.relative_to(output_dir)))

        return {"status": "success", "results": results}

    @router.get("/{experiment_id}/download")
    async def download_experiment_results(experiment_id: str):
        """Download experiment results as ZIP file"""
        if experiment_id not in containers:
            raise HTTPException(status_code=404, detail="Experiment not found")

        container_info = containers[experiment_id]
        output_dir = Path(container_info["output_dir"])
        zip_path = output_dir.parent / "results.zip"

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add output files
                if output_dir.exists():
                    for file_path in output_dir.rglob("*"):
                        if file_path.is_file():
                            arcname = file_path.relative_to(output_dir)
                            zipf.write(file_path, arcname)

                # Add script file
                script_file = Path(container_info["script_file"])
                if script_file.exists():
                    zipf.write(script_file, "user_script.py")

            return FileResponse(
                path=str(zip_path),
                filename=f"experiment_{experiment_id}_results.zip",
                media_type="application/zip"
            )
        except Exception as e:
            logger.error(f"Failed to create results ZIP for experiment {experiment_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/{experiment_id}/stop")
    async def stop_experiment(experiment_id: str):
        """Stop experiment"""
        if experiment_id not in containers:
            raise HTTPException(status_code=404, detail="Experiment not found")

        container_info = containers[experiment_id]
        container = container_info.get("container")

        if container is None:
            return {"status": "success", "message": "No running container to stop"}

        try:
            container.stop(timeout=30)
            container_info["status"] = "stopped"
            container_info["end_time"] = datetime.now()

            logger.info(f"Stopped experiment: {experiment_id}")
            return {"status": "success", "message": "Experiment stopped"}
        except Exception as e:
            logger.error(f"Failed to stop experiment {experiment_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/{experiment_id}")
    async def delete_experiment(experiment_id: str):
        """Delete experiment"""
        if experiment_id not in containers:
            raise HTTPException(status_code=404, detail="Experiment not found")

        container_info = containers[experiment_id]

        # Stop container if running
        container = container_info.get("container")
        if container:
            try:
                container.stop(timeout=10)
            except Exception as e:
                logger.error(f"Failed to stop container for experiment {experiment_id}: {e}")

        # Remove experiment data
        try:
            import shutil
            experiment_dir = Path(container_info["output_dir"]).parent
            if experiment_dir.exists():
                shutil.rmtree(experiment_dir)
        except Exception as e:
            logger.error(f"Failed to remove experiment directory for {experiment_id}: {e}")

        # Remove from containers dict
        del containers[experiment_id]

        logger.info(f"Deleted experiment: {experiment_id}")
        return {"status": "success", "message": "Experiment deleted"}

    @router.get("")
    async def list_experiments():
        """List all experiments"""
        experiment_list = []
        for experiment_id, container_info in containers.items():
            experiment_list.append({
                "experiment_id": experiment_id,
                "status": container_info["status"],
                "start_time": container_info["start_time"].isoformat() if container_info.get("start_time") else None,
                "end_time": container_info["end_time"].isoformat() if container_info.get("end_time") else None
            })

        return {"status": "success", "experiments": experiment_list}

    return router


async def run_experiment_container(experiment_id: str, script_file: Path, output_dir: Path):
    """Run experiment in Docker container

    Args:
        experiment_id: Unique experiment identifier
        script_file: Path to user script
        output_dir: Path to output directory
    """
    try:
        # Update status
        containers[experiment_id]["status"] = "running"

        # Run container
        container = docker_client.containers.run(
            image="bioreactor-user-experiment:latest",
            command=["python", "/app/user_script.py"],
            volumes={
                str(output_dir): {
                    'bind': '/app/output',
                    'mode': 'rw'
                },
                str(script_file): {
                    'bind': '/app/user_script.py',
                    'mode': 'ro'
                }
            },
            environment={
                "BIOREACTOR_NODE_API_URL": "http://host.docker.internal:9000",
                "EXPERIMENT_ID": experiment_id
            },
            detach=True,
            mem_limit="512m",
            cpu_period=100000,
            cpu_quota=100000,  # 1 CPU core
            network_mode="host",  # Use host network for direct access
            name=f"experiment-{experiment_id}",
            remove=True
        )

        # Store container reference
        containers[experiment_id]["container"] = container

        # Wait for container to complete
        result = container.wait()

        # Update status
        containers[experiment_id]["status"] = "completed" if result["StatusCode"] == 0 else "failed"
        containers[experiment_id]["end_time"] = datetime.now()
        containers[experiment_id]["exit_code"] = result["StatusCode"]

        logger.info(f"Experiment {experiment_id} completed with exit code {result['StatusCode']}")

    except Exception as e:
        logger.error(f"Error running experiment {experiment_id}: {e}")
        containers[experiment_id]["status"] = "failed"
        containers[experiment_id]["end_time"] = datetime.now()
        containers[experiment_id]["error_message"] = str(e)
