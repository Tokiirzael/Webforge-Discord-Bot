import subprocess
import os
from config import KOBOLDCPP_LAUNCH_SCRIPT_PATH, KOBOLDCPP_PROFILE_PATH

_kobold_process = None

def start_koboldcpp():
    """Starts the KoboldCpp executable as a subprocess."""
    global _kobold_process
    if is_koboldcpp_running():
        print("KoboldCpp process is already running.")
        return True

    if not KOBOLDCPP_LAUNCH_SCRIPT_PATH or not os.path.exists(KOBOLDCPP_LAUNCH_SCRIPT_PATH):
        print(f"Error: KoboldCpp executable not found or not configured in config.py.")
        print(f"Attempted path: '{KOBOLDCPP_LAUNCH_SCRIPT_PATH}'")
        return False

    print(f"Starting KoboldCpp from: {KOBOLDCPP_LAUNCH_SCRIPT_PATH}")
    try:
        command = [KOBOLDCPP_LAUNCH_SCRIPT_PATH, "--config", KOBOLDCPP_PROFILE_PATH]
        script_dir = os.path.dirname(KOBOLDCPP_LAUNCH_SCRIPT_PATH)

        if os.name == 'nt': # Windows
            _kobold_process = subprocess.Popen(
                command,
                cwd=script_dir,
                shell=True
            )
        else: # Linux, macOS
            _kobold_process = subprocess.Popen(
                command,
                preexec_fn=os.setsid,
                cwd=script_dir
            )

        print(f"KoboldCpp process started with PID: {_kobold_process.pid}")
        return True
    except Exception as e:
        print(f"Failed to start KoboldCpp process: {e}")
        _kobold_process = None
        return False

def stop_koboldcpp():
    """Stops the running KoboldCpp subprocess."""
    global _kobold_process
    if not is_koboldcpp_running():
        print("KoboldCpp process is not running.")
        return True

    print(f"Stopping KoboldCpp process with PID: {_kobold_process.pid}")
    try:
        if os.name == 'nt':
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(_kobold_process.pid)])
        else:
            import signal
            os.killpg(os.getpgid(_kobold_process.pid), signal.SIGTERM)

        _kobold_process.wait(timeout=10)
        print("KoboldCpp process stopped.")
    except Exception as e:
        print(f"An error occurred while stopping the KoboldCpp process: {e}")
    finally:
        _kobold_process = None
    return True

def is_koboldcpp_running():
    """Checks if the KoboldCpp process is currently running."""
    global _kobold_process
    if _kobold_process is None:
        return False

    return _kobold_process.poll() is None
