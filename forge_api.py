# forge_api.py

import requests
import json
import base64
import io
from PIL import Image # Pillow library for image handling
import os

from config import FORGE_API_URL, TXT2IMG_ENDPOINT, DEFAULT_MODEL

class ForgeAPIClient:
    def __init__(self, base_url=FORGE_API_URL):
        self.base_url = base_url
        self.txt2img_url = f"{self.base_url}{TXT2IMG_ENDPOINT}"

    def _send_request(self, method, url, data=None):
        """Helper to send HTTP requests and handle common errors."""
        try:
            if method == "POST":
                response = requests.post(url, json=data, timeout=300) # 5-minute timeout
            elif method == "GET":
                response = requests.get(url, timeout=60)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to Forge API at {self.base_url}. Is Forge running with --api?")
            return None
        except requests.exceptions.Timeout:
            print(f"Error: Request to {url} timed out.")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"An unexpected request error occurred: {e}")
            return None
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON response from {url}. Response: {response.text}")
            return None

    def txt2img(self, payload):
        """
        Sends a text-to-image generation request to Forge.
        Payload structure example:
        {
            "prompt": "a dog",
            "negative_prompt": "cat",
            "steps": 20,
            "cfg_scale": 7,
            "sampler_name": "Euler a",
            "width": 512,
            "height": 512,
            "seed": -1,
            "override_settings": {
                "sd_model_checkpoint": "model_name.safetensors"
            },
            "enable_hr": true, # For Hires. fix
            "hr_scale": 2, # If you want to force a scale, but user wants UI settings
            # Other hr settings not needed if user specifies to use UI settings
        }
        """
        # Ensure the model is set in override_settings
        if "override_settings" not in payload:
            payload["override_settings"] = {}
        if "sd_model_checkpoint" not in payload["override_settings"]:
            payload["override_settings"]["sd_model_checkpoint"] = DEFAULT_MODEL

        print(f"Sending txt2img request with payload: {json.dumps(payload, indent=2)}")
        response_data = self._send_request("POST", self.txt2img_url, data=payload)

        if response_data and "images" in response_data and response_data["images"]:
            # Forge returns a list of base64 encoded images
            image_b64 = response_data["images"][0] # Take the first image
            try:
                img_bytes = base64.b64decode(image_b64)
                image = Image.open(io.BytesIO(img_bytes))
                return image
            except Exception as e:
                print(f"Error decoding or opening image: {e}")
                return None
        elif response_data:
            print("No 'images' found in the Forge API response.")
            return None
        return None

# You could add other API interactions here if needed, e.g., for getting models:
# def get_models(self):
#     return self._send_request("GET", f"{self.base_url}/sdapi/v1/sd-models")