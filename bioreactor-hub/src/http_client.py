"""HTTP client for bioreactor-node v3 communication"""
import logging
import requests
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BioreactorNodeHTTPClient:
    """HTTP client for bioreactor-node v3 communication

    Replaces SSH-based communication with direct HTTP API calls.
    Provides the same interface as the SSH client for drop-in compatibility.
    """

    def __init__(self, base_url: str = "http://bioreactor-node:9000"):
        """Initialize HTTP client

        Args:
            base_url: Base URL of bioreactor-node API
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 60

    def test_connection(self) -> bool:
        """Test connection to bioreactor-node

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.session.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def forward_experiment(self, experiment_id: str, script_content: str) -> Dict[str, Any]:
        """Start experiment and poll until completion

        This method provides the same interface as the SSH client's forward_experiment
        for drop-in compatibility with the existing hub code.

        Args:
            experiment_id: Unique experiment identifier
            script_content: User's Python script content

        Returns:
            Dict with keys:
                - success: bool - True if experiment completed successfully
                - exit_code: int - Container exit code (0 = success)
                - error: str - Error message if failed
        """
        try:
            # Start experiment
            logger.info(f"Starting experiment {experiment_id} via HTTP")
            response = self.session.post(
                f"{self.base_url}/api/experiments/start",
                json={
                    "script_content": script_content,
                    "experiment_id": experiment_id
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Experiment {experiment_id} started successfully")

            # Poll for completion
            poll_interval = 2  # seconds
            max_polls = 1800  # 1 hour max (1800 * 2 seconds)
            polls = 0

            while polls < max_polls:
                try:
                    status_resp = self.session.get(
                        f"{self.base_url}/api/experiments/{experiment_id}/status",
                        timeout=10
                    )
                    status_resp.raise_for_status()
                    data = status_resp.json()

                    exp_data = data.get("experiment", {})
                    exp_status = exp_data.get("status")

                    logger.debug(f"Experiment {experiment_id} status: {exp_status}")

                    # Check if experiment completed
                    if exp_status in ["completed", "failed", "stopped"]:
                        exit_code = exp_data.get("exit_code", 1)
                        error = exp_data.get("error_message")

                        if exp_status == "completed" and exit_code == 0:
                            logger.info(f"Experiment {experiment_id} completed successfully")
                            return {
                                "success": True,
                                "exit_code": exit_code,
                                "error": None
                            }
                        else:
                            logger.error(f"Experiment {experiment_id} failed: {error}")
                            return {
                                "success": False,
                                "exit_code": exit_code,
                                "error": error or f"Experiment {exp_status}"
                            }

                    # Continue polling
                    time.sleep(poll_interval)
                    polls += 1

                except requests.exceptions.Timeout:
                    logger.warning(f"Status check timeout for experiment {experiment_id}, retrying...")
                    time.sleep(poll_interval)
                    polls += 1
                    continue

            # Timeout reached
            logger.error(f"Experiment {experiment_id} timed out after {max_polls * poll_interval} seconds")
            return {
                "success": False,
                "exit_code": 1,
                "error": f"Experiment timed out after {max_polls * poll_interval} seconds"
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed for experiment {experiment_id}: {e}")
            return {
                "success": False,
                "exit_code": 1,
                "error": f"HTTP request failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error forwarding experiment {experiment_id}: {e}")
            return {
                "success": False,
                "exit_code": 1,
                "error": f"Unexpected error: {str(e)}"
            }

    def get_experiment_status(self, experiment_id: str) -> Dict[str, Any]:
        """Get experiment status

        Args:
            experiment_id: Experiment identifier

        Returns:
            Dict with experiment status information
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/experiments/{experiment_id}/status",
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get status for experiment {experiment_id}: {e}")
            return {
                "status": "error",
                "experiment": None,
                "error": str(e)
            }

    def get_experiment_logs(self, experiment_id: str, tail: int = 100) -> Dict[str, Any]:
        """Get experiment logs

        Args:
            experiment_id: Experiment identifier
            tail: Number of log lines to retrieve

        Returns:
            Dict with logs
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/experiments/{experiment_id}/logs",
                params={"tail": tail},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get logs for experiment {experiment_id}: {e}")
            return {
                "status": "error",
                "logs": f"Error retrieving logs: {e}"
            }

    def stop_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """Stop running experiment

        Args:
            experiment_id: Experiment identifier

        Returns:
            Dict with status
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/experiments/{experiment_id}/stop",
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to stop experiment {experiment_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to stop experiment: {e}"
            }
