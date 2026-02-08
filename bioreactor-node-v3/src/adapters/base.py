"""Base adapter class for hardware components"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel

class ComponentAdapter(ABC):
    """Base class for hardware component adapters

    Each adapter wraps a hardware component from bioreactor_v3 and exposes it via REST API.
    Adapters provide metadata for auto-generating endpoints and schemas for validation.
    """

    def __init__(self, bioreactor, component_name: str):
        """Initialize adapter

        Args:
            bioreactor: Bioreactor instance from bioreactor_v3
            component_name: Component key in bioreactor._initialized dict
        """
        self.bioreactor = bioreactor
        self.component_name = component_name
        self.initialized = bioreactor.is_component_initialized(component_name) if bioreactor else False

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Return component capabilities metadata for API discovery

        Returns:
            Dict with keys like: type, control_type, parameters, ranges, etc.
        """
        pass

    @abstractmethod
    def get_control_schema(self) -> Optional[type[BaseModel]]:
        """Return Pydantic schema for control requests

        Returns:
            Pydantic BaseModel class for POST request validation, or None if sensor-only
        """
        pass

    @abstractmethod
    def get_state_schema(self) -> type[BaseModel]:
        """Return Pydantic schema for state/sensor responses

        Returns:
            Pydantic BaseModel class for response validation
        """
        pass

    @abstractmethod
    async def control(self, request: BaseModel) -> Dict[str, Any]:
        """Execute control operation (for actuators)

        Args:
            request: Validated Pydantic model with control parameters

        Returns:
            Dict with status and result data
        """
        pass

    @abstractmethod
    async def read_state(self) -> Dict[str, Any]:
        """Read current state/sensor data

        Returns:
            Dict with current state/sensor readings
        """
        pass
