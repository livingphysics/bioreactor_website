from src.utils import balanced_flow, pid_controller
from src.bioreactor import Bioreactor
import logging
import time
import matplotlib.pyplot as plt

# Orchestration functions

def chemostat_mode(
    bioreactor,
    pump_name,
    flow_rate_ml_s,
    temp_setpoint,
    kp=10.0,
    ki=1.0,
    kd=0.0,
    dt=1.0,
    flow_freq=1.0,
    flow_duration=3600.0,
    temp_freq=1.0,
    temp_duration=3600.0,
    elapsed=None
):
    """
    Run the reactor in chemostat mode:
    - Balanced flow on the specified pump.
    - PID temperature control.
    Both run in their own threads using bioreactor.run().
    Args:
        bioreactor: Bioreactor instance
        pump_name: e.g. 'tube_1_in' or 'tube_1_out'
        flow_rate_ml_s: Inflow/outflow rate (ml/sec)
        temp_setpoint: Desired temperature (°C)
        kp, ki, kd: PID gains
        dt: Time step for PID loop (s)
        flow_freq: Frequency (s) for balanced_flow
        flow_duration: Duration (s) for balanced_flow
        temp_freq: Frequency (s) for pid_controller
        temp_duration: Duration (s) for pid_controller
    """
    logger = getattr(bioreactor, 'logger', None)

    def flow_job(bio):
        balanced_flow(bio, pump_name, flow_rate_ml_s)
    def temp_job(bio):
        pid_controller(bio, setpoint=temp_setpoint, kp=kp, ki=ki, kd=kd, dt=dt)
    jobs = [
        (flow_job, flow_freq, flow_duration),
        (temp_job, temp_freq, temp_duration)
    ]
    
    if logger:
        logger.info(f"Starting chemostat mode: flow_job every {flow_freq}s for {flow_duration}s, temp_job every {temp_freq}s for {temp_duration}s.")
        
    bioreactor.run(jobs)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    DURATION = 8 * 3600  # 8 hours
    try:
        with Bioreactor() as bioreactor:
            chemostat_mode(
                bioreactor=bioreactor,
                pump_name='tube_1_in',
                flow_rate_ml_s=0.01,
                temp_setpoint=37.0,
                kp=10.0,
                ki=1.0,
                kd=0.0,
                dt=1.0,
                flow_freq=1.0,
                flow_duration=DURATION,
                temp_freq=1.0,
                temp_duration=DURATION
            )
            start = time.time()
            while time.time() - start < DURATION:
                time.sleep(1)
            plt.close('all')
    except Exception as e:
        logging.error(f"Error: {e}")
