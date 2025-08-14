#!/usr/bin/env python3
"""
Kokoro TTS Script - Fixed API Implementation

This script interfaces with the Kokoro-FastAPI running on localhost:8880
Usage: python kokoro_tts.py --text "Hello world" --voice af_bella --output output.wav
"""

import argparse
import sys
import os
import requests
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Generate speech using Kokoro-82M TTS")
    parser.add_argument("--text", required=True, help="Text to convert to speech")
    parser.add_argument("--voice", default="af_bella", help="Voice to use (default: af_bella)")
    parser.add_argument("--output", required=True, help="Output audio file path")
    
    args = parser.parse_args()
    
    try:
        print(f"Generating speech for: '{args.text}'")
        print(f"Using voice: {args.voice}")
        print(f"Output file: {args.output}")
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        
        # Check if server is running by testing the voices endpoint first
        try:
            voices_response = requests.get("http://localhost:8880/v1/audio/voices", timeout=5)
            if voices_response.status_code != 200:
                print("❌ Error: Kokoro API server responded with error to voices request")
                print(f"Response: {voices_response.text}")
                sys.exit(1)
        except requests.exceptions.ConnectionError:
            print("❌ Error: Could not connect to Kokoro API at http://localhost:8880")
            print("Make sure your Kokoro TTS server is running with: docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest")
            sys.exit(1)
        
        # Prepare payload for the correct OpenAI-compatible endpoint
        payload = {
            "model": "kokoro",
            "input": args.text,
            "voice": args.voice,
            "response_format": "wav",  # Use wav for better compatibility
            "speed": 1.0
        }
        
        print("Sending request to Kokoro API...")
        # Use the correct OpenAI-compatible speech endpoint
        response = requests.post(
            "http://localhost:8880/v1/audio/speech", 
            json=payload, 
            timeout=30
        )
        
        # Check if request was successful
        if response.status_code == 200:
            # Write audio data to file
            with open(args.output, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Audio file created successfully at: {args.output}")
            
            # Verify file was created and has content
            if os.path.exists(args.output) and os.path.getsize(args.output) > 0:
                print(f"✅ File verification passed - Size: {os.path.getsize(args.output)} bytes")
            else:
                print("⚠️ Warning: Output file is empty or missing")
                sys.exit(1)
                
        else:
            print(f"❌ API Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            
            # Provide helpful suggestions based on common error codes
            if response.status_code == 404:
                print("\n💡 Troubleshooting suggestions:")
                print("1. Make sure Kokoro-FastAPI is running on port 8880")
                print("2. Verify the server started successfully without errors")
                print("3. Try accessing http://localhost:8880/docs in your browser")
            elif response.status_code == 422:
                print("\n💡 This might be a voice name issue. Try:")
                print("- af_bella, af_sarah, af_nicole, or af_sky")
                print("- Check available voices at: http://localhost:8880/v1/audio/voices")
            
            sys.exit(1)
            
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to Kokoro API at http://localhost:8880")
        print("\n💡 Make sure your Kokoro TTS server is running:")
        print("For GPU: docker run --gpus all -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest")
        print("For CPU: docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest")
        sys.exit(1)
        
    except requests.exceptions.Timeout:
        print("❌ Error: Request to Kokoro API timed out")
        print("The text might be too long, or the server is overloaded")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error generating speech: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()