# config.py
from pathlib import Path

# --- Base Directory ---
# Get the absolute path of the directory where this config file is located
BASE_DIR = Path(__file__).resolve().parent

# --- Discord Bot Settings ---
# The name of the environment variable for your bot token.
# You need to create a .env file in the same directory and put a line like:
# DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
DISCORD_TOKEN_NAME = "DISCORD_TOKEN"

# The prefix for all bot commands.
COMMAND_PREFIX = "!paint "

# --- Channel Restrictions ---
# A list of channel IDs where the bot is allowed to use paint commands.
PAINT_CHANNEL_IDS = [
    1390064079720153219,
    1390064007037194260,
    1405408895077322772,
]
# A list of additional channel IDs where the bot is allowed to chat.
# The bot can also chat in the PAINT_CHANNEL_IDS.
CHAT_CHANNEL_IDS = [
    1405076588156026922
]
# A list of category IDs where the bot is allowed to chat.
ALLOWED_CATEGORY_IDS = [
    1390063887105130507,
    1405403511142748270
]

# --- Permission Settings ---
# The role required to generate images.
GENERATION_ROLE_ID = [
    1404675951668760709,
    1405409041366122619,
]

# A list of role IDs that can delete any bot message.
MODERATOR_ROLE_IDS = [
    1202820140958490725,
    1201664265606680639,
    1202859329863159838,
    1405409041366122619
]

# --- Stat Tracking and Tiers ---
STATS_FILE = "user_stats.json"
PROFILE_DIR = "user_profiles"
# The titles users get as they generate more images.
# The number is the minimum generations needed to achieve the title.
# The list must be sorted from highest threshold to lowest.
GENERATION_TIERS = [
    (80, "Ghost in the System"),
    (60, "Digitized"),
    (40, "Attentive"),
    (20, "Curiosity"),
]

# --- Stable Diffusion Forge API Settings ---
# The address of your running Forge instance.
FORGE_API_URL = "http://127.0.0.1:7860"
TXT2IMG_ENDPOINT = "/sdapi/v1/txt2img"

# --- KoboldCpp API Settings ---
KOBOLDCPP_API_URL = "http://127.0.0.1:5001" # The base URL for your KoboldCpp instance
KOBOLDCPP_CHAT_ENDPOINT = "/api/v1/generate" # The endpoint for text generation

# --- Kokoro TTS Settings (For PierrunoYT/Kokoro-TTS-Local) ---
# Path to your Kokoro-TTS-Local installation directory (relative to this config file)
KOKORO_SUBDIR = "Kokoro-TTS-Local"
KOKORO_LOCAL_PATH = BASE_DIR / KOKORO_SUBDIR

# Path to Python executable in your Kokoro environment
KOKORO_PYTHON_PATH = KOKORO_LOCAL_PATH / "venv" / "Scripts" / "python.exe"

# Path to the TTS script
KOKORO_SCRIPT_PATH = BASE_DIR / "kokoro_tts_local_wrapper.py"

# Output file path for generated audio
KOKORO_OUTPUT_FILE = BASE_DIR / "temp_audio" / "gemma_speech.wav"

# Voice to use - available voices from Kokoro-TTS-Local
KOKORO_VOICE = "af_bella"  # Options: af_bella, af_sarah, af_sky, af_nicole, am_adam, am_michael, etc.

# Maximum concurrent TTS requests (keep low to avoid overwhelming the system)
MAX_CONCURRENT_TTS = 1

# TTS timeout in seconds (increased since local TTS can be slower)
TTS_TIMEOUT = 120

# --- Character Settings ---
# This is the character the bot will roleplay as.
CHARACTER_NAME = "Gemma"
# This is the persona that will be used in the prompt to the AI.
CHARACTER_PERSONA = "A helpful and vaguely flirtatious feminine AI assistant who occasionally jokes or teases the users. Speaks with as if she is an eloquent servant. Does not use any kind of emoji. Cannot see images."
# This is a greeting message the bot can use.
CHARACTER_GREETING = "Hello! You require my attention? Lovely thing."

# --- Timezone Settings ---
# A mapping of common user-provided timezone names to their official IANA DB names.
# This allows the bot to understand natural language requests for time.
# The key (e.g., "cst") must be lowercase.
# IMPORTANT: Always map to location-based names (e.g., "America/Chicago") instead of
# fixed abbreviations (e.g., "CST"). This ensures Daylight Saving Time is handled automatically.
TIMEZONE_MAP = {
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "mountain": "America/Denver",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "central": "America/Chicago",
    "est": "America/New_York",
    "edt": "America/New_York",
    "eastern": "America/New_York",
    "gmt": "Europe/London",
    "bst": "Europe/London",
    "london": "Europe/London",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "paris": "Europe/Paris",
    "ist": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "jst": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
    "sydney": "Australia/Sydney",
}

# The maximum number of tokens to include in the context for the AI.
CONTEXT_TOKEN_LIMIT = 16384

# --- Default Generation Parameters ---
# These are the base settings for every image generation.
DEFAULT_MODEL = "plantMilkModelSuite_walnut.safetensors" # The model file to use for generation.
DEFAULT_SAMPLER_NAME = "Euler a"    # The sampling method.
DEFAULT_STEPS = 28                  # How many steps to take to generate the image (higher can be better).
DEFAULT_CFG_SCALE = 3               # How closely the bot should follow the prompt (higher is stricter).
DEFAULT_SEED = -1                   # The starting number for generation. -1 means a random seed every time.
DEFAULT_CLIP_SKIP = 2               # How many layers of the model to skip at the end. 2 is a common value.

# --- Image Resolution Presets ---
# The available resolutions for the !generate, !generateport, and !generateland commands.
RESOLUTIONS = {
    "portrait": {"width": 1024, "height": 1520},
    "landscape": {"width": 1520, "height": 1024},
    "square": {"width": 1024, "height": 1024},
}

# --- Base Prompts ---
# These are automatically added to the start of your prompts.
BASE_POSITIVE_PROMPT = "<lora:Detailer_NoobAI_Incrs_v1:1> detailed, masterpiece, best quality, good quality"
BASE_NEGATIVE_PROMPT = "bad quality, worst quality, lowres, jpeg artifacts, bad anatomy, bad hands, multiple views, signature, watermark, censored, ugly, child, loli"

# --- Negative Prompt Filtering ---
# Any words in this list will be silently removed from a user's negative prompt.
# This is a safety feature to help prevent generating certain types of content.
FORBIDDEN_NEGATIVE_TERMS = ["Child", "Loli"]

# --- ADetailer Settings ---
# These settings control the "ADetailer" extension, which automatically finds and
# redraws faces and hands to make them look better.
ADETAILER_ENABLED_BY_DEFAULT = True
ADETAILER_DETECTION_MODEL = "face_yolov8n.pt" # The model used to find faces.
ADETAILER_PROMPT = "face, perfect eyes, beautiful"
ADETAILER_NEGATIVE_PROMPT = "bad face, blurry, deformed"
ADETAILER_CONFIDENCE = 0.3          # How confident the model must be to redraw a face.
ADETAILER_MASK_BLUR = 4             # How much to blur the edge of the redrawn area.
ADETAILER_INPAINT_DENOISING = 0.4   # How much the redrawn face can change from the original.
ADETAILER_INPAINT_ONLY_MASKED = True
ADETAILER_INPAINT_PADDING = 32

# --- Hires.fix Settings ---
# These settings are used when a user includes the `--upscale` flag in their command.
# Hires.fix generates a small image first, then upscales it to a larger size,
# adding more detail.
HIRES_UPSCALER = "remacri_original" # The upscaling algorithm to use.
HIRES_STEPS = 15                    # How many steps to use in the second, upscaling pass.
HIRES_DENOISING = 0.35              # How much the image is allowed to change during the upscale.
HIRES_UPSCALE_BY = 1.5              # How much to increase the image size by (e.g., 1.5x).
HIRES_RESIZE_WIDTH = 0              # Set to 0 to use the HIRES_UPSCALE_BY factor.
HIRES_RESIZE_HEIGHT = 0             # Set to 0 to use the HIRES_UPSCALE_BY factor.

# --- Bot Message Strings ---
# These are the messages the bot sends in Discord.
MSG_GENERATING = "Generating image with Forge... this might take a moment!"
MSG_GEN_ERROR = "An error occurred during image generation. Please check the bot's console for details or try again later."
MSG_NO_PROMPT = "Please provide a prompt! Example: `!paint generate a majestic dragon flying over a castle :: text, blurry`"
MSG_API_ERROR = "Could not connect to Forge API. Make sure Forge is running with `--api` enabled and the `FORGE_API_URL` in `config.py` is correct."

# --- TTS Message Strings ---
MSG_TTS_GENERATING = "Generating speech response... 🔊"
MSG_TTS_ERROR = "An error occurred during speech generation. The text response is still available above."
MSG_TTS_QUEUE_FULL = "TTS queue is currently full. Please try again in a moment."