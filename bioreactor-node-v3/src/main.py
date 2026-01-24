"""
Bioreactor Node v3 - Main FastAPI Application
Modular hardware control system with dynamic API generation and v2 compatibility
"""
import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add bioreactor_v3 to path
BIOREACTOR_V3_PATH = Path(__file__).parent.parent / 'bioreactor_v3' / 'src'
sys.path.insert(0, str(BIOREACTOR_V3_PATH))

from bioreactor import Bioreactor
from config_default import Config

from src.config import NodeConfig
from src.api.endpoints import create_v3_router
from src.api.legacy import create_legacy_router
from src.api.experiments import create_experiments_router, initialize_docker

# Configure logging
logging.basicConfig(
    level=getattr(logging, NodeConfig.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
bioreactor_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    global bioreactor_instance

    logger.info("=" * 60)
    logger.info("Starting Bioreactor Node v3")
    logger.info("=" * 60)

    # Initialize Docker client
    if initialize_docker():
        logger.info("✓ Docker client initialized")
    else:
        logger.warning("✗ Docker client initialization failed")

    # Initialize hardware based on mode
    hardware_mode = NodeConfig.HARDWARE_MODE
    logger.info(f"Hardware mode: {hardware_mode}")

    if hardware_mode == "real":
        try:
            # Load hardware config from bioreactor_v3
            config = Config()

            # Override paths for containerized environment
            config.LOG_FILE = str(Path(NodeConfig.LOG_DIR) / 'bioreactor.log')
            config.DATA_OUT_FILE = str(Path(NodeConfig.DATA_DIR) / 'bioreactor_data.csv')

            # Create directories
            Path(NodeConfig.LOG_DIR).mkdir(parents=True, exist_ok=True)
            Path(NodeConfig.DATA_DIR).mkdir(parents=True, exist_ok=True)
            Path(NodeConfig.EXPERIMENTS_DIR).mkdir(parents=True, exist_ok=True)

            logger.info("Initializing hardware...")
            bioreactor_instance = Bioreactor(config)

            # Log initialization status
            if bioreactor_instance._initialized:
                logger.info("✓ Hardware initialized successfully")
                logger.info("Initialized components:")
                for comp, status in bioreactor_instance._initialized.items():
                    symbol = "✓" if status else "✗"
                    logger.info(f"  {symbol} {comp}")
            else:
                logger.warning("Hardware initialization completed with no components")

        except Exception as e:
            logger.error(f"✗ Hardware initialization failed: {e}", exc_info=True)
            bioreactor_instance = None

    else:
        logger.info("Simulation mode - hardware initialization skipped")
        bioreactor_instance = None

    logger.info("=" * 60)
    logger.info("Bioreactor Node v3 ready")
    logger.info("=" * 60)

    yield

    # Cleanup
    logger.info("Shutting down Bioreactor Node v3...")
    if bioreactor_instance:
        try:
            logger.info("Cleaning up hardware...")
            bioreactor_instance.finish()
            logger.info("✓ Hardware cleanup complete")
        except Exception as e:
            logger.error(f"✗ Cleanup error: {e}", exc_info=True)

    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Bioreactor Node v3",
    description="Modular hardware control system with plugin-based architecture and v2 compatibility",
    version="3.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "service": "Bioreactor Node v3",
        "version": "3.0.0",
        "status": "operational",
        "docs": "/docs",
        "health": "/health"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    initialized_components = {}
    if bioreactor_instance:
        initialized_components = {
            comp: status
            for comp, status in bioreactor_instance._initialized.items()
        }

    return {
        "status": "healthy",
        "version": "3.0.0",
        "hardware_mode": NodeConfig.HARDWARE_MODE,
        "hardware_available": bioreactor_instance is not None,
        "initialized_components": initialized_components,
        "component_count": len(initialized_components)
    }

# Include routers
logger.info("Registering API routers...")

# v3 dynamic endpoints (only if hardware is available)
if bioreactor_instance:
    v3_router = create_v3_router(bioreactor_instance)
    app.include_router(v3_router)
    logger.info("✓ v3 dynamic endpoints registered")

    legacy_router = create_legacy_router(bioreactor_instance)
    app.include_router(legacy_router)
    logger.info("✓ v2 legacy endpoints registered")
else:
    logger.warning("✗ Hardware endpoints not registered (no hardware available)")

# Experiment management (always available)
experiments_router = create_experiments_router()
app.include_router(experiments_router)
logger.info("✓ Experiment management endpoints registered")


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting server on {NodeConfig.HOST}:{NodeConfig.PORT}")
    uvicorn.run(
        app,
        host=NodeConfig.HOST,
        port=NodeConfig.PORT,
        log_level=NodeConfig.LOG_LEVEL.lower()
    )
