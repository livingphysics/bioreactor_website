"""
Hardware configuration for the bioreactor API.

Edit INIT_COMPONENTS to enable/disable hardware components.
Only enabled components get API endpoints.
"""
import sys
from pathlib import Path
from typing import Optional, Union

# Add bioreactor_v3 to path
BIOREACTOR_V3_PATH = Path(__file__).parent / 'bioreactor_v3' / 'src'
sys.path.insert(0, str(BIOREACTOR_V3_PATH))

class Config:
    """
    Hardware configuration.

    Override default settings here for your specific hardware.
    Only include settings that differ from defaults.
    """

    # ========================================================================
    # Component Initialization Control
    # ========================================================================
    # Set to True to initialize, False to skip.
    # Only initialized components get API endpoints.
    INIT_COMPONENTS = {
        'i2c': True,
        'temp_sensor': True,
        'peltier_driver': True,
        'stirrer': True,
        'led': True,
        'ring_light': True,
        'optical_density': True,
        'eyespy_adc': True,
        'co2_sensor': True,
        'o2_sensor': True,
        'ambient_temp': True,
        'peltier_current': True,
        'pumps': False,
        'relays': False,
    }

    # Peltier Driver (Raspberry Pi 5 GPIO via lgpio)
    PELTIER_PWM_PIN: int = 21
    PELTIER_DIR_PIN: int = 20
    PELTIER_PWM_FREQ: int = 1000
    # This rig's peltier is wired opposite the driver convention: verified 2026-07-03
    # that 'heat' at 70% cooled the bath ~1.9 °C in 75s. Inverting the DIR pin makes
    # heat/cool (and PID/schedules) physically correct for everyone.
    PELTIER_DIR_INVERTED: bool = True

    # Data retention for API-generated run CSVs in bioreactor_v3/src/bioreactor_data/.
    # Old run files are pruned (oldest first) on startup and before each run so the
    # SD card can't fill up; runs are refused if free space drops below the floor.
    # Only touches files this API creates (*_peltier_schedule.csv / *_pid_run.csv).
    DATA_RETENTION_MAX_MB: int = 1000   # cap total size of API run files
    DATA_RETENTION_KEEP: int = 10       # always keep at least this many newest runs
    DATA_MIN_FREE_MB: int = 500         # refuse to start a run if free disk below this

    # Pi camera (rpicam-still snapshots via GET /api/camera/snapshot).
    # rotation/hflip/vflip/zoom are defaults; requests can override via query params.
    CAMERA_ENABLED: bool = True
    CAMERA_WIDTH: int = 1280
    CAMERA_HEIGHT: int = 720
    CAMERA_ROTATION: int = 0     # 0 or 180
    CAMERA_HFLIP: bool = False
    CAMERA_VFLIP: bool = False
    CAMERA_ZOOM: float = 1.0     # 1.0 = full frame; 2.0 = 2x centered digital zoom
    CAMERA_QUALITY: int = 90

    # Rolling sensor-history buffer (for the monitor's long-range plot).
    # Samples temp/ambient/current/OD continuously (independent of runs). Served at
    # GET /api/history from an in-memory HISTORY_WINDOW_H window; every sample is also
    # appended to a daily archive file history/YYYY-MM-DD.jsonl and kept for
    # HISTORY_RETENTION_DAYS (files older than that are pruned). Append-only, so a
    # year of data costs ~0.5 GB and only a few MB/day of SD writes.
    HISTORY_ENABLED: bool = True
    HISTORY_INTERVAL_S: int = 10        # sample period
    HISTORY_WINDOW_H: int = 24          # hours kept in memory + served to the frontend
    HISTORY_RETENTION_DAYS: int = 365   # days of daily archive files kept on disk

    # Stirrer (PWM only)
    STIRRER_PWM_PIN: int = 12
    STIRRER_PWM_FREQ: int = 1000
    STIRRER_DEFAULT_DUTY: float = 30.0

    # LED (PWM control)
    LED_PWM_PIN: int = 25
    LED_PWM_FREQ: int = 500

    # Ring Light (Neopixel via pi5neo SPI)
    RING_LIGHT_SPI_DEVICE: str = '/dev/spidev0.0'
    RING_LIGHT_COUNT: int = 32
    RING_LIGHT_SPI_SPEED: int = 800

    # Optical Density (ADS1115 ADC)
    OD_ADC_CHANNELS: dict[str, str] = {
        '135': 'A0',
        'Ref': 'A1',
        '90': 'A2',
    }

    # IR-gated OD sampling (od_sampler.py). Every reading pulses the IR LED:
    #   LED on (OD_LED_POWER) -> settle (OD_SETTLE_S) -> read -> pause (OD_POST_READ_S) -> LED off.
    # Runs continuously (24/7) so the 24h OD history fills even when nobody's watching.
    # When both OD and eyespy sources are present they interleave (one source per
    # pulse), so each samples at half the pulse rate. The whole gated measurement is
    # held under HARDWARE_LOCK (so nothing toggles the LED mid-read), which means the
    # lock is occupied for ~settle+read+post each pulse. The 1 Hz heater safety loop
    # shares that lock, so keep the settle short to bound lock occupancy: an IR LED +
    # ADS1115 stabilise in <20 ms, so 0.25 s is ample and keeps occupancy well under
    # the pulse period. led_power/enabled are also settable live via POST /api/od/sampling.
    OD_SAMPLE_ENABLED: bool = True
    OD_LED_POWER: float = 10.0       # IR LED % during each gated reading (frontend: 1–20%)
    OD_SETTLE_S: float = 0.25        # settle after LED-on before reading (bounds lock occupancy)
    OD_POST_READ_S: float = 0.05     # brief pause after reading before LED-off
    OD_PULSE_PERIOD_S: float = 1.0   # LED-pulse period (single source 1 Hz; both 0.5 Hz each)

    # Eyespy ADC (ADS1114, single-channel per board)
    EYESPY_ADC: dict = {
        'eyespy1': {
            'i2c_address': 0x49,
            'i2c_bus': 1,
            'gain': 1.0,
        },
        'eyespy2': {
            'i2c_address': 0x4a,
            'i2c_bus': 1,
            'gain': 1.0,
        },
    }

    # CO2 Sensor
    CO2_SENSOR_TYPE: str = 'atlas_i2c'
    CO2_SENSOR_I2C_ADDRESS: Optional[int] = None
    CO2_SENSOR_I2C_BUS: int = 1

    # O2 Sensor (Atlas Scientific)
    O2_SENSOR_I2C_ADDRESS: Optional[int] = None
    O2_SENSOR_I2C_BUS: int = 1

    # Ambient Temperature Sensor (NXP PCT2075, I2C) — reads in °C
    AMBIENT_TEMP_I2C_ADDRESS: int = 0x37
    AMBIENT_TEMP_I2C_BUS: int = 1

    # Peltier Current Sensor (TI INA228 current monitor, I2C) — reads in Amps.
    # Current is derived from the shunt voltage: I = V_shunt / INA228_SHUNT_OHMS,
    # so INA228_SHUNT_OHMS must be CALIBRATED to your board's shunt resistor.
    PELTIER_CURRENT_I2C_ADDRESS: int = 0x40
    PELTIER_CURRENT_I2C_BUS: int = 1
    INA228_SHUNT_OHMS: float = 0.015  # Adafruit INA228 breakout default; calibrate per board

    # Pumps (ticUSB protocol)
    PUMPS: dict[str, dict[str, Union[str, int, float]]] = {
        'inflow': {
            'serial': '00473498',
            'step_mode': 3,
            'current_limit': 32,
            'direction': 'forward',
            'steps_per_ml': 10000000.0,
        },
        'outflow': {
            'serial': '00473497',
            'step_mode': 3,
            'current_limit': 32,
            'direction': 'forward',
            'steps_per_ml': 10000000.0,
        },
    }
