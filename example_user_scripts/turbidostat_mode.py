import logging
import time
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

from src.config import Config as cfg
from src.utils import pid_controller, measure_and_write_sensor_data, ExtendedKalmanFilter, turbidostat_od_controller

# --- Turbidostat orchestration function ---
def turbidostat_mode(
    bioreactor,
    pump_name,
    target_od,
    temp_setpoint,
    sampling_interval=60.0,
    process_noise_biomass=1e-5,
    process_noise_growth_rate=1e-6,
    measurement_noise=0.05,
    control_gain=0.5,
    flow_rate_max_ml_s=0.1,
    od_sensor_channel=0,
    dead_zone=0.02,
    initial_flow_rate_ml_s=0.01,
    culture_volume_ml=10.0,
    ekf_initial_growth_rate=0.2,
    kp=10.0,
    ki=1.0,
    kd=0.0,
    dt=1.0,
    temp_freq=1.0,
    temp_duration=True,
    log_plot_freq=60.0,
    log_plot_duration=True,
    duration_seconds=None
):
    """
    Run the reactor in turbidostat mode:
    - OD control with EKF and flow adjustment.
    - PID temperature control (as a separate job).
    - Sensor measurement/logging/plotting (as a separate job).
    All jobs run in their own threads using bioreactor.run(jobs).
    """
    import numpy as np
    import time
    import matplotlib.pyplot as plt

    # --- EKF state ---
    # Initial OD measurement
    def measure_od(bio):
        with bio.led_context():
            readings = bio.get_photodiodes()
            od_reading = readings[od_sensor_channel]
            od = 2.0 * od_reading - 0.1  # Example calibration
            return max(0.0, od)

    initial_od = measure_od(bioreactor)
    ekf = ExtendedKalmanFilter(
        initial_biomass=initial_od,
        initial_growth_rate=ekf_initial_growth_rate,
        process_noise_biomass=process_noise_biomass,
        process_noise_growth_rate=process_noise_growth_rate,
        measurement_noise=measurement_noise,
        dt=sampling_interval
    )
    state = {
        'flow_rate_ml_s': initial_flow_rate_ml_s,
        'dilution_rate_h': (initial_flow_rate_ml_s * 3600) / culture_volume_ml
    }
    def dilution_job(bio, elapsed=None):
        turbidostat_od_controller(
            bio,
            ekf,
            measure_od,
            pump_name,
            target_od,
            control_gain,
            flow_rate_max_ml_s,
            dead_zone,
            culture_volume_ml,
            state,
            elapsed
        )

    # --- Temperature job ---
    def temp_job(bio, elapsed=None):
        pid_controller(bio, setpoint=temp_setpoint, kp=kp, ki=ki, kd=kd, dt=dt)

    # --- Sensor/logging/plotting job ---
    times = []
    od_vals = []
    est_ods = []
    est_growths = []
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    plt.ion()
    def log_plot_job(bio, elapsed=None):
        # Log sensor data
        measure_and_write_sensor_data(bio, elapsed)
        # Plot OD and growth rate history
        od = measure_od(bio)
        est_od, est_growth = ekf.get_state()
        times.append(elapsed)
        od_vals.append(od)
        est_ods.append(est_od)
        est_growths.append(est_growth)
        # Plot
        ax1.clear()
        ax2.clear()
        ax1.plot(np.array(times)/3600, od_vals, 'b-', label='OD Measured')
        ax1.plot(np.array(times)/3600, est_ods, 'r--', label='OD Estimated')
        ax1.axhline(y=target_od, color='g', linestyle='-', label='Target OD')
        ax1.set_ylabel('Optical Density (OD)')
        ax1.set_title('Turbidostat OD Control')
        ax1.legend()
        ax1.grid(True)
        ax2.plot(np.array(times)/3600, est_growths, 'g-', label='Estimated Growth Rate')
        ax2.set_xlabel('Time (hours)')
        ax2.set_ylabel('Growth Rate (h^-1)')
        ax2.legend()
        ax2.grid(True)
        plt.tight_layout()
        plt.pause(0.01)

    # --- Jobs list ---
    jobs = [
        (dilution_job, sampling_interval, duration_seconds if duration_seconds else True),
        (temp_job, temp_freq, temp_duration),
        (log_plot_job, log_plot_freq, log_plot_duration)
    ]
    bioreactor.run(jobs)

# --- Main block ---
if __name__ == "__main__":
    from bioreactor import Bioreactor
    import logging
    import time
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    DURATION = 8 * 3600  # 8 hours
    try:
        with Bioreactor() as bioreactor:
            turbidostat_mode(
                bioreactor=bioreactor,
                pump_name='tube_1_in',
                target_od=0.6,
                temp_setpoint=37.0,
                sampling_interval=60.0,
                duration_seconds=DURATION
            )
            start = time.time()
            while time.time() - start < DURATION:
                time.sleep(1)
            plt.close('all')
    except Exception as e:
        logging.error(f"Error: {e}")
