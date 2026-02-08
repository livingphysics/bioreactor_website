"""Node-specific configuration"""
import os

class NodeConfig:
    """Configuration for bioreactor node v3"""

    # API settings
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "9000"))

    # Hardware mode
    HARDWARE_MODE = os.getenv("HARDWARE_MODE", "simulation")  # "real" or "simulation"

    # Docker settings
    DOCKER_SOCKET = "/var/run/docker.sock"
    USER_CONTAINER_IMAGE = "bioreactor-user-experiment:latest"
    CONTAINER_MEMORY_LIMIT = "512m"
    CONTAINER_CPU_LIMIT = 1.0

    # Data directories
    DATA_DIR = os.getenv("DATA_DIR", "/app/data")
    EXPERIMENTS_DIR = os.path.join(DATA_DIR, "experiments")
    LOG_DIR = os.getenv("LOG_DIR", "/app/logs")

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
