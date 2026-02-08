"""
Live data streaming for bioreactor dashboard
Provides Server-Sent Events (SSE) for real-time sensor data
"""
import asyncio
import json
import os
import csv
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, Any
import httpx


def load_dashboard_config() -> Dict[str, Any]:
    """Load dashboard settings from config file"""
    config_path = Path("/app/config/dashboard_settings.json")
    default_config = {
        "display_components": {
            "co2_sensor": True,
            "temperature": False,
            "photodiodes": False,
            "peltier_current": False
        },
        "update_interval": 2.0,
        "csv_file_path": "/app/data/bioreactor_data.csv"
    }

    try:
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading dashboard config: {e}")

    return default_config


def save_dashboard_config(config: Dict[str, Any]) -> bool:
    """Save dashboard settings to config file"""
    config_path = Path("/app/config/dashboard_settings.json")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving dashboard config: {e}")
        return False


async def get_running_experiment_id(hub_api_url: str) -> str:
    """Get the ID of the currently running experiment, or None if none running"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{hub_api_url}/api/queue/status")
            if response.status_code == 200:
                data = response.json()
                # Look through queue for running experiment
                for exp in data.get("queue", []):
                    if exp.get("status") == "running":
                        return exp.get("experiment_id")
    except Exception as e:
        print(f"Error checking experiment status: {e}")
    return None


def read_latest_csv_data(csv_path: str) -> Dict[str, Any]:
    """Read the latest line from the bioreactor CSV file"""
    try:
        if not Path(csv_path).exists():
            return {"status": "error", "error": "CSV file not found", "source": "csv"}

        with open(csv_path, 'r') as f:
            # Read all lines and get the last one
            lines = f.readlines()
            if len(lines) < 2:  # Need header + at least one data line
                return {"status": "error", "error": "No data in CSV", "source": "csv"}

            # Parse CSV
            reader = csv.DictReader(lines)
            last_row = None
            for row in reader:
                last_row = row

            if not last_row:
                return {"status": "error", "error": "Could not parse CSV", "source": "csv"}

            # Helper function to safely parse numeric values
            def safe_float(value):
                if value and value.strip():
                    try:
                        return float(value)
                    except ValueError:
                        return None
                return None

            # Helper function to safely parse JSON arrays
            def safe_json_parse(value):
                if value and value.strip():
                    try:
                        return json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        return None
                return None

            # Convert to our format - support both v2 and v3 CSV formats
            return {
                "timestamp": last_row.get("timestamp", datetime.now().isoformat()),
                "co2_ppm": safe_float(last_row.get("co2_ppm")),
                # V3 format
                "temperature": safe_float(last_row.get("temperature")),  # Single reading
                "od_voltages": safe_json_parse(last_row.get("od_voltages")),
                "eyespy_voltages": safe_json_parse(last_row.get("eyespy_voltages")),
                "stirrer_duty": safe_float(last_row.get("stirrer_duty")),
                "peltier_duty": safe_float(last_row.get("peltier_duty")),
                "peltier_direction": last_row.get("peltier_direction"),
                "ring_light_r": safe_float(last_row.get("ring_light_r")),
                "ring_light_g": safe_float(last_row.get("ring_light_g")),
                "ring_light_b": safe_float(last_row.get("ring_light_b")),
                # V2 format (backward compatibility)
                "photodiodes": safe_json_parse(last_row.get("photodiodes")),
                "vial_temperatures": safe_json_parse(last_row.get("vial_temperatures")),
                "io_temperatures": safe_json_parse(last_row.get("io_temperatures")),
                "peltier_current": safe_float(last_row.get("peltier_current")),
                "temperatures": safe_json_parse(last_row.get("temperatures")),  # V2/V3 list format
                "status": "success",
                "source": "csv"
            }
    except Exception as e:
        print(f"Error reading CSV data: {e}")
        return {"status": "error", "error": str(e), "source": "csv"}


async def get_sensor_data_from_hardware(config: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch sensor data directly from hardware based on config"""
    node_url = os.getenv("BIOREACTOR_NODE_API_URL", "http://bioreactor-node:9000")
    display = config.get("display_components", {})

    result = {
        "timestamp": datetime.now().isoformat(),
        "status": "success",
        "source": "hardware"
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Get CO2 if enabled
            if display.get("co2_sensor", False):
                try:
                    response = await client.get(f"{node_url}/api/v3/co2_sensor/state")
                    if response.status_code == 200:
                        co2_data = response.json()
                        result["co2_ppm"] = co2_data.get("co2_ppm", None)
                except:
                    result["co2_ppm"] = None

            # Get all sensors if any other component is enabled
            if display.get("temperature") or display.get("photodiodes") or display.get("peltier_current"):
                try:
                    response = await client.get(f"{node_url}/api/sensors/all")
                    if response.status_code == 200:
                        data = response.json()
                        if display.get("temperature"):
                            result["temperature"] = data.get("temperature", None)
                        if display.get("photodiodes"):
                            result["photodiodes"] = data.get("photodiodes", [])
                        if display.get("peltier_current"):
                            result["peltier_current"] = data.get("peltier_current", None)
                except:
                    pass

    except Exception as e:
        print(f"Error fetching sensor data: {e}")
        result["status"] = "error"
        result["error"] = str(e)

    return result


async def get_sensor_data(hub_api_url: str) -> dict:
    """Fetch current sensor data - from CSV if experiment running, else from hardware

    Args:
        hub_api_url: URL of the bioreactor hub API

    Returns:
        Dictionary with sensor readings
    """
    config = load_dashboard_config()

    # Check if experiment is running and get its ID
    running_experiment_id = await get_running_experiment_id(hub_api_url)

    if running_experiment_id:
        # Read from the running experiment's CSV file
        csv_path = f"/app/node_data/experiments/{running_experiment_id}/output/experiment_data.csv"
        csv_data = read_latest_csv_data(csv_path)

        # If CSV read succeeded, return it
        if csv_data.get("status") == "success":
            return csv_data

        # If CSV read failed, fall back to hardware
        print(f"CSV read failed for experiment {running_experiment_id}: {csv_data.get('error')}, falling back to hardware")
        return await get_sensor_data_from_hardware(config)
    else:
        # No experiment running - query hardware directly based on config
        return await get_sensor_data_from_hardware(config)


async def stream_sensor_data(hub_api_url: str) -> AsyncGenerator[str, None]:
    """
    Stream sensor data using Server-Sent Events (SSE)

    Args:
        hub_api_url: URL of the bioreactor hub API

    Yields:
        SSE-formatted strings with sensor data
    """
    config = load_dashboard_config()
    interval = config.get("update_interval", 2.0)

    while True:
        try:
            data = await get_sensor_data(hub_api_url)

            # Format as SSE
            json_data = json.dumps(data)
            yield f"data: {json_data}\n\n"

            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            # Client disconnected
            break
        except Exception as e:
            print(f"Error in stream_sensor_data: {e}")
            await asyncio.sleep(interval)
