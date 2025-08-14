# kokoro_api.py

import asyncio
import subprocess
import logging
import os
import requests
from pathlib import Path
import base64

from config import KOKORO_LOCAL_PATH, KOKORO_PYTHON_PATH, KOKORO_SCRIPT_PATH, KOKORO_OUTPUT_FILE, KOKORO_VOICE

class KokoroTTSClient:
    def __init__(self):
        self.local_path = Path(KOKORO_LOCAL_PATH) if KOKORO_LOCAL_PATH else None
        self.python_path = KOKORO_PYTHON_PATH
        self.script_path = KOKORO_SCRIPT_PATH
        self.output_file = KOKORO_OUTPUT_FILE
        self.voice = KOKORO_VOICE
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        
        logging.info(f"KokoroTTS initialized with voice: {self.voice}")
        logging.info(f"Local path: {self.local_path}")

    async def generate_speech(self, text: str) -> bool:
        """
        Generates speech from text using the local Kokoro-TTS-Local installation.
        Returns True if successful, False otherwise.
        """
        try:
            # Clean the text for TTS
            cleaned_text = self._clean_text_for_tts(text)
            
            if not cleaned_text.strip():
                logging.warning("Empty text after cleaning, skipping TTS generation")
                return False
            
            # Use the wrapper script to generate speech
            return await self._generate_subprocess(cleaned_text)
                
        except Exception as e:
            logging.error(f"Error during TTS generation: {e}")
            return False

    async def _generate_subprocess(self, text: str) -> bool:
        """
        Generate speech using the local wrapper script.
        """
        try:
            # Encode text to base64 to safely pass multi-line strings and special characters
            encoded_text = base64.b64encode(text.encode('utf-8')).decode('ascii')

            # Construct the command to call our wrapper script, ensuring all parts are strings
            cmd = [
                str(self.python_path),
                str(self.script_path),
                "--text", encoded_text,
                "--voice", self.voice,
                "--output", str(self.output_file),
                "--base64"  # Flag to tell the wrapper to decode the text
            ]
            
            # Add kokoro-path if specified
            if self.local_path:
                cmd.extend(["--kokoro-path", str(self.local_path)])
            
            logging.info(f"Executing TTS command: {' '.join(cmd)}")
            
            # Set up the environment to ensure UTF-8 output from the subprocess
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            # Run the command asynchronously with a timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logging.error("TTS generation timed out after 2 minutes")
                return False
            
            # Log output for debugging
            if stdout:
                logging.info(f"TTS STDOUT: {stdout.decode('utf-8', errors='ignore')}")
            if stderr:
                logging.error(f"TTS STDERR: {stderr.decode('utf-8', errors='ignore')}")
            
            if process.returncode == 0:
                # Verify the output file was created
                if os.path.exists(self.output_file) and os.path.getsize(self.output_file) > 0:
                    logging.info(f"TTS generation successful - Size: {os.path.getsize(self.output_file)} bytes")
                    return True
                else:
                    logging.error("TTS command succeeded but output file not found or empty")
                    return False
            else:
                logging.error(f"TTS subprocess failed. Return code: {process.returncode}")
                return False
                
        except Exception as e:
            logging.error(f"Error during subprocess TTS generation: {e}")
            return False

    def _clean_text_for_tts(self, text: str) -> str:
        """
        Cleans text for TTS by removing Discord formatting and other problematic characters.
        """
        # Remove Discord mentions
        import re
        text = re.sub(r'<@!?\d+>', '', text)
        text = re.sub(r'<#\d+>', '', text)
        text = re.sub(r'<@&\d+>', '', text)
        
        # Remove Discord markdown
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # Italic
        text = re.sub(r'__(.*?)__', r'\1', text)      # Underline
        text = re.sub(r'`(.*?)`', r'\1', text)        # Code
        text = re.sub(r'~~(.*?)~~', r'\1', text)      # Strikethrough
        
        # Remove URLs
        text = re.sub(r'https?://\S+', '', text)
        
        # Clean up extra whitespace
        text = ' '.join(text.split())
        
        # Limit length (local TTS can handle longer text)
        if len(text) > 2000:
            text = text[:1997] + "..."
            
        return text.strip()

    def get_output_file_path(self) -> str:
        """Returns the path to the generated audio file."""
        return self.output_file

    async def test_connection(self) -> bool:
        """
        Tests if Kokoro-TTS-Local is properly set up and accessible.
        """
        try:
            # Check if the local installation exists
            if not self.local_path or not self.local_path.exists():
                logging.error(f"Kokoro local path does not exist: {self.local_path}")
                return False
            
            # Check for required files
            required_files = ["tts_demo.py", "models.py"]
            for file in required_files:
                if not (self.local_path / file).exists():
                    logging.error(f"Required Kokoro file missing: {file}")
                    return False
            
            # Check Python executable
            if not os.path.exists(self.python_path):
                logging.error(f"Python executable not found: {self.python_path}")
                return False
            
            # Test with a short phrase
            logging.info("Testing Kokoro TTS with short phrase...")
            success = await self.generate_speech("Test")
            if success:
                logging.info("Kokoro TTS test successful")
                return True
            else:
                logging.error("Kokoro TTS test failed")
                return False
                
        except Exception as e:
            logging.error(f"Kokoro TTS connection test error: {e}")
            return False

    async def get_available_voices(self) -> list:
        """
        Get list of available voices from the Kokoro installation.
        """
        try:
            if not self.local_path:
                return []
            
            voices_dir = self.local_path / "voices"
            if not voices_dir.exists():
                return []
            
            # List .pt files in the voices directory
            voices = []
            for voice_file in voices_dir.glob("*.pt"):
                voice_name = voice_file.stem
                voices.append(voice_name)
            
            logging.info(f"Found {len(voices)} voices: {voices}")
            return sorted(voices)
                
        except Exception as e:
            logging.error(f"Error getting voices: {e}")
            return []


# Fallback client for different setups
class KokoroLocalDirectClient:
    """
    Direct client that attempts to import and use Kokoro modules directly.
    Use this if the subprocess approach doesn't work for your setup.
    """
    def __init__(self):
        self.local_path = Path(KOKORO_LOCAL_PATH) if KOKORO_LOCAL_PATH else None
        self.voice = KOKORO_VOICE
        self.output_file = KOKORO_OUTPUT_FILE
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        
        # Try to add Kokoro to Python path
        if self.local_path and self.local_path.exists():
            import sys
            sys.path.insert(0, str(self.local_path))

    async def generate_speech(self, text: str) -> bool:
        """
        Generate speech by importing Kokoro modules directly.
        """
        try:
            cleaned_text = self._clean_text_for_tts(text)
            
            if not cleaned_text.strip():
                logging.warning("Empty text after cleaning, skipping TTS generation")
                return False
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None, 
                self._generate_sync, 
                cleaned_text
            )
            return success
            
        except Exception as e:
            logging.error(f"Error in direct TTS generation: {e}")
            return False

    def _generate_sync(self, text: str) -> bool:
        """
        Synchronous generation method for use with run_in_executor.
        """
        try:
            # Import Kokoro modules
            from models import KokoroModel
            import torch
            import torchaudio
            
            # Initialize model
            model = KokoroModel()
            
            # Generate audio
            # Note: The exact API may vary based on your Kokoro version
            # Try different common method names
            audio_data = None
            methods = ['generate', 'synthesize', 'tts', 'speak']
            
            for method_name in methods:
                if hasattr(model, method_name):
                    try:
                        method = getattr(model, method_name)
                        audio_data = method(text=text, voice=self.voice)
                        if audio_data is not None:
                            break
                    except Exception as e:
                        logging.debug(f"Method {method_name} failed: {e}")
                        continue
            
            if audio_data is None:
                logging.error("No valid generation method found or all methods failed")
                return False
            
            # Save audio file
            if isinstance(audio_data, torch.Tensor):
                # Ensure correct shape for saving
                if audio_data.dim() > 1:
                    audio_data = audio_data.squeeze()
                
                # Save as WAV with 24kHz sample rate (typical for Kokoro)
                torchaudio.save(self.output_file, audio_data.unsqueeze(0), 24000)
            else:
                # Handle other data types (numpy arrays, etc.)
                import soundfile as sf
                sf.write(self.output_file, audio_data, 24000)
            
            # Verify file was created
            if os.path.exists(self.output_file) and os.path.getsize(self.output_file) > 0:
                logging.info(f"Direct TTS generation successful - Size: {os.path.getsize(self.output_file)} bytes")
                return True
            else:
                logging.error("Direct TTS generation failed - no output file")
                return False
            
        except ImportError as e:
            logging.error(f"Failed to import Kokoro modules: {e}")
            return False
        except Exception as e:
            logging.error(f"Error in direct TTS generation: {e}")
            return False

    def _clean_text_for_tts(self, text: str) -> str:
        """Same cleaning logic as the main client."""
        import re
        text = re.sub(r'<@!?\d+>', '', text)
        text = re.sub(r'<#\d+>', '', text)
        text = re.sub(r'<@&\d+>', '', text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'__(.*?)__', r'\1', text)
        text = re.sub(r'`(.*?)`', r'\1', text)
        text = re.sub(r'~~(.*?)~~', r'\1', text)
        text = re.sub(r'https?://\S+', '', text)
        text = ' '.join(text.split())
        if len(text) > 2000:
            text = text[:1997] + "..."
        return text.strip()