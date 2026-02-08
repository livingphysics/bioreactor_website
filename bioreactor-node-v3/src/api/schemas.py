"""Pydantic schemas for API requests/responses"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    hardware_mode: str
    hardware_available: bool
    initialized_components: Dict[str, bool]

class CapabilitiesResponse(BaseModel):
    """Component capabilities response"""
    components: Dict[str, Dict[str, Any]]

class ErrorResponse(BaseModel):
    """Standard error response"""
    status: str = "error"
    message: str
    details: Optional[Dict[str, Any]] = None
