import subprocess
import os
from config import FORGE_LAUNCH_SCRIPT_PATH

_forge_process = None

def start_forge():
    """Starts the Forge WebUI as a subprocess."""
    global _forge_process
    if is_forge_running():
        print("Forge process is already running.")
        return True

    if not FORGE_LAUNCH_SCRIPT_PATH or not os.path.exists(FORGE_LAUNCH_SCRIPT_PATH):
        print(f"Error: Forge launch script not found or not configured in config.py.")
        print(f"Attempted path: '{FORGE_LAUNCH_SCRIPT_PATH}'")
        return False

    print(f"Starting Forge from: {FORGE_LAUNCH_SCRIPT_PATH}")
    try:
        # Use Popen to start the process in the background without blocking.
        # For Windows, `creationflags` can hide the console window.
        # For Linux/macOS, `preexec_fn=os.setsid` is important for clean termination of the process group.
        # The script needs to be run from its own directory to find related files.
        script_dir = os.path.dirname(FORGE_LAUNCH_SCRIPT_PATH)

        if os.name == 'nt': # Windows
            # Launching batch files directly can be tricky. A reliable way is to use `cmd.exe`.
            # The `/c` argument tells cmd to execute the command that follows and then terminate.
            # `cwd` sets the working directory, which is crucial for the script to find other files.
            # We just need to run the batch script directly, as the arguments are now set inside it.
            _forge_process = subprocess.Popen(
                [os.path.basename(FORGE_LAUNCH_SCRIPT_PATH)],
                cwd=script_dir,
                shell=True # Using shell=True is simpler for .bat files on Windows
            )
        else: # Linux, macOS
            # For non-Windows systems, we can often execute shell scripts directly.
            _forge_process = subprocess.Popen(
                [FORGE_LAUNCH_SCRIPT_PATH],
                preexec_fn=os.setsid,
                cwd=script_dir
            )

        print(f"Forge process started with PID: {_forge_process.pid}")
        return True
    except Exception as e:
        print(f"Failed to start Forge process: {e}")
        _forge_process = None
        return False

def stop_forge():
    """Stops the running Forge WebUI subprocess."""
    global _forge_process
    if not is_forge_running():
        print("Forge process is not running.")
        return True

    print(f"Stopping Forge process with PID: {_forge_process.pid}")
    try:
        # Terminate the process and its children.
        if os.name == 'nt':
            # On Windows, terminating the parent doesn't always kill child processes.
            # A more robust way is to kill the process tree.
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(_forge_process.pid)])
        else:
            # On Linux/macOS, `os.killpg` can kill the whole process group.
            import signal
            os.killpg(os.getpgid(_forge_process.pid), signal.SIGTERM)

        _forge_process.wait(timeout=10) # Wait for the process to terminate
        print("Forge process stopped.")
    except Exception as e:
        print(f"An error occurred while stopping the Forge process: {e}")
        # If termination fails, a manual kill might be needed.
    finally:
        _forge_process = None
    return True

def is_forge_running():
    """Checks if the Forge process is currently running."""
    global _forge_process
    if _forge_process is None:
        return False

    # `poll()` returns None if the process is still running, otherwise it returns the exit code.
    return _forge_process.poll() is None
