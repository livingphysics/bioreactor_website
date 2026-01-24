"""Dynamic v3 API endpoints - auto-generated from available components"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'bioreactor_v3', 'src'))

from src.adapters.registry import get_available_adapters

def create_v3_router(bioreactor) -> APIRouter:
    """Auto-generate v3 API endpoints from available components

    Args:
        bioreactor: Bioreactor instance from bioreactor_v3

    Returns:
        FastAPI router with dynamic endpoints for each component
    """
    router = APIRouter(prefix="/api/v3", tags=["hardware_v3"])

    adapters = get_available_adapters(bioreactor)

    @router.get("/capabilities")
    async def get_capabilities():
        """Discover available hardware components and their capabilities"""
        return {name: adapter.get_capabilities() for name, adapter in adapters.items()}

    # Dynamically create endpoints for each component
    for comp_name, adapter in adapters.items():

        # Control endpoint (if actuator)
        if adapter.get_control_schema() is not None:
            control_schema = adapter.get_control_schema()
            state_schema = adapter.get_state_schema()

            async def control_endpoint(
                request: control_schema,  # type: ignore
                _adapter=adapter
            ):
                result = await _adapter.control(request)
                if result.get("status") == "error":
                    raise HTTPException(status_code=500, detail=result.get("message"))
                return result

            router.add_api_route(
                f"/{comp_name}/control",
                control_endpoint,
                methods=["POST"],
                response_model=state_schema,  # type: ignore
                summary=f"Control {comp_name}",
                description=f"Control the {comp_name} component"
            )

        # State reading endpoint (all components have this)
        state_schema = adapter.get_state_schema()

        async def state_endpoint(_adapter=adapter):
            return await _adapter.read_state()

        router.add_api_route(
            f"/{comp_name}/state",
            state_endpoint,
            methods=["GET"],
            response_model=state_schema,  # type: ignore
            summary=f"Read {comp_name} state",
            description=f"Read current state of {comp_name}"
        )

    return router
