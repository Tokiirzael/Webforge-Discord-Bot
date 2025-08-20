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

import re
from web_search import perform_search, scrape_website_text

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
    KOBOLDCPP_IDLE_TIMEOUT_MINUTES,
    # TTS Settings
    MAX_CONCURRENT_TTS, TTS_TIMEOUT, MSG_TTS_GENERATING, MSG_TTS_ERROR, MSG_TTS_QUEUE_FULL,
    # New Forge settings
    FORGE_IDLE_TIMEOUT_MINUTES
)
from forge_api import ForgeAPIClient
from kobold_api import KoboldAPIClient
from kokoro_api import KokoroTTSClient
import process_manager
import kobold_process_manager

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

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
forge_api = ForgeAPIClient()
kobold_api = KoboldAPIClient(base_url=KOBOLDCPP_API_URL)
kokoro_api = KokoroTTSClient()

user_stats = {} # In-memory cache for user generation stats
chat_histories = {} # key: channel_id, value: list of messages
listening_channels = {} # {channel_id: asyncio.Task}
last_forge_use_time = None
forge_idle_task = None
last_kobold_use_time = None
kobold_idle_task = None

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
            ctx, text = await tts_queue.get()
            
            if ctx is None:  # Shutdown signal
                break
                
            try:
                # Generate the speech
                await ctx.channel.send(MSG_TTS_GENERATING, delete_after=10)
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
                            
                            await ctx.channel.send(
                                f"🔊 **Audio response for {ctx.author.mention}:**", 
                                file=discord_file
                            )
                        
                        logging.info(f"TTS audio sent successfully for user {ctx.author}")
                    else:
                        await ctx.channel.send(MSG_TTS_ERROR)
                        logging.error("TTS file was generated but not found on disk")
                else:
                    await ctx.channel.send(MSG_TTS_ERROR)
                    logging.error("TTS generation failed")
                    
            except asyncio.TimeoutError:
                await ctx.channel.send("Speech generation timed out. The text response is still available above.")
                logging.error(f"TTS generation timed out for user {ctx.author}")
            except Exception as e:
                await ctx.channel.send(MSG_TTS_ERROR)
                logging.error(f"Error during TTS processing: {e}")
            finally:
                # Mark this task as done
                tts_queue.task_done()
                
        except Exception as e:
            logging.error(f"Critical error in TTS queue processor: {e}")
            # Continue processing other requests
            continue
    
    tts_processing = False

async def add_to_tts_queue(ctx, text):
    """Adds a TTS request to the queue if there's room."""
    if tts_queue.qsize() >= MAX_CONCURRENT_TTS:
        await ctx.channel.send(MSG_TTS_QUEUE_FULL, delete_after=10)
        return False
    
    await tts_queue.put((ctx, text))
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

# --- Agentic Web Search Logic ---

async def summarize_and_answer_with_persona(original_prompt: str, scraped_content: str, source_url: str):
    """
    Formats a prompt that instructs the AI to act as its persona while answering a question
    based on scraped web content, and to cite its source.
    """
    # We need to make sure we don't exceed the token limit. Let's reserve half the context for scraped text.
    max_context_len = CONTEXT_TOKEN_LIMIT // 2
    truncated_text = scraped_content[:max_context_len]

    # Construct the new prompt, incorporating the character's persona
    new_prompt = (
        f"You are {CHARACTER_NAME}. {CHARACTER_PERSONA}\n\n"
        f"A user has asked you a question, and you have gathered information from a webpage to answer it. "
        f"Your task is to synthesize the information from the 'Webpage Content' section and use it to answer the 'User's original question' in your own words, while staying in character. "
        f"At the end of your response, you MUST cite your source in the format: \"Source: [URL]\"\n\n"
        f"---\n"
        f"User's original question: \"{original_prompt}\"\n\n"
        f"Source URL: {source_url}\n\n"
        f"Webpage Content:\n{truncated_text}\n"
        f"---\n\n"
        f"Now, provide your answer:"
    )

    # Use the existing kobold_api client to generate the text
    final_answer = await asyncio.to_thread(kobold_api.generate_text, new_prompt)
    return final_answer


# --- UI Components ---

class GenerationView(discord.ui.View):
    """
    A view that holds the state of a generation and contains the action buttons.
    """
    def __init__(self, original_ctx, prompt, seed, preset_name, is_upscaled: bool):
        super().__init__(timeout=3600) # 1-hour timeout for the buttons
        self.original_ctx = original_ctx
        self.prompt = prompt
        self.seed = seed
        self.preset_name = preset_name

        # The "Upscale" and "Rerun" buttons should not be shown if the image is already an upscale.
        if is_upscaled:
            self.upscale_button.disabled = True
            self.upscale_button.style = discord.ButtonStyle.secondary
            self.rerun_button.disabled = True

    async def on_timeout(self):
        # When the view times out, disable all components
        for item in self.children:
            item.disabled = True
        # Update the original message to reflect the disabled state
        await self.message.edit(view=self)

    @discord.ui.button(label="Upscale", style=discord.ButtonStyle.primary)
    async def upscale_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback for the upscale button."""
        # Acknowledge the click immediately
        await interaction.response.send_message(f"Upscaling image for {interaction.user.mention}...", ephemeral=True)

        # Disable the button after it's clicked
        button.disabled = True
        button.label = "Upscaled"
        await self.message.edit(view=self)

        # Call the generation function with the stored parameters, but force upscale=True
        await _generate_image(
            ctx=self.original_ctx,
            prompt=self.prompt,
            preset_name=self.preset_name,
            upscale=True,
            seed=self.seed
        )

    @discord.ui.button(label="Rerun", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def rerun_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback for the rerun button."""
        await interaction.response.send_message(f"Rerunning prompt for {interaction.user.mention} with a new seed...", ephemeral=True)

        # Call the generation function with the same prompt but a random seed
        await _generate_image(
            ctx=self.original_ctx,
            prompt=self.prompt,
            preset_name=self.preset_name,
            upscale=False, # A rerun is not an upscale
            seed=-1 # Use a random seed
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback for the delete button."""

        # Check for permissions
        is_original_author = interaction.user.id == self.original_ctx.author.id
        # Get the user's roles, check if any of them are in the moderator list
        is_moderator = any(role.id in MODERATOR_ROLE_IDS for role in interaction.user.roles)

        if not is_original_author and not is_moderator:
            await interaction.response.send_message("You don't have permission to delete this.", ephemeral=True)
            return

        # If permission check passes, delete the message.
        await self.message.delete()
        await interaction.response.send_message("Image deleted.", ephemeral=True)

async def _generate_image(ctx, prompt: str, preset_name: str, upscale: bool, seed: int = None):
    """Prepares the payload and calls the Forge API to generate an image."""
    # First, check if the Forge API is online
    if not forge_api.is_online():
        await ctx.send(f"Sorry, the image generation service appears to be offline. Please use the `{COMMAND_PREFIX}start` command to start it.")
        return

    if not prompt:
        await ctx.send(MSG_NO_PROMPT)
        return

    resolution = RESOLUTIONS.get(preset_name, {})
    width, height = resolution.get("width"), resolution.get("height")
    if not width or not height:
        logging.error(f"Invalid resolution preset '{preset_name}' used.")
        await ctx.send("An internal error occurred with resolution settings.")
        return

    # Split the prompt into positive and negative parts
    user_positive, user_negative = (p.strip() for p in prompt.split("::", 1)) if "::" in prompt else (prompt, "")

    final_positive_prompt = f"{BASE_POSITIVE_PROMPT}, {user_positive}".strip(", ")
    combined_negative_prompt = f"{user_negative}, {BASE_NEGATIVE_PROMPT}".strip(", ")
    final_negative_prompt = clean_negative_prompt(combined_negative_prompt)

    generation_seed = seed if seed is not None else DEFAULT_SEED

    # --- Construct the main payload for the Forge API ---
    payload = {
        "prompt": final_positive_prompt, "negative_prompt": final_negative_prompt,
        "steps": DEFAULT_STEPS, "cfg_scale": DEFAULT_CFG_SCALE,
        "sampler_name": DEFAULT_SAMPLER_NAME, "seed": generation_seed,
        "width": width, "height": height, "clip_skip": DEFAULT_CLIP_SKIP,
        "override_settings": {"sd_model_checkpoint": DEFAULT_MODEL},
        "alwayson_scripts": {}
    }

    # If --upscale is used, add the Hires.fix script settings
    if upscale:
        payload["alwayson_scripts"]["img2img hires fix"] = {"args": [{"hr_upscaler": HIRES_UPSCALER, "hr_second_pass_steps": HIRES_STEPS, "denoising_strength": HIRES_DENOISING, "hr_scale": HIRES_UPSCALE_BY, "hr_sampler": "Euler a", "hr_resize_x": HIRES_RESIZE_WIDTH, "hr_resize_y": HIRES_RESIZE_HEIGHT}]}

    # If ADetailer is enabled in the config, add its script settings
    if ADETAILER_ENABLED_BY_DEFAULT:
        payload["alwayson_scripts"]["ADetailer"] = {"args": [{"ad_model": ADETAILER_DETECTION_MODEL, "ad_prompt": ADETAILER_PROMPT, "ad_negative_prompt": ADETAILER_NEGATIVE_PROMPT, "ad_confidence": ADETAILER_CONFIDENCE, "ad_mask_blur": ADETAILER_MASK_BLUR, "ad_denoising_strength": ADETAILER_INPAINT_DENOISING, "ad_inpaint_only_masked": ADETAILER_INPAINT_ONLY_MASKED, "ad_inpaint_padding": ADETAILER_INPAINT_PADDING}]}

    # --- Send request and handle response ---
    await ctx.send(f"{MSG_GENERATING} (`{preset_name}`)")
    logging.info(f"User '{ctx.author}' request: Upscale={upscale}, Seed={generation_seed}, Prompt='{prompt}'")

    image, info_json = await asyncio.to_thread(forge_api.txt2img, payload)

    if image and info_json:
        global last_forge_use_time
        last_forge_use_time = datetime.datetime.now()

        # --- Stat Tracking ---
        user_id_str = str(ctx.author.id)
        user_stats[user_id_str] = user_stats.get(user_id_str, 0) + 1
        save_stats(user_stats)

        generation_count = user_stats[user_id_str]
        user_title = get_user_title(generation_count)

        # --- Message Formatting ---
        try:
            info_data = json.loads(info_json)
            final_seed = info_data.get("seed", "unknown")
        except json.JSONDecodeError:
            final_seed = "unknown"

        # Build the response string
        response_parts = []
        if user_title:
            response_parts.append(f"Title: {user_title}")
        response_parts.append(f"Generation #{generation_count}")
        response_parts.append(f"Seed: `{final_seed}`")

        response_text = f"Here's your image, {ctx.author.mention}! ({' | '.join(response_parts)})"

        with io.BytesIO() as image_binary:
            image.save(image_binary, 'PNG')
            image_binary.seek(0)
            discord_file = discord.File(fp=image_binary, filename=f"seed_{final_seed}.png")

            view = GenerationView(
                original_ctx=ctx,
                prompt=prompt,
                seed=final_seed,
                preset_name=preset_name,
                is_upscaled=upscale
            )

            message = await ctx.send(response_text, file=discord_file, view=view)
            view.message = message # Store message for view timeout

            logging.info(f"Image sent for '{ctx.author}'. Seed: {final_seed}, Total Gens: {generation_count}")
    else:
        await ctx.send(MSG_GEN_ERROR)
        logging.error("Failed to get image from Forge API.")

# --- Chat Response Generation ---
async def generate_chat_response(message, user_message: str):
    """Generates a chat response using the same logic as the existing chat system."""
    global last_kobold_use_time
    last_kobold_use_time = datetime.datetime.now()
    
    if 'date' in user_message.lower() or 'time' in user_message.lower():
        # Timezone detection
        tz_name = "America/Chicago" # Default timezone
        import re
        for tz_key, tz_value in TIMEZONE_MAP.items():
            # \b ensures we match whole words only
            if re.search(r'\b' + re.escape(tz_key) + r'\b', user_message, re.IGNORECASE):
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

# --- Bot Events ---

async def forge_idle_check():
    """A background task to automatically shut down Forge after a period of inactivity."""
    await bot.wait_until_ready()

    status_channel = None
    # A channel to post status messages to. Let's try to find a valid one.
    if PAINT_CHANNEL_IDS:
        try:
            status_channel = await bot.fetch_channel(PAINT_CHANNEL_IDS[0])
        except (discord.NotFound, discord.Forbidden):
            print(f"Could not fetch status channel {PAINT_CHANNEL_IDS[0]}. Idle shutdown messages will not be sent.")

    while not bot.is_closed():
        await asyncio.sleep(60) # Check every minute

        if process_manager.is_forge_running() and last_forge_use_time is not None:
            # Check if timeout is enabled in config
            if FORGE_IDLE_TIMEOUT_MINUTES > 0:
                idle_duration = datetime.datetime.now() - last_forge_use_time
                if idle_duration.total_seconds() > FORGE_IDLE_TIMEOUT_MINUTES * 60:
                    print(f"Forge has been idle for over {FORGE_IDLE_TIMEOUT_MINUTES} minutes. Shutting down.")
                    if status_channel:
                        await status_channel.send(f"Forge has been idle for {FORGE_IDLE_TIMEOUT_MINUTES} minutes. Shutting down to save resources. Use `!paint start` to restart it.")
                    process_manager.stop_forge()

async def kobold_idle_check():
    """A background task to automatically shut down KoboldCpp after a period of inactivity."""
    await bot.wait_until_ready()

    status_channel = None
    if CHAT_CHANNEL_IDS:
        try:
            status_channel = await bot.fetch_channel(CHAT_CHANNEL_IDS[0])
        except (discord.NotFound, discord.Forbidden):
            print(f"Could not fetch status channel {CHAT_CHANNEL_IDS[0]}. Idle shutdown messages will not be sent.")

    while not bot.is_closed():
        await asyncio.sleep(60) # Check every minute

        if kobold_process_manager.is_koboldcpp_running() and last_kobold_use_time is not None:
            if KOBOLDCPP_IDLE_TIMEOUT_MINUTES > 0:
                idle_duration = datetime.datetime.now() - last_kobold_use_time
                if idle_duration.total_seconds() > KOBOLDCPP_IDLE_TIMEOUT_MINUTES * 60:
                    print(f"KoboldCpp has been idle for over {KOBOLDCPP_IDLE_TIMEOUT_MINUTES} minutes. Shutting down.")
                    if status_channel:
                        await status_channel.send(f"The chat AI has been idle for {KOBOLDCPP_IDLE_TIMEOUT_MINUTES} minutes and is going dormant. Use `!gemma` to wake it up.")
                    kobold_process_manager.stop_koboldcpp()
                    chat_histories.clear()
                    logging.info("Chat history has been cleared due to inactivity.")

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    global user_stats, forge_idle_task, kobold_idle_task
    user_stats = load_stats()
    logging.info(f'Logged in as {bot.user}')
    if not tts_processing:
        bot.loop.create_task(process_tts_queue())
        logging.info("TTS queue processor started.")
    if forge_idle_task is None:
        forge_idle_task = bot.loop.create_task(forge_idle_check())
        logging.info("Forge idle check task started.")
    if kobold_idle_task is None:
        kobold_idle_task = bot.loop.create_task(kobold_idle_check())
        logging.info("KoboldCpp idle check task started.")
    await bot.change_presence(activity=discord.Game(name=f"Art & Chat"))

@bot.event
async def on_shutdown():
    """Event that runs when the bot is shutting down."""
    await tts_queue.put((None, None))  # Send shutdown signal (ctx, text)
    logging.info("TTS queue shutdown signal sent.")
    await asyncio.sleep(1)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # 1. Prioritize command processing above all else.
    # This will handle all commands decorated with @bot.command()
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # 2. If it's not a command, then process it as a potential chat message.
    all_chat_channels = PAINT_CHANNEL_IDS + CHAT_CHANNEL_IDS
    is_allowed_channel = (message.channel.id in all_chat_channels or (message.channel.category and message.channel.category.id in ALLOWED_CATEGORY_IDS))

    if not is_allowed_channel:
        return

    # Handle image attachments with chat
    if message.attachments and "image" in message.attachments[0].content_type:
        # Let image analysis trigger a chat response, same as a name mention
        pass # Fall through to the chat logic below

    # Chat Triggers
    gemma_command_prefix = f"!{CHARACTER_NAME.lower()} "
    is_direct_chat_command = message.content.lower().startswith(gemma_command_prefix)
    is_mention = CHARACTER_NAME.lower() in message.content.lower()

    # If the message is a chat trigger (and not a different command)
    if not message.content.startswith("!") or is_direct_chat_command:
        if is_direct_chat_command or is_mention:
            # First, check if the Kobold API is online
            if not kobold_api.is_online():
                await message.channel.send(f"Sorry, the chat service is offline. Please use `!gemma` to start it.")
                return

            user_message = ""
            if is_direct_chat_command:
                user_message = message.content[len(gemma_command_prefix):].strip()
            else: # Is a mention
                user_message = message.content

            if not user_message and not message.attachments:
                return

            # Handle image analysis if an image is attached
            if message.attachments and "image" in message.attachments[0].content_type:
                try:
                    await message.add_reaction("🤔")
                    image_bytes = await message.attachments[0].read()
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    caption = await asyncio.to_thread(kobold_api.interrogate_image, base64_image=base64_image)
                    await message.remove_reaction("🤔", bot.user)
                    if not caption:
                        await message.channel.send("Sorry, I couldn't interpret that image.")
                        return

                    user_context = user_message or "What's in this image?"
                    # Prepend the image context to the user's message
                    user_message = f"{user_context}\n\n[Image Content: {caption}]"

                except Exception as e:
                    logging.error(f"Error processing image attachment: {e}")
                    await message.channel.send("Sorry, an error occurred while processing the image.")
                    return

            # Check for the new search trigger
            if CHARACTER_NAME.lower() in user_message.lower() and "search" in user_message.lower():
                # Extract a clean search query
                query = re.sub(f'{CHARACTER_NAME.lower()}|search', '', user_message, flags=re.IGNORECASE).strip()
                logging.info(f"User requested a web search for: '{query}'")
                await message.channel.send(f"🧠 Searching the web for `{query}`...")

                # Perform Search
                search_results = perform_search(query)
                if not search_results:
                    await message.channel.send("I tried to search the web, but my search came up empty.")
                    return

                # Scrape Top Result
                top_result_url = search_results[0].get('link')
                if not top_result_url:
                    await message.channel.send("I found search results, but I couldn't extract a valid link.")
                    return

                logging.info(f"Scraping content from URL: {top_result_url}")
                scraped_content = scrape_website_text(top_result_url)
                if not scraped_content:
                    await message.channel.send(f"I found a webpage ({top_result_url}), but I was unable to read its content.")
                    return

                # 4. Get Final Answer
                logging.info("Getting summarized answer from AI based on scraped content.")
                final_answer = await summarize_and_answer_with_persona(query, scraped_content, top_result_url)

                if final_answer:
                    if len(final_answer) <= 2000:
                        await message.channel.send(final_answer)
                    else:
                        # Handle long messages
                        for i in range(0, len(final_answer), 1990):
                            await message.channel.send(final_answer[i:i + 1990])
                            await asyncio.sleep(1)
                else:
                    await message.channel.send("I found information on the web, but I had trouble summarizing it.")

            else:
                # We have a valid prompt, now get the response
                initial_response = await generate_chat_response(message, user_message)

                if initial_response:
                    if len(initial_response) <= 2000:
                        await message.channel.send(initial_response)
                    else:
                        # Handle long messages
                        for i in range(0, len(initial_response), 1990):
                            await message.channel.send(initial_response[i:i + 1990])
                            await asyncio.sleep(1)

                    # Only generate speech if the user's original message contained "speak"
                    if "speak" in user_message.lower():
                        await add_to_tts_queue(message, initial_response)
                else:
                    await message.channel.send("Sorry, I couldn't get a response from the character.")
            return

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound) or isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Oops! You forgot the prompt. Usage: `{COMMAND_PREFIX}{ctx.command.name} [options] <prompt>`")
    else:
        await ctx.send(MSG_GEN_ERROR)
        logging.error(f"An unhandled error occurred in command {ctx.command}: {error}", exc_info=True)

# --- Bot Commands ---

@bot.group(name="paint", invoke_without_command=True)
async def paint(ctx):
    """Base command for all paint-related commands."""
    await ctx.send_help(ctx.command)

@paint.command(name="generate", aliases=["generateport", "generateland"], help="Generates an image. Aliases: generateport, generateland.")
@is_allowed_paint_channel()
async def generate(ctx, *, full_prompt_string: str):
    """
    The main command for generating images. It supports different presets based on the alias used
    and can parse arguments like --upscale and --seed from the prompt string.
    """
    try:
        # Separate the command-line style args from the actual prompt text
        args, cleaned_prompt = parse_generate_args(full_prompt_string)
    except ValueError as e:
        await ctx.send(f"Error parsing arguments: {e}. Please check your command format.")
        return

    # Determine which resolution preset to use based on the command alias (e.g., !paint generateland)
    invoked_command = ctx.invoked_with.lower()
    preset_name = "square" # Default
    if invoked_command == "generateport":
        preset_name = "portrait"
    elif invoked_command == "generateland":
        preset_name = "landscape"

    # Call the main image generation logic
    await _generate_image(
        ctx,
        prompt=cleaned_prompt,
        preset_name=preset_name,
        upscale=args.get('upscale', False), # Use upscale if the arg was found
        seed=args.get('seed') # Use the specified seed, or None if not found
    )

@paint.command(name="clearchat", help="Clears the chat history for this channel.")
async def clearchat(ctx):
    channel_id = ctx.channel.id
    if channel_id in chat_histories:
        del chat_histories[channel_id]
        await ctx.send("The chat history for this channel has been cleared.")
    else:
        await ctx.send("There is no chat history for this channel to clear.")

@paint.command(name="setprofile", help="Sets your user profile for the chatbot.")
async def setprofile(ctx, *, profile_text: str):
    """Saves or updates a user's profile text."""
    if not profile_text:
        await ctx.send("Please provide some text for your profile. Example: `!paint setprofile A friendly artist from Canada.`")
        return
    try:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        file_path = os.path.join(PROFILE_DIR, f"{ctx.author.id}.txt")
        file_content = f"[[ {profile_text} ]]"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
        await ctx.send(f"Your profile has been saved, {ctx.author.mention}!")
        logging.info(f"Saved profile for user {ctx.author.id}")
    except Exception as e:
        logging.error(f"Failed to save profile for user {ctx.author.id}: {e}")
        await ctx.send("Sorry, there was an error saving your profile.")

@paint.command(name="viewprofile", help="View your current user profile.")
async def viewprofile(ctx):
    """Displays the user's current profile to them privately."""
    try:
        file_path = os.path.join(PROFILE_DIR, f"{ctx.author.id}.txt")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                profile_content = f.read()
            await ctx.send(f"Here is your current profile, {ctx.author.mention}:\n```\n{profile_content}\n```", ephemeral=True)
        else:
            await ctx.send("You don't have a profile set up yet. Use `!paint setprofile <text>` to create one.", ephemeral=True)
    except Exception as e:
        logging.error(f"Failed to view profile for user {ctx.author.id}: {e}")
        await ctx.send("Sorry, there was an error retrieving your profile.", ephemeral=True)

@bot.command(name="gemma", help="Starts the KoboldCPP service.")
async def gemma(ctx):
    """Starts the KoboldCpp service and the idle timer."""
    global last_kobold_use_time, kobold_idle_task
    if kobold_process_manager.is_koboldcpp_running():
        if kobold_api.is_online():
            await ctx.send("The KoboldCPP service is already running.")
        else:
            await ctx.send("The KoboldCPP service is starting, but not yet online. Please wait a moment.")
        return

    await ctx.send("🚀 Starting the KoboldCPP service... This may take a few minutes.")

    success = await asyncio.to_thread(kobold_process_manager.start_koboldcpp)
    if not success:
        await ctx.send("❌ Failed to start the KoboldCPP service. Please check the bot's console for errors.")
        return

    # Now, wait for the API to become online
    await ctx.send("...KoboldCPP process started. Waiting for the API to become responsive...")

    online = False
    for i in range(24): # Wait up to 2 minutes
        await asyncio.sleep(5)
        if kobold_api.is_online():
            online = True
            break

    if online:
        last_kobold_use_time = datetime.datetime.now()
        # Start the idle check task if it's not already running
        if kobold_idle_task is None or kobold_idle_task.done():
            kobold_idle_task = bot.loop.create_task(kobold_idle_check())
            logging.info("KoboldCpp idle check task started.")
        await ctx.send(f"✅ The KoboldCPP service is now online and ready to use! It will go dormant after {KOBOLDCPP_IDLE_TIMEOUT_MINUTES} minutes of inactivity.")
    else:
        await ctx.send("⚠️ The KoboldCPP service started but did not become responsive in time. It might be stuck or still loading.")

@bot.command(name="listen", help="Resets the 30-minute inactivity timer for the chat AI.")
async def listen(ctx):
    """Resets the inactivity timer for KoboldCpp."""
    global last_kobold_use_time
    if kobold_process_manager.is_koboldcpp_running():
        last_kobold_use_time = datetime.datetime.now()
        await ctx.send("✅ Chat AI inactivity timer has been reset for another 30 minutes.")
    else:
        await ctx.send("The chat AI is not currently running. Use `!gemma` to start it.")

@bot.command(name="stop", help="Manually stops the KoboldCpp service.")
async def stop(ctx):
    """Manually stops the KoboldCpp service and the idle timer."""
    global kobold_idle_task
    if kobold_process_manager.is_koboldcpp_running():
        await ctx.send("🛑 Stopping the KoboldCPP service...")
        await asyncio.to_thread(kobold_process_manager.stop_koboldcpp)
        if kobold_idle_task and not kobold_idle_task.done():
            kobold_idle_task.cancel()
        chat_histories.clear()
        logging.info("Chat history has been cleared by manual stop command.")
        await ctx.send("✅ The KoboldCPP service has been stopped and chat history is cleared.")
    else:
        await ctx.send("The KoboldCPP service is not currently running.")

@bot.command(name="deleteprofile", help="Deletes your user profile.")
async def deleteprofile(ctx):
    """Deletes the user's profile file."""
    try:
        file_path = os.path.join(PROFILE_DIR, f"{ctx.author.id}.txt")
        if os.path.exists(file_path):
            os.remove(file_path)
            await ctx.send(f"Your profile has been deleted, {ctx.author.mention}.")
            logging.info(f"Deleted profile for user {ctx.author.id}")
        else:
            await ctx.send("You don't have a profile to delete.", ephemeral=True)
    except Exception as e:
        logging.error(f"Failed to delete profile for user {ctx.author.id}: {e}")
        await ctx.send("Sorry, there was an error deleting your profile.")

# --- Service Management Commands ---
@paint.command(name="start", help="Starts the Forge backend service.")
async def start_service(ctx):
    if process_manager.is_forge_running():
        await ctx.send("The Forge service is already running.")
        return

    await ctx.send("🚀 Starting the Forge service... This may take a few minutes.")

    success = await asyncio.to_thread(process_manager.start_forge)
    if not success:
        await ctx.send("❌ Failed to start the Forge service. Please check the bot's console for errors.")
        return

    # Now, wait for the API to become online
    await ctx.send("...Forge process started. Waiting for the API to become responsive...")

    online = False
    for i in range(24): # Wait up to 2 minutes (24 * 5 seconds)
        await asyncio.sleep(5)
        if forge_api.is_online():
            online = True
            break

    if online:
        await ctx.send("✅ The Forge service is now online and ready to use!")
    else:
        await ctx.send("⚠️ The Forge service started but did not become responsive in time. It might be stuck or still loading.")


@paint.command(name="stop", help="Stops the Forge backend service.")
async def stop_service(ctx):
    if not process_manager.is_forge_running():
        await ctx.send("The Forge service is not currently running.")
        return

    await ctx.send("🛑 Stopping the Forge service...")
    await asyncio.to_thread(process_manager.stop_forge)
    await ctx.send("✅ The Forge service has been stopped.")


# --- Run the Bot ---
if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    finally:
        logging.info("Bot is shutting down.")
        