# config.py

import os

# --- Discord Bot Settings ---
DISCORD_TOKEN_NAME = "DISCORD_TOKEN" # The name of the environment variable for your bot token
COMMAND_PREFIX = "!paint " # The character your bot's commands will start with

# --- Channel Restrictions ---
# A list of channel IDs where the bot is allowed to respond to commands.
# To get a channel ID: Enable Developer Mode in Discord (User Settings -> Advanced),
# then right-click on the channel and select "Copy ID".
# Example: ALLOWED_CHANNEL_IDS = [123456789012345678, 987654321098765432]
ALLOWED_CHANNEL_IDS = [
    1390064007037194260, # Replace with your actual channel ID
    1390064079720153219  # Add more as needed
    ]

# --- Stable Diffusion WebUI Forge API Settings ---
FORGE_API_URL = "http://127.0.0.1:7860" # Default API URL for Forge. Change if yours is different.
TXT2IMG_ENDPOINT = "/sdapi/v1/txt2img" # The API endpoint for text-to-image generation

# --- Default Stable Diffusion Generation Parameters ---
# These are the default settings for image generation. Users cannot change these
# to prevent exceeding system capabilities or generating wildly inconsistent results.
DEFAULT_STEPS = 28 # How many steps the model takes to generate an image
DEFAULT_CFG_SCALE = 3 # Classifier Free Guidance Scale (how much the prompt influences the image)
DEFAULT_SAMPLER_NAME = "Euler a" # The algorithm used for sampling
DEFAULT_SEED = -1 # -1 means random seed for each generation
DEFAULT_MODEL = "plantMilkModelSuite_walnut.safetensors" # The name of the model you want to use.
                                            # Make sure this model is loaded in your Forge UI.
DEFAULT_CLIP_SKIP = 2 # From your PNG Info


# --- Image Resolutions Presets ---
# These are the only resolutions users can choose from.
RESOLUTIONS = {
    "portrait": {"width": 1024, "height": 1520},
    "landscape": {"width": 1520, "height": 1024},
    "square": {"width": 1024, "height": 1024},
}
# Initial default resolution when the bot starts
DEFAULT_RESOLUTION_PRESET = "square"

# --- Negative Prompt Filtering Settings ---
# Words or phrases that will be removed from user-provided negative prompts.
# This helps prevent distasteful content and keeps generations cleaner.
# Add or remove items from this list as needed. Case-insensitive.
FORBIDDEN_NEGATIVE_TERMS = [
    "Child", "Loli"
]

# --- Base Prompts for All Generations ---
# These prompts will be added to every user-provided prompt.
# Use common prompt enhancers here. Separate with commas.
BASE_POSITIVE_PROMPT = "<lora:Detailer_NoobAI_Incrs_v1:1> detailed, masterpiece, best quality, good quality"

# These negative prompts will be added to every user-provided negative prompt.
# Use common negative prompt enhancers here to avoid bad quality. Separate with commas.
BASE_NEGATIVE_PROMPT = "bad quality, worst quality, lowres, jpeg artifacts, bad anatomy, bad hands, multiple views, signature, watermark, censored, ugly, child, loli"


# --- ADetailer Default Settings ---
# IMPORTANT: Ensure ADetailer extension is installed in Forge AND its models are downloaded.
# Common models: face_yolov8n.pt, hand_yolo8n.pt, person_yolo8m.pt etc.
# Check your Forge's 'models/adetailer' directory.
ADETAILER_ENABLED_BY_DEFAULT = True # Set to True to always enable ADetailer
ADETAILER_DETECTION_MODEL = "face_yolov8n.pt" # Example: your ADetailer detection model
ADETAILER_PROMPT = "face, perfect eyes, beautiful"
ADETAILER_NEGATIVE_PROMPT = "bad face, blurry, deformed"
ADETAILER_CONFIDENCE = 0.3 # Minimum detection confidence
ADETAILER_MASK_BLUR = 4 # Blur of the mask in pixels
ADETAILER_INPAINT_DENOISING = 0.4 # Denoising strength for inpainting
ADETAILER_INPAINT_ONLY_MASKED = True # Only inpaint the masked area
ADETAILER_INPAINT_PADDING = 32 # From your PNG info


# --- Bot Message Strings ---
MSG_INVALID_RES = "Sorry, that's not a valid resolution preset. Please choose from: `portrait`, `landscape`, `square`."
MSG_RES_SET = "Resolution set to **{width}x{height}** (`{preset}`)."
# MSG_UPSCALE_ENABLED and MSG_UPSCALE_DISABLED are removed as there's no !upscale command
# but you can add them back if you re-introduce upscaling.
MSG_GENERATING = "Generating image with Forge... this might take a moment!"
MSG_GEN_ERROR = "An error occurred during image generation. Please check the bot's console for details or try again later."
MSG_NO_PROMPT = "Please provide a prompt! Example: `!paint generate a majestic dragon flying over a castle :: text, blurry`"
MSG_API_ERROR = "Could not connect to Forge API. Make sure Forge is running with `--api` enabled and the `FORGE_API_URL` in `config.py` is correct."