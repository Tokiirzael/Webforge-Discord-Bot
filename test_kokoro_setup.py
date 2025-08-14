#!/usr/bin/env python3
"""
Test script to verify Kokoro TTS setup for Discord bot integration.

This script helps diagnose configuration issues and test the TTS pipeline.
"""

import os
import sys
from pathlib import Path
import subprocess

def test_kokoro_path():
    """Test if Kokoro installation can be found."""
    print("=" * 50)
    print("TESTING KOKORO INSTALLATION PATH")
    print("=" * 50)
    
    # Check config values (you'll need to update these)
    kokoro_paths_to_check = [
        "F:/Kokoro",  # Your likely path based on config
        "../Kokoro",
        "./Kokoro",
        "../Kokoro-TTS-Local",
        "./Kokoro-TTS-Local",
    ]
    
    found_path = None
    for path_str in kokoro_paths_to_check:
        path = Path(path_str)
        print(f"Checking: {path.absolute()}")
        
        if path.exists():
            print(f"  ✅ Path exists")
            
            # Check for key files
            key_files = ["tts_demo.py", "models.py", "gradio_interface.py"]
            all_files_found = True
            
            for file in key_files:
                file_path = path / file
                if file_path.exists():
                    print(f"  ✅ Found {file}")
                else:
                    print(f"  ❌ Missing {file}")
                    all_files_found = False
            
            if all_files_found:
                found_path = path
                print(f"  🎉 Valid Kokoro installation found!")
                break
        else:
            print(f"  ❌ Path does not exist")
    
    if found_path:
        print(f"\n✅ Kokoro installation found at: {found_path.absolute()}")
        return found_path
    else:
        print(f"\n❌ No valid Kokoro installation found!")
        print("Please make sure Kokoro-TTS-Local is installed and update the paths in config.py")
        return None

def test_python_environment(kokoro_path):
    """Test if Python environment is accessible."""
    print("\n" + "=" * 50)
    print("TESTING PYTHON ENVIRONMENT")
    print("=" * 50)
    
    # Check for virtual environment
    venv_paths = [
        kokoro_path / "venv" / "Scripts" / "python.exe",  # Windows
        kokoro_path / "venv" / "bin" / "python",  # Linux/Mac
    ]
    
    python_path = None
    for venv_path in venv_paths:
        print(f"Checking: {venv_path}")
        if venv_path.exists():
            print(f"  ✅ Virtual environment Python found")
            python_path = venv_path
            break
        else:
            print(f"  ❌ Not found")
    
    if not python_path:
        # Try system Python
        python_path = "python"
        print(f"  🔄 Falling back to system Python: {python_path}")
    
    # Test Python execution
    try:
        result = subprocess.run([str(python_path), "--version"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"  ✅ Python version: {result.stdout.strip()}")
            return python_path
        else:
            print(f"  ❌ Python execution failed: {result.stderr}")
            return None
    except Exception as e:
        print(f"  ❌ Error testing Python: {e}")
        return None

def test_kokoro_modules(kokoro_path, python_path):
    """Test if Kokoro modules can be imported."""
    print("\n" + "=" * 50)
    print("TESTING KOKORO MODULES")
    print("=" * 50)
    
    test_script = f'''
import sys
sys.path.insert(0, r"{kokoro_path}")

try:
    print("Testing module imports...")
    
    # Test basic imports
    from models import KokoroModel
    print("✅ Successfully imported KokoroModel")
    
    import torch
    print(f"✅ PyTorch version: {{torch.__version__}}")
    print(f"✅ CUDA available: {{torch.cuda.is_available()}}")
    
    # Test model initialization
    model = KokoroModel()
    print("✅ Model initialized successfully")
    
    print("All module tests passed!")
    
except Exception as e:
    print(f"❌ Module test failed: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''
    
    try:
        # Write test script to temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(test_script)
            temp_script = f.name
        
        # Run test script
        result = subprocess.run([str(python_path), temp_script], 
                              capture_output=True, text=True, timeout=30)
        
        print("Test output:")
        print(result.stdout)
        
        if result.stderr:
            print("Errors/Warnings:")
            print(result.stderr)
        
        # Clean up
        os.unlink(temp_script)
        
        if result.returncode == 0:
            print("✅ All Kokoro modules loaded successfully")
            return True
        else:
            print("❌ Module loading failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during module test: {e}")
        return False

def test_voices(kokoro_path):
    """Test available voices."""
    print("\n" + "=" * 50)
    print("TESTING AVAILABLE VOICES")
    print("=" * 50)
    
    voices_dir = kokoro_path / "voices"
    
    if not voices_dir.exists():
        print(f"❌ Voices directory not found: {voices_dir}")
        return []
    
    voices = []
    for voice_file in voices_dir.glob("*.pt"):
        voice_name = voice_file.stem
        voices.append(voice_name)
        print(f"  ✅ Found voice: {voice_name}")
    
    if not voices:
        print("❌ No voice files found!")
        print("You may need to run Kokoro once to download voice files")
    else:
        print(f"\n✅ Found {len(voices)} voices total")
    
    return voices

def test_tts_generation(kokoro_path, python_path):
    """Test actual TTS generation."""
    print("\n" + "=" * 50)
    print("TESTING TTS GENERATION")
    print("=" * 50)
    
    # Create output directory
    output_dir = Path("./temp_audio")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "test_generation.wav"
    
    # Test our wrapper script
    wrapper_script = "kokoro_tts_local.py"
    
    if not Path(wrapper_script).exists():
        print(f"❌ Wrapper script not found: {wrapper_script}")
        print("Make sure kokoro_tts_local.py is in the current directory")
        return False
    
    cmd = [
        str(python_path),
        wrapper_script,
        "--text", "This is a test of the Kokoro text to speech system.",
        "--voice", "af_bella",
        "--output", str(output_file),
        "--kokoro-path", str(kokoro_path)
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        print("Command output:")
        print(result.stdout)
        
        if result.stderr:
            print("Errors/Warnings:")
            print(result.stderr)
        
        if result.returncode == 0 and output_file.exists() and output_file.stat().st_size > 0:
            print(f"✅ TTS generation successful!")
            print(f"✅ Output file: {output_file}")
            print(f"✅ File size: {output_file.stat().st_size} bytes")
            return True
        else:
            print("❌ TTS generation failed")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ TTS generation timed out")
        return False
    except Exception as e:
        print(f"❌ Error during TTS test: {e}")
        return False

def main():
    print("🎵 Kokoro TTS Setup Test for Discord Bot 🎵")
    print("This script will test your Kokoro installation and configuration.")
    print()
    
    # Step 1: Find Kokoro installation
    kokoro_path = test_kokoro_path()
    if not kokoro_path:
        print("\n❌ Cannot proceed without a valid Kokoro installation")
        print("\nNext steps:")
        print("1. Install Kokoro-TTS-Local from: https://github.com/PierrunoYT/Kokoro-TTS-Local")
        print("2. Update the paths in this script and config.py")
        print("3. Run this test again")
        return False
    
    # Step 2: Test Python environment
    python_path = test_python_environment(kokoro_path)
    if not python_path:
        print("\n❌ Cannot proceed without a working Python environment")
        return False
    
    # Step 3: Test module imports
    modules_ok = test_kokoro_modules(kokoro_path, python_path)
    if not modules_ok:
        print("\n❌ Module loading failed - check dependencies")
        return False
    
    # Step 4: Test voices
    voices = test_voices(kokoro_path)
    
    # Step 5: Test actual generation
    generation_ok = test_tts_generation(kokoro_path, python_path)
    
    # Final summary
    print("\n" + "=" * 50)
    print("FINAL SUMMARY")
    print("=" * 50)
    
    if generation_ok:
        print("🎉 ALL TESTS PASSED!")
        print("\nYour Kokoro setup is working correctly.")
        print("Update your config.py with these values:")
        print(f'KOKORO_LOCAL_PATH = r"{kokoro_path}"')
        print(f'KOKORO_PYTHON_PATH = r"{python_path}"')
        print('KOKORO_SCRIPT_PATH = "./kokoro_tts_local.py"')
        if voices:
            print(f'KOKORO_VOICE = "{voices[0]}" # or any of: {", ".join(voices[:5])}')
        
        return True
    else:
        print("❌ Some tests failed.")
        print("Please fix the issues above and try again.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)