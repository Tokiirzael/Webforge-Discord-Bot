# bot.py

import logging
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import io
import json
import shlex
import argparse

import datetime
from zoneinfo import ZoneInfo
import base64

# Import settings from the config file
from config import (
    DISCORD_TOKEN_NAME, COMMAND_PREFIX, PAINT_CHANNEL_IDS, CHAT_CHANNEL_IDS, ALLOWED_CATEGORY_IDS,
    MODERATOR_ROLE_IDS, GENERATION_ROLE_ID,
    STATS_FILE, PROFILE_DIR, GENERATION_TIERS,
    DEFAULT_STEPS, DEFAULT_CFG_SCALE, DEFAULT_SAMPLER_NAME, DEFAULT_SEED, DEFAULT_MODEL,
    DEFAULT_CLIP_SKIP, RESOLUTIONS, FORBIDDEN_NEGATIVE_TERMS,
    BASE_POSITIVE_PROMPT, BASE_NEGATIVE_PROMPT,
    ADETAILER_ENABLED_BY_DEFAULT, ADETAILER_DETECTION_MODEL, ADETAILER_PROMPT,
    ADETAILER_NEGATIVE_PROMPT, ADETAILER_CONFIDENCE, ADETAILER_MASK_BLUR,
    ADETAILER_INPAINT_DENOISING, ADETAILER_INPAINT_ONLY_MASKED, ADETAILER_INPAINT_PADDING,
    HIRES_UPSCALER, HIRES_STEPS, HIRES_DENOISING, HIRES_UPSCALE_BY,
    HIRES_RESIZE_WIDTH, HIRES_RESIZE_HEIGHT,
    MSG_GENERATING, MSG_GEN_ERROR, MSG_NO_PROMPT, MSG_API_ERROR,
    KOBOLDCPP_API_URL, CHARACTER_NAME, CHARACTER_PERSONA, CONTEXT_TOKEN_LIMIT, CHARACTER_GREETING, TIMEZONE_MAP,
    # TTS Settings
    MAX_CONCURRENT_TTS, TTS_TIMEOUT, MSG_TTS_GENERATING, MSG_TTS_ERROR, MSG_TTS_QUEUE_FULL
)
from forge_api import ForgeAPIClient
from kobold_api import KoboldAPIClient
from kokoro_api import KokoroTTSClient

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')

# Load environment variables from a .env file
load_dotenv()

# --- Bot Initialization ---
DISCORD_TOKEN = os.getenv(DISCORD_TOKEN_NAME)
if not DISCORD_TOKEN:
    print(f"Error: {DISCORD_TOKEN_NAME} not found in environment variables.")
    exit()

# Define the bot's intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)
forge_api = ForgeAPIClient()
kobold_api = KoboldAPIClient(base_url=KOBOLDCPP_API_URL)
kokoro_api = KokoroTTSClient()

user_stats = {} # In-memory cache for user generation stats
chat_histories = {} # key: channel_id, value: list of messages
listening_channels = {} # {channel_id: asyncio.Task}

# --- TTS Queue System ---
tts_queue = asyncio.Queue()
tts_processing = False

async def process_tts_queue():
    """Processes TTS requests one at a time from the queue."""
    global tts_processing
    tts_processing = True
    
    while True:
        try:
            # Get the next TTS request from the queue
            tts_request = await tts_queue.get()
            
            if tts_request is None:  # Shutdown signal
                break
                
            ctx, text, original_message = tts_request
            
            try:
                # Generate the speech
                success = await asyncio.wait_for(
                    kokoro_api.generate_speech(text), 
                    timeout=TTS_TIMEOUT
                )
                
                if success:
                    # Send the audio file
                    audio_file_path = kokoro_api.get_output_file_path()
                    
                    if os.path.exists(audio_file_path):
                        with open(audio_file_path, 'rb') as audio_file:
                            discord_file = discord.File(
                                fp=audio_file, 
                                filename=f"gemma_speech.wav",
                                description="Gemma's voice response"
                            )
                            
                            await ctx.send(
                                f"🔊 **Audio response for {ctx.author.mention}:**", 
                                file=discord_file
                            )
                        
                        logging.info(f"TTS audio sent successfully for user {ctx.author}")
                    else:
                        await ctx.send(MSG_TTS_ERROR)
                        logging.error("TTS file was generated but not found on disk")
                else:
                    await ctx.send(MSG_TTS_ERROR)
                    logging.error("TTS generation failed")
                    
            except asyncio.TimeoutError:
                await ctx.send("Speech generation timed out. The text response is still available above.")
                logging.error(f"TTS generation timed out for user {ctx.author}")
            except Exception as e:
                await ctx.send(MSG_TTS_ERROR)
                logging.error(f"Error during TTS processing: {e}")
            finally:
                # Mark this task as done
                tts_queue.task_done()
                
        except Exception as e:
            logging.error(f"Critical error in TTS queue processor: {e}")
            # Continue processing other requests
            continue
    
    tts_processing = False

async def add_to_tts_queue(ctx, text, original_message):
    """Adds a TTS request to the queue if there's room."""
    if tts_queue.qsize() >= MAX_CONCURRENT_TTS * 3:  # Allow some buffer
        await ctx.send(MSG_TTS_QUEUE_FULL)
        return False
    
    await tts_queue.put((ctx, text, original_message))
    return True

# --- Helper Functions ---

def load_stats():
    """Loads user stats from the JSON file."""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_stats(stats_dict):
    """Saves the given stats dictionary to the JSON file."""
    with open(STATS_FILE, 'w') as f:
        json.dump(stats_dict, f, indent=4)

def parse_generate_args(prompt_string: str):
    """
    Parses command-line style arguments from the prompt string.
    Recognizes --upscale and --seed=<number>.
    """
    # Custom parser to avoid exiting the program on a parsing error
    class NonExitingArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError(message)

    parser = NonExitingArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--upscale', action='store_true')
    parser.add_argument('--seed', type=int)

    # shlex helps split the string while respecting quoted sections
    words = shlex.split(prompt_string)
    
    try:
        # Let argparse handle separating known args from the rest of the prompt
        namespace, prompt_words = parser.parse_known_args(words)
        parsed_args = vars(namespace)
    except (ValueError, argparse.ArgumentError) as e:
        # If parsing fails, assume the whole string was a prompt with no valid args
        logging.warning(f"Could not parse args, treating as full prompt. Details: {e}")
        parsed_args = {}
        prompt_words = words

    cleaned_prompt = ' '.join(prompt_words)
    return parsed_args, cleaned_prompt

def clean_negative_prompt(user_negative_prompt: str) -> str:
    """Removes forbidden terms from the user's negative prompt for safety."""
    cleaned_prompt = user_negative_prompt
    for term in FORBIDDEN_NEGATIVE_TERMS:
        cleaned_prompt = cleaned_prompt.replace(term, "", -1).replace(term.capitalize(), "", -1)
    return " ".join(cleaned_prompt.split()).strip()

def get_user_title(count: int) -> str:
    """Returns a user's title based on their generation count."""
    # The GENERATION_TIERS list is sorted from highest to lowest.
    # We iterate through it and return the first title the user qualifies for.
    for threshold, title in GENERATION_TIERS:
        if count >= threshold:
            return title
    return "" # Return an empty string if no tier is met

def get_token_count(text: str) -> int:
    """Approximates the number of tokens in a string (1 token ~ 4 chars)."""
    return len(text) // 4

async def listening_timer(channel: discord.TextChannel):
    """Manages the 30-minute timer for listen mode."""
    try:
        await asyncio.sleep(29 * 60)
        warning_message = (
            f"**Attention:** Listen mode will automatically turn off in 60 seconds. "
            f"Type `!listen` to reset the timer for another 30 minutes."
        )
        await channel.send(warning_message)
        await asyncio.sleep(60)

        if channel.id in listening_channels:
            del listening_channels[channel.id]
            if channel.id in chat_histories:
                del chat_histories[channel.id]
            await channel.send("**Listen mode has been deactivated. Chat history for this session has been cleared.**")
    except asyncio.CancelledError:
        logging.info(f"Listen mode timer for channel {channel.id} was cancelled (likely reset).")
    except Exception as e:
        logging.error(f"An error occurred in the listening timer for channel {channel.id}: {e}")
        if channel.id in listening_channels:
            del listening_channels[channel.id]

def is_allowed_paint_channel():
    """A custom check to ensure bot commands only run in specified paint channels."""
    async def predicate(ctx):
        if not PAINT_CHANNEL_IDS or ctx.channel.id in PAINT_CHANNEL_IDS:
            return True
        else:
            await ctx.send(f"Sorry, {ctx.author.mention}, you can only use me in paint channels.", ephemeral=True)
            return False
    return commands.check(predicate)

# --- Chat Response Generation ---
async def generate_chat_response(message, user_message: str):
    """Generates a chat response using the same logic as the existing chat system."""
    
    if 'date' in user_message.lower() or 'time' in user_message.lower():
        # Timezone detection
        tz_name = "America/Chicago" # Default timezone
        for tz_key, tz_value in TIMEZONE_MAP.items():
            if tz_key in user_message.lower():
                tz_name = tz_value
                break
        
        try:
            target_tz = ZoneInfo(tz_name)
            now = datetime.datetime.now(tz=target_tz)
            time_str = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
            # Add the timezone name to the injected prompt for clarity
            user_message = f"[Current Time in {tz_name.replace('_', ' ')}: {time_str}] {user_message}"
        except Exception as e:
            logging.error(f"Could not get timezone-aware time for {tz_name}: {e}")
            # Fallback for safety
            now = datetime.datetime.now()
            time_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
            user_message = f"[Current Time: {time_str}] {user_message}"

    channel_id = message.channel.id
    if channel_id not in chat_histories:
        chat_histories[channel_id] = []
    history = chat_histories[channel_id]

    # Check for and load user profile
    user_id = message.author.id
    profile_path = os.path.join(PROFILE_DIR, f"{user_id}.txt")
    user_profile_text = ""
    if os.path.exists(profile_path):
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                user_profile_text = f.read().strip()
        except Exception as e:
            logging.error(f"Could not read profile for user {user_id}: {e}")

    # Construct the user's turn, including profile if it exists
    if user_profile_text:
        user_turn_prompt = f"[User Profile for {message.author.display_name}: [[{user_profile_text}]]] {message.author.display_name}: {user_message}"
    else:
        user_turn_prompt = f"{message.author.display_name}: {user_message}"

    current_turn_text = f"<start_of_turn>user\n{user_turn_prompt}<end_of_turn>"
    persona_text = f"You are {CHARACTER_NAME}. {CHARACTER_PERSONA}\n\n"
    tokens_used = get_token_count(persona_text + current_turn_text)

    history_conversation = []
    for msg in reversed(history):
        user_prefix = f"{msg['user_name']}: " if msg['user_name'] != CHARACTER_NAME else ""
        msg_text = f"<start_of_turn>{'model' if msg['user_name'] == CHARACTER_NAME else 'user'}\n{user_prefix}{msg['text']}<end_of_turn>"
        msg_tokens = get_token_count(msg_text)
        if tokens_used + msg_tokens > CONTEXT_TOKEN_LIMIT: break
        history_conversation.insert(0, msg_text)
        tokens_used += msg_tokens

    full_prompt = persona_text + "\n".join(history_conversation) + "\n" + current_turn_text + "\n<start_of_turn>model\n"
    
    response_text = await asyncio.to_thread(kobold_api.generate_text, full_prompt)

    if response_text:
        history.append({"user_name": message.author.display_name, "text": user_message})
        history.append({"user_name": CHARACTER_NAME, "text": response_text})
        return response_text
    else:
        return None
        