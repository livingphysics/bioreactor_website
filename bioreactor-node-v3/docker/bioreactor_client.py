"""
Bioreactor Client Library for User Experiments (v3)
Provides a safe interface to bioreactor hardware through the node API.
"""

import os
import time
import logging
import requests
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BioreactorClient:
    """Client for communicating with bioreactor hardware through node v3 API"""

    def __init__(self, api_url: Optional[str] = None):
        """Initialize bioreactor client"""
        self.api_url = api_url or os.getenv("BIOREACTOR_NODE_API_URL", "http://localhost:9000")
        self.session = requests.Session()
        self.session.timeout = 30

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to node API"""
        url = f"{self.api_url}{endpoint}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise ConnectionError(f"Failed to communicate with bioreactor node: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get hardware status"""
        return self._make_request("GET", "/api/status")

    def get_sensors(self) -> Dict[str, Any]:
        """Get all sensor data"""
        return self._make_request("GET", "/api/sensors/all")

    def get_photodiodes(self) -> Dict[str, Any]:
        """Get photodiode readings"""
        return self._make_request("GET", "/api/sensors/photodiodes")

    def get_temperature(self) -> Dict[str, Any]:
        """Get temperature readings"""
        return self._make_request("GET", "/api/sensors/temperature")

    def get_co2(self) -> Dict[str, Any]:
        """Get CO2 sensor reading (v3 endpoint)"""
        return self._make_request("GET", "/api/v3/co2_sensor/state")

    def control_led(self, state: bool) -> Dict[str, Any]:
        """Control LED"""
        return self._make_request("POST", "/api/led", {"state": state})

    def control_ring_light(self, color: List[int], pixel: Optional[int] = None) -> Dict[str, Any]:
        """Control ring light"""
        data = {"color": color}
        if pixel is not None:
            data["pixel"] = pixel
        return self._make_request("POST", "/api/ring-light", data)

    def control_peltier(self, power: int, direction: str) -> Dict[str, Any]:
        """Control peltier (temperature control)"""
        return self._make_request("POST", "/api/peltier", {
            "power": power,
            "direction": direction
        })

    def control_pump(self, name: str, velocity: float) -> Dict[str, Any]:
        """Control pump flow rate"""
        return self._make_request("POST", "/api/pump", {
            "name": name,
            "velocity": velocity
        })

    def control_stirrer(self, duty_cycle: int) -> Dict[str, Any]:
        """Control stirrer speed"""
        return self._make_request("POST", "/api/stirrer", {
            "duty_cycle": duty_cycle
        })

class Bioreactor:
    """Bioreactor class that provides the standard interface for user scripts"""

    def __init__(self):
        """Initialize bioreactor interface"""
        self.client = BioreactorClient()
        self.logger = logger
        self._temp_integral = 0.0
        self._temp_last_error = 0.0

        # Test connection
        try:
            status = self.client.get_status()
            logger.info("Bioreactor interface initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize bioreactor interface: {e}")
            raise

    def change_led(self, state: bool) -> None:
        """Change LED state"""
        result = self.client.control_led(state)
        if result.get("status") != "success":
            raise RuntimeError(f"LED control failed: {result}")

    def change_ring_light(self, color: List[int], pixel: Optional[int] = None) -> None:
        """Change ring light color"""
        result = self.client.control_ring_light(color, pixel)
        if result.get("status") != "success":
            raise RuntimeError(f"Ring light control failed: {result}")

    def change_peltier(self, power: int, forward: bool) -> None:
        """Change peltier power and direction (v3 API)"""
        direction = "heat" if forward else "cool"
        try:
            result = self.client._make_request("POST", "/api/v3/peltier_driver/control", {
                "duty_cycle": float(power),
                "direction": direction
            })
            if result.get("status") != "success":
                raise RuntimeError(f"Peltier control failed: {result}")
        except Exception as e:
            raise RuntimeError(f"Peltier control failed: {e}")

    def change_pump(self, pump_name: str, ml_per_sec: float) -> None:
        """Change pump flow rate (v3 API)"""
        try:
            result = self.client._make_request("POST", "/api/v3/pumps/control", {
                "pump_name": pump_name,
                "velocity": ml_per_sec
            })
            if result.get("status") != "success":
                raise RuntimeError(f"Pump control failed: {result}")
        except Exception as e:
            raise RuntimeError(f"Pump control failed: {e}")

    def change_stirrer(self, duty_cycle: int) -> None:
        """Change stirrer speed (v3 API)"""
        try:
            result = self.client._make_request("POST", "/api/v3/stirrer/control", {
                "duty_cycle": float(duty_cycle)
            })
            if result.get("status") != "success":
                raise RuntimeError(f"Stirrer control failed: {result}")
        except Exception as e:
            raise RuntimeError(f"Stirrer control failed: {e}")

    def get_peltier_state(self) -> Dict[str, Any]:
        """Get current peltier state (v3 API)"""
        try:
            result = self.client._make_request("GET", "/api/v3/peltier_driver/state")
            if result.get("status") == "success":
                return {
                    "duty_cycle": result.get("duty_cycle", 0.0),
                    "direction": result.get("direction", "forward"),
                    "active": result.get("active", False)
                }
            return {"duty_cycle": 0.0, "direction": "forward", "active": False}
        except Exception:
            return {"duty_cycle": 0.0, "direction": "forward", "active": False}

    def get_stirrer_state(self) -> Dict[str, Any]:
        """Get current stirrer state (v3 API)"""
        try:
            result = self.client._make_request("GET", "/api/v3/stirrer/state")
            if result.get("status") == "success":
                return {
                    "duty_cycle": result.get("duty_cycle", 0.0),
                    "active": result.get("active", False)
                }
            return {"duty_cycle": 0.0, "active": False}
        except Exception:
            return {"duty_cycle": 0.0, "active": False}

    def change_ring_light(self, red: int, green: int, blue: int, pixel: Optional[int] = None) -> None:
        """Change ring light color (v3 API)"""
        try:
            data = {"red": red, "green": green, "blue": blue}
            if pixel is not None:
                data["pixel_index"] = pixel
            result = self.client._make_request("POST", "/api/v3/ring_light/control", data)
            if result.get("status") != "success":
                raise RuntimeError(f"Ring light control failed: {result}")
        except Exception as e:
            raise RuntimeError(f"Ring light control failed: {e}")

    def get_ring_light_state(self) -> Dict[str, Any]:
        """Get current ring light state (v3 API)"""
        try:
            result = self.client._make_request("GET", "/api/v3/ring_light/state")
            if result.get("status") == "success":
                return {
                    "red": result.get("red", 0),
                    "green": result.get("green", 0),
                    "blue": result.get("blue", 0),
                    "active": result.get("active", False)
                }
            return {"red": 0, "green": 0, "blue": 0, "active": False}
        except Exception:
            return {"red": 0, "green": 0, "blue": 0, "active": False}

    def get_photodiodes(self) -> List[float]:
        """Get photodiode readings"""
        result = self.client.get_photodiodes()
        if result.get("status") == "success":
            data = result.get("data", {})
            # Return list of photodiode values
            readings = []
            for key in sorted(data.keys()):
                if key.startswith('photodiode_'):
                    readings.append(data[key])
            return readings
        else:
            raise RuntimeError(f"Failed to get photodiode readings: {result}")

    def get_vial_temp(self) -> List[float]:
        """Get vial temperature readings"""
        result = self.client.get_temperature()
        if result.get("status") == "success":
            data = result.get("data", {})
            # Return list of vial temperature values
            temps = []
            for key in sorted(data.keys()):
                if key.startswith('vial_temp_'):
                    temps.append(data[key])
            return temps
        else:
            raise RuntimeError(f"Failed to get temperature readings: {result}")

    def get_io_temp(self) -> List[float]:
        """Get IO temperature readings"""
        result = self.client.get_temperature()
        if result.get("status") == "success":
            data = result.get("data", {})
            # Return list of IO temperature values
            temps = []
            for key in sorted(data.keys()):
                if key.startswith('io_temp_'):
                    temps.append(data[key])
            return temps
        else:
            raise RuntimeError(f"Failed to get temperature readings: {result}")

    def get_peltier_curr(self) -> float:
        """Get peltier current reading"""
        result = self.client.get_sensors()
        if result.get("status") == "success":
            data = result.get("data", {})
            return data.get("peltier_current", 0.0)
        else:
            raise RuntimeError(f"Failed to get current reading: {result}")

    def get_co2(self) -> float:
        """Get CO2 concentration in ppm"""
        result = self.client.get_co2()
        if result.get("status") == "success":
            return result.get("co2_ppm", 0.0)
        else:
            raise RuntimeError(f"Failed to get CO2 reading: {result}")

    def get_od_voltages(self) -> List[float]:
        """Get optical density voltages (v3 API)"""
        try:
            result = self.client._make_request("GET", "/api/v3/optical_density/state")
            if result.get("status") == "success":
                return result.get("voltages", [])
            return []
        except Exception:
            return []

    def get_eyespy_voltages(self) -> List[float]:
        """Get eyespy ADC voltages (v3 API)"""
        try:
            result = self.client._make_request("GET", "/api/v3/eyespy_adc/state")
            if result.get("status") == "success":
                return result.get("voltages", [])
            return []
        except Exception:
            return []

    def get_temperature(self) -> float:
        """Get temperature sensor reading (v3 API - single sensor)"""
        try:
            result = self.client._make_request("GET", "/api/v3/temp_sensor/state")
            if result.get("status") == "success":
                temps = result.get("temperatures", [])
                # Return first temperature sensor reading, or None if not available
                return temps[0] if temps and len(temps) > 0 else None
            return None
        except Exception:
            return None

    def run(self, jobs: List) -> None:
        """Run jobs (placeholder for compatibility)"""
        logger.info("Bioreactor.run() called - this is a placeholder for compatibility")
        # In the containerized environment, jobs are handled differently
        # This maintains compatibility with existing scripts

    def stop_all(self) -> None:
        """Stop all operations"""
        logger.info("Stopping all bioreactor operations")
        try:
            self.change_peltier(0, True)
            self.change_stirrer(0)
            # Stop all pumps (you may need to adjust pump names)
            for pump in ["media_in", "media_out", "waste_in", "waste_out"]:
                try:
                    self.change_pump(pump, 0.0)
                except Exception:
                    pass  # Pump may not exist
        except Exception as e:
            logger.error(f"Error stopping operations: {e}")

    def finish(self) -> None:
        """Finish bioreactor operations"""
        logger.info("Finishing bioreactor operations")
        self.stop_all()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit"""
        self.finish()

# Utility functions
def measure_and_write_sensor_data(bioreactor: Bioreactor, elapsed: Optional[float] = None) -> Dict[str, Any]:
    """Get sensor measurements and return as dictionary (v3 API)

    Args:
        bioreactor: Bioreactor instance
        elapsed: Optional elapsed time in seconds. If None, uses actual timestamp.

    Returns:
        Dictionary with sensor readings including timestamp

    Gracefully handles unavailable sensors by setting them to None.

    V3 sensors:
        - co2_ppm: CO2 concentration in ppm
        - temperature: Single temperature reading in Celsius
        - od_voltages: List of optical density voltages
        - eyespy_voltages: List of eyespy ADC voltages
    """
    from datetime import datetime

    # Record exact measurement time
    timestamp = datetime.now().isoformat()

    # Try to get CO2 reading
    try:
        co2_ppm = bioreactor.get_co2()
    except Exception:
        co2_ppm = None

    # Try to get temperature sensor (v3 API - single reading)
    try:
        temperature = bioreactor.get_temperature()
    except Exception:
        temperature = None

    # Try to get optical density voltages (v3 API)
    try:
        od_voltages = bioreactor.get_od_voltages()
    except Exception:
        od_voltages = None

    # Try to get eyespy ADC voltages (v3 API)
    try:
        eyespy_voltages = bioreactor.get_eyespy_voltages()
    except Exception:
        eyespy_voltages = None

    data_row = {
        'timestamp': timestamp,
        'co2_ppm': co2_ppm,
        'temperature': temperature,
        'od_voltages': od_voltages,
        'eyespy_voltages': eyespy_voltages
    }

    # Include elapsed time if provided (for backward compatibility)
    if elapsed is not None:
        data_row['elapsed'] = elapsed

    bioreactor.logger.info(f"Measured sensor data: {data_row}")
    return data_row

def measure_all_data(bioreactor: Bioreactor, include_controls: bool = True, elapsed: Optional[float] = None) -> Dict[str, Any]:
    """Get all sensor measurements and control states (v3 API)

    Args:
        bioreactor: Bioreactor instance
        include_controls: If True, includes current control states (stirrer, peltier)
        elapsed: Optional elapsed time in seconds. If None, uses actual timestamp.

    Returns:
        Dictionary with complete system state including sensors and controls

    V3 data includes:
        - timestamp: ISO format timestamp
        - co2_ppm: CO2 concentration
        - temperature: Single temperature reading in Celsius
        - od_voltages: Optical density voltages
        - eyespy_voltages: Eyespy ADC voltages
        - stirrer_duty: Current stirrer duty cycle (if include_controls=True)
        - peltier_duty: Current peltier duty cycle (if include_controls=True)
        - peltier_direction: Current peltier direction (if include_controls=True)
        - ring_light_r: Ring light red value (if include_controls=True)
        - ring_light_g: Ring light green value (if include_controls=True)
        - ring_light_b: Ring light blue value (if include_controls=True)
    """
    # Get sensor data
    data = measure_and_write_sensor_data(bioreactor, elapsed)

    # Optionally include control states
    if include_controls:
        try:
            stirrer_state = bioreactor.get_stirrer_state()
            data['stirrer_duty'] = stirrer_state.get('duty_cycle', 0.0)
        except Exception:
            data['stirrer_duty'] = None

        try:
            peltier_state = bioreactor.get_peltier_state()
            data['peltier_duty'] = peltier_state.get('duty_cycle', 0.0)
            data['peltier_direction'] = peltier_state.get('direction', 'forward')
        except Exception:
            data['peltier_duty'] = None
            data['peltier_direction'] = None

        try:
            ring_light_state = bioreactor.get_ring_light_state()
            data['ring_light_r'] = ring_light_state.get('red', 0)
            data['ring_light_g'] = ring_light_state.get('green', 0)
            data['ring_light_b'] = ring_light_state.get('blue', 0)
        except Exception:
            data['ring_light_r'] = None
            data['ring_light_g'] = None
            data['ring_light_b'] = None

    return data

def write_data_to_csv(data: Dict[str, Any], filename: str = "experiment_data.csv", output_dir: Optional[str] = None):
    """Write sensor data to CSV file in the output directory

    Args:
        data: Dictionary containing sensor readings (e.g., from measure_and_write_sensor_data)
        filename: Name of the CSV file (default: "experiment_data.csv")
        output_dir: Output directory path (default: uses OUTPUT_DIR environment variable)

    Example:
        bioreactor = Bioreactor()
        elapsed = 0
        while elapsed < 60:
            data = measure_and_write_sensor_data(bioreactor, elapsed)
            write_data_to_csv(data)  # Appends to experiment_data.csv
            time.sleep(5)
            elapsed += 5
    """
    import csv
    import os
    from pathlib import Path

    # Use OUTPUT_DIR environment variable if not specified
    if output_dir is None:
        output_dir = os.getenv("OUTPUT_DIR", "/app/output")

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    filepath = os.path.join(output_dir, filename)
    file_exists = os.path.isfile(filepath)

    # Determine fieldnames from data keys
    fieldnames = list(data.keys())

    try:
        with open(filepath, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Write header if file is new
            if not file_exists:
                writer.writeheader()

            # Write data row
            writer.writerow(data)

    except Exception as e:
        logger.error(f"Failed to write data to CSV: {e}")

def pid_controller(bioreactor: Bioreactor, setpoint: float, current_temp: Optional[float] = None,
                  kp: float = 10.0, ki: float = 1.0, kd: float = 0.0, dt: float = 1.0, elapsed: Optional[float] = None):
    """PID loop to maintain reactor temperature at setpoint"""
    if current_temp is None:
        temps = bioreactor.get_vial_temp()
        current_temp = temps[0] if temps else 0.0

    error = setpoint - current_temp
    bioreactor._temp_integral += error * dt
    derivative = (error - bioreactor._temp_last_error) / dt if dt > 0 else 0.0
    output = kp * error + ki * bioreactor._temp_integral + kd * derivative

    duty = max(0, min(100, int(abs(output))))
    forward = (output >= 0)
    bioreactor.change_peltier(duty, forward)
    bioreactor._temp_last_error = error

    bioreactor.logger.info(f"PID controller: setpoint={setpoint}, current_temp={current_temp}, output={output}, duty={duty}, forward={forward}")

def balanced_flow(bioreactor: Bioreactor, pump_name: str, ml_per_sec: float, elapsed: Optional[float] = None):
    """For a given pump, set its flow and automatically set the converse pump to the same rate"""
    if pump_name.endswith('_in'):
        converse = pump_name[:-3] + '_out'
    elif pump_name.endswith('_out'):
        converse = pump_name[:-4] + '_in'
    else:
        raise ValueError("Pump name must end with '_in' or '_out'")

    bioreactor.change_pump(pump_name, ml_per_sec)
    bioreactor.change_pump(converse, ml_per_sec)

    bioreactor.logger.info(f"Balanced flow: {pump_name} and {converse} set to {ml_per_sec} ml/sec")

def ring_light_cycle(bioreactor: Bioreactor, color: tuple = (50, 50, 50),
                    on_time: float = 60.0, off_time: float = 60.0, elapsed: Optional[float] = None):
    """Cycle ring light on and off in a loop

    Args:
        bioreactor: Bioreactor instance
        color: RGB tuple (r, g, b) with values 0-255 (default: (50, 50, 50))
        on_time: Duration in seconds to keep ring light on (default: 60.0)
        off_time: Duration in seconds to keep ring light off (default: 60.0)
        elapsed: Elapsed time since start (s)

    Example:
        bioreactor = Bioreactor()
        elapsed = 0
        while elapsed < 300:  # 5 minutes
            ring_light_cycle(bioreactor, color=(100, 100, 100), on_time=30, off_time=30, elapsed=elapsed)
            time.sleep(1)
            elapsed += 1
    """
    import time

    # Initialize state if not present - start with ring light ON
    if not hasattr(bioreactor, '_ring_light_state'):
        bioreactor._ring_light_state = 'on'
        bioreactor._ring_light_last_switch_time = None
        # Turn ring light on immediately on first call
        bioreactor.set_ring_light(color)
        bioreactor.logger.info(f"Ring light cycle started: turned ON with color={color}, will stay on for {on_time}s")

    # Get current time
    if elapsed is None:
        if not hasattr(bioreactor, '_ring_light_start_time'):
            bioreactor._ring_light_start_time = time.time()
        current_time = time.time() - bioreactor._ring_light_start_time
    else:
        current_time = elapsed

    # Initialize last switch time on first call
    if bioreactor._ring_light_last_switch_time is None:
        bioreactor._ring_light_last_switch_time = current_time

    # Calculate time since last state switch
    time_since_switch = current_time - bioreactor._ring_light_last_switch_time

    # Determine if we need to switch state
    if bioreactor._ring_light_state == 'on':
        # Currently on - check if we should turn off
        if time_since_switch >= on_time:
            bioreactor.set_ring_light((0, 0, 0))  # Turn off
            bioreactor._ring_light_state = 'off'
            bioreactor._ring_light_last_switch_time = current_time
            bioreactor.logger.info(f"Ring light turned OFF, will stay off for {off_time}s")
    else:  # state == 'off'
        # Currently off - check if we should turn on
        if time_since_switch >= off_time:
            bioreactor.set_ring_light(color)
            bioreactor._ring_light_state = 'on'
            bioreactor._ring_light_last_switch_time = current_time
            bioreactor.logger.info(f"Ring light turned ON: color={color}, will stay on for {on_time}s")

# Config class for compatibility
class Config:
    """Configuration placeholder for compatibility with existing scripts"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
