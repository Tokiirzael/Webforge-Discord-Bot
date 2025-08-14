import requests
import json
import base64
import logging

from config import GEMMA_API_BASE_URL, GEMMA_API_ENDPOINT, GEMMA_MODEL_NAME, GEMMA_API_KEY

class GemmaAPIClient:
    def __init__(self, base_url=GEMMA_API_BASE_URL, api_key=GEMMA_API_KEY):
        self.base_url = base_url
        self.api_key = api_key
        self.interpret_url = f"{self.base_url}{GEMMA_API_ENDPOINT}"

    def _send_request(self, data=None):
        """Helper to send HTTP POST requests to an OpenAI-compatible API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        try:
            logging.info(f"Sending payload to Gemma API at {self.interpret_url}")
            # To avoid logging the full base64 string, we can log a summary
            # logging.info(f"Payload summary: { {k: v for k, v in data.items() if k != 'messages'} }")
            response = requests.post(self.interpret_url, headers=headers, json=data, timeout=300) # 5-minute timeout
            logging.info(f"Raw response from Gemma API: {response.text}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to Gemma API at {self.base_url}.")
            return None
        except requests.exceptions.Timeout:
            print(f"Error: Request to {self.interpret_url} timed out.")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"An unexpected request error occurred: {e}")
            return None
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON response from {self.interpret_url}. Response: {response.text}")
            return None

    def interpret_image(self, base64_image: str, prompt: str, content_type: str):
        """
        Sends an image and a prompt for interpretation.
        """
        image_data_uri = f"data:{content_type};base64,{base64_image}"

        payload = {
            "model": GEMMA_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_data_uri
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1024 # Limit the response length for interpretations
        }

        print(f"Sending image interpretation request to Gemma API...")
        response_data = self._send_request(data=payload)

        if response_data and "choices" in response_data and response_data["choices"]:
            try:
                content = response_data["choices"][0]["message"]["content"]
                return content.strip()
            except (KeyError, IndexError) as e:
                print(f"Error parsing Gemma API response: {e}")
                return None
        else:
            print("No 'choices' found in the Gemma API response.")
            return None
        return None
