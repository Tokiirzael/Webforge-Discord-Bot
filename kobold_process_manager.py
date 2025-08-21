import subprocess
import os
from config import KOBOLDCPP_LAUNCH_SCRIPT_PATH, KOBOLDCPP_PROFILES

_kobold_process = None

def start_koboldcpp(model_name: str = "default"):
    """Starts the KoboldCpp executable as a subprocess using a specific model profile."""
    global _kobold_process
    if is_koboldcpp_running():
        print("KoboldCpp process is already running.")
        return True, None # Return success, no model name needed

    # --- Validate Paths and Profile ---
    if not KOBOLDCPP_LAUNCH_SCRIPT_PATH or not os.path.exists(KOBOLDCPP_LAUNCH_SCRIPT_PATH):
        print(f"Error: KoboldCpp executable not found or not configured in config.py.")
        print(f"Attempted path: '{KOBOLDCPP_LAUNCH_SCRIPT_PATH}'")
        return False, None

    model_profile = KOBOLDCPP_PROFILES.get(model_name)
    if not model_profile:
        print(f"Error: Model profile '{model_name}' not found in KOBOLDCPP_PROFILES in config.py.")
        return False, None

    profile_path = model_profile.get("profile_path")
    if not profile_path or not os.path.exists(profile_path):
        print(f"Error: Profile path for '{model_name}' not found or is invalid.")
        print(f"Attempted path: '{profile_path}'")
        return False, None

    # --- Start the Process ---
    print(f"Starting KoboldCpp with profile '{model_name}' from: {KOBOLDCPP_LAUNCH_SCRIPT_PATH}")
    try:
        command = [KOBOLDCPP_LAUNCH_SCRIPT_PATH, "--config", profile_path]
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

        print(f"KoboldCpp process started with PID: {_kobold_process.pid} using model '{model_name}'")
        return True, model_name # Return success and the name of the model that was started
    except Exception as e:
        print(f"Failed to start KoboldCpp process: {e}")
        _kobold_process = None
        return False, None

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
