# kobold_api.py

import requests
import json

from config import KOBOLDCPP_API_URL, KOBOLDCPP_CHAT_ENDPOINT, KOBOLDCPP_MAX_LENGTH

class KoboldAPIClient:
    def __init__(self, base_url=KOBOLDCPP_API_URL):
        self.base_url = base_url
        self.chat_url = f"{self.base_url}{KOBOLDCPP_CHAT_ENDPOINT}"

    def is_online(self):
        """Checks if the Kobold API is responsive."""
        try:
            response = requests.get(self.base_url, timeout=5)
            return response.status_code == 200
        except requests.ConnectionError:
            return False
        except requests.RequestException:
            return False

    def _send_request(self, method, url, data=None):
        """Helper to send HTTP requests and handle common errors."""
        try:
            if method == "POST":
                response = requests.post(url, json=data, timeout=120) # 2-minute timeout
            elif method == "GET":
                response = requests.get(url, timeout=60)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to KoboldCpp API at {self.base_url}.")
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

    def generate_text(self, prompt):
        """
        Sends a text generation request to KoboldCpp.
        """
        payload = {
            "prompt": prompt,
            "max_length": KOBOLDCPP_MAX_LENGTH,
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64,
            "min_p": 0.0,
            "rep_pen": 1.0,
            "quiet": True
        }

        print(f"Sending text generation request with payload: {json.dumps(payload, indent=2)}")
        response_data = self._send_request("POST", self.chat_url, data=payload)

        if response_data and "results" in response_data and response_data["results"]:
            try:
                # Assuming the response is like: {"results": [{"text": "..."}]}
                generated_text = response_data["results"][0]["text"]
                return generated_text.strip()
            except (KeyError, IndexError) as e:
                print(f"Error parsing KoboldCpp response: {e}")
                return None
        else:
            print("No 'results' found in the KoboldCpp API response.")
            return None
        return None

    def interrogate_image(self, base64_image: str):
        """
        Sends an image to the /sdapi/v1/interrogate endpoint to get a text caption.
        """
        interrogate_url = f"{self.base_url}/sdapi/v1/interrogate"
        payload = {
            "image": base64_image,
            "model": "clip" # Common default interrogator model
        }

        print("Sending image interrogation request...")
        response_data = self._send_request("POST", interrogate_url, data=payload)

        if response_data and "caption" in response_data:
            return response_data["caption"]
        else:
            print("No 'caption' found in the interrogation response.")
            return None
