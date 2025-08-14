#!/usr/bin/env python3
"""
Kokoro TTS Local Wrapper Script

This script works with PierrunoYT/Kokoro-TTS-Local implementation
by creating a temporary script that uses the Kokoro CLI programmatically.

Usage: python kokoro_tts_local.py --text "Hello world" --voice af_bella --output output.wav
"""

import argparse
import sys
import os
import subprocess
import tempfile
import shutil
from pathlib import Path

def create_kokoro_script(kokoro_path, text, voice, speed, output_file):
    """Create a temporary Python script that uses Kokoro's internal API"""
    script_content = f'''
import sys
import os
sys.path.insert(0, r"{kokoro_path}")

try:
    from models import KokoroModel
    import torch
    import torchaudio
    
    # Initialize model
    model = KokoroModel()
    
    # Generate speech
    print("Generating speech...")
    
    # The exact API calls may vary - this is based on typical TTS model usage
    # You may need to adjust this based on your specific Kokoro version
    
    try:
        # Generate audio tensor
        audio_tensor = model.synthesize(
            text="{text}",
            voice="{voice}",
            speed={speed}
        )
        
        # Save as WAV file
        torchaudio.save("{output_file}", audio_tensor.unsqueeze(0), 24000)
        print("Speech generation completed successfully")
        
    except Exception as e:
        print(f"Error in synthesis: {{e}}")
        sys.exit(1)
        
except Exception as e:
    print(f"Error loading Kokoro: {{e}}")
    sys.exit(1)
'''
    return script_content

def main():
    parser = argparse.ArgumentParser(description="Generate speech using Kokoro-TTS-Local")
    parser.add_argument("--text", required=True, help="Text to convert to speech")
    parser.add_argument("--voice", default="af_bella", help="Voice to use (default: af_bella)")
    parser.add_argument("--output", required=True, help="Output audio file path")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed (0.5-2.0, default: 1.0)")
    parser.add_argument("--kokoro-path", help="Path to Kokoro-TTS-Local directory")
    
    args = parser.parse_args()
    
    try:
        print(f"Generating speech for: '{args.text}'")
        print(f"Using voice: {args.voice}")
        print(f"Speech speed: {args.speed}x")
        print(f"Output file: {args.output}")
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        
        # Determine Kokoro path
        if args.kokoro_path:
            kokoro_path = Path(args.kokoro_path)
        else:
            # Try to find Kokoro installation
            possible_paths = [
                Path("F:/Kokoro"),  # Default from config
                Path("../Kokoro-TTS-Local"),
                Path("./Kokoro-TTS-Local"),
                Path("../Kokoro"),
                Path("./Kokoro"),
            ]
            
            kokoro_path = None
            for path in possible_paths:
                if path.exists() and (path / "tts_demo.py").exists():
                    kokoro_path = path
                    break
            
            if not kokoro_path:
                print("❌ Error: Could not find Kokoro-TTS-Local installation")
                print("Please specify the path with --kokoro-path")
                print("Expected to find 'tts_demo.py' in the Kokoro directory")
                sys.exit(1)
        
        print(f"Using Kokoro installation at: {kokoro_path}")
        
        # Check for virtual environment
        venv_python = kokoro_path / "venv" / "Scripts" / "python.exe"  # Windows
        if not venv_python.exists():
            venv_python = kokoro_path / "venv" / "bin" / "python"  # Linux/Mac
        
        if not venv_python.exists():
            print("❌ Error: Could not find Python executable in Kokoro virtual environment")
            print(f"Expected: {venv_python}")
            print("Make sure Kokoro-TTS-Local is properly installed with its virtual environment")
            sys.exit(1)
        
        # Method 1: Try to use Kokoro's CLI directly with automation
        try:
            print("Attempting to use Kokoro CLI...")
            
            # Create a simple automation script
            automation_script = f'''
import sys
import os

# Change to Kokoro directory
os.chdir(r"{kokoro_path}")

# Add to path
sys.path.insert(0, r"{kokoro_path}")

# Try to use the TTS functionality directly
try:
    from models import KokoroModel
    import torch
    import torchaudio
    import soundfile as sf
    
    # Initialize the model
    model = KokoroModel()
    
    print("Model loaded successfully")
    
    # Generate the audio
    # Note: The exact method names may vary depending on your Kokoro version
    # Common patterns in TTS models:
    audio_data = None
    
    # Try different possible method names
    methods_to_try = [
        lambda: model.generate(text="{args.text}", voice="{args.voice}", speed={args.speed}),
        lambda: model.synthesize(text="{args.text}", voice="{args.voice}", speed={args.speed}),
        lambda: model.tts(text="{args.text}", voice="{args.voice}", speed={args.speed}),
        lambda: model.speak(text="{args.text}", voice="{args.voice}", speed={args.speed})
    ]
    
    for i, method in enumerate(methods_to_try):
        try:
            print(f"Trying method {{i+1}}...")
            audio_data = method()
            if audio_data is not None:
                print(f"Success with method {{i+1}}")
                break
        except Exception as e:
            print(f"Method {{i+1}} failed: {{e}}")
            continue
    
    if audio_data is not None:
        # Save the audio file
        if isinstance(audio_data, torch.Tensor):
            # Convert tensor to numpy if needed
            if audio_data.dim() > 1:
                audio_data = audio_data.squeeze()
            
            # Save as WAV
            sf.write(r"{args.output}", audio_data.cpu().numpy(), 24000)
        else:
            # Handle other data types
            sf.write(r"{args.output}", audio_data, 24000)
        
        print("Audio saved successfully")
    else:
        print("Error: No audio data generated")
        sys.exit(1)
        
except Exception as e:
    print(f"Error: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''
            
            # Write the automation script to a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(automation_script)
                temp_script = f.name
            
            try:
                # Run the automation script with Kokoro's Python environment
                result = subprocess.run(
                    [str(venv_python), temp_script],
                    capture_output=True,
                    text=True,
                    timeout=120  # 2-minute timeout
                )
                
                print("STDOUT:", result.stdout)
                if result.stderr:
                    print("STDERR:", result.stderr)
                
                if result.returncode == 0:
                    # Check if output file was created
                    if os.path.exists(args.output) and os.path.getsize(args.output) > 0:
                        print(f"✅ Audio file created successfully at: {args.output}")
                        print(f"✅ File verification passed - Size: {os.path.getsize(args.output)} bytes")
                    else:
                        print("❌ Error: Output file was not created or is empty")
                        sys.exit(1)
                else:
                    print(f"❌ Error: Script execution failed with return code {result.returncode}")
                    sys.exit(1)
                    
            finally:
                # Clean up temporary script
                try:
                    os.unlink(temp_script)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            print("❌ Error: TTS generation timed out")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error during TTS generation: {e}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()