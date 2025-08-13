# bot.py

import logging
# Configure logging for more detailed console output
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')


import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio # For asynchronous operations
import io
import datetime
from zoneinfo import ZoneInfo

# Import our custom modules
from config import (
    DISCORD_TOKEN_NAME, COMMAND_PREFIX, FORGE_API_URL, TXT2IMG_ENDPOINT,
    DEFAULT_STEPS, DEFAULT_CFG_SCALE, DEFAULT_SAMPLER_NAME, DEFAULT_SEED, DEFAULT_MODEL,
    DEFAULT_CLIP_SKIP,
    RESOLUTIONS, DEFAULT_RESOLUTION_PRESET,
    FORBIDDEN_NEGATIVE_TERMS,
    BASE_POSITIVE_PROMPT, BASE_NEGATIVE_PROMPT,
    # --- NO HIRES.FIX IMPORTS HERE ---
    # --- ADETAILER IMPORTS ---
    ADETAILER_ENABLED_BY_DEFAULT, ADETAILER_DETECTION_MODEL,
    ADETAILER_PROMPT, ADETAILER_NEGATIVE_PROMPT,
    ADETAILER_CONFIDENCE, ADETAILER_MASK_BLUR, ADETAILER_INPAINT_DENOISING, ADETAILER_INPAINT_ONLY_MASKED,
    ADETAILER_INPAINT_PADDING,
    MSG_INVALID_RES, MSG_RES_SET,
    # MSG_UPSCALE_ENABLED, MSG_UPSCALE_DISABLED, # Removed, as !upscale command is gone
    MSG_GENERATING, MSG_GEN_ERROR, MSG_NO_PROMPT, MSG_API_ERROR,
    # --- NEW CHAT IMPORTS ---
    KOBOLDCPP_API_URL, CHARACTER_NAME, CHARACTER_PERSONA, CONTEXT_TOKEN_LIMIT,
    PAINT_CHANNEL_IDS, CHAT_CHANNEL_IDS, ALLOWED_CATEGORY_IDS
)
from forge_api import ForgeAPIClient
from kobold_api import KoboldAPIClient

# Load environment variables from .env file
load_dotenv()

# --- Bot Initialization ---
DISCORD_TOKEN = os.getenv(DISCORD_TOKEN_NAME)
if not DISCORD_TOKEN:
    print(f"Error: {DISCORD_TOKEN_NAME} environment variable not set.")
    print(f"Please create a .env file with {DISCORD_TOKEN_NAME}=YOUR_BOT_TOKEN")
    exit()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- Global Bot State (These will hold our current settings) ---
current_width = RESOLUTIONS[DEFAULT_RESOLUTION_PRESET]["width"]
current_height = RESOLUTIONS[DEFAULT_RESOLUTION_PRESET]["height"]
current_preset_name = DEFAULT_RESOLUTION_PRESET

# 'enable_upscale' is no longer needed as Hires.fix is removed and not user-toggleable
# If you want to control ADetailer on/off, use ADETAILER_ENABLED_BY_DEFAULT directly.

forge_api = ForgeAPIClient(base_url=FORGE_API_URL)
kobold_api = KoboldAPIClient(base_url=KOBOLDCPP_API_URL)

# --- Global Chat State ---
chat_histories = {} # key: user_id, value: list of messages
listening_channels = {} # {channel_id: asyncio.Task}

# --- Helper Functions ---

def get_token_count(text: str) -> int:
    """
    Approximates the number of tokens in a string.
    A common approximation is 1 token ~ 4 characters.
    """
    return len(text) // 4


async def listening_timer(channel: discord.TextChannel):
    """
    Manages the 30-minute timer for listen mode in a specific channel.
    Sends a warning at 29 minutes and deactivates after 30.
    """
    try:
        await asyncio.sleep(29 * 60)  # 29 minutes

        warning_message = (
            f"**Attention:** Listen mode will automatically turn off in 60 seconds. "
            f"Type `!listen` to reset the timer for another 30 minutes."
        )
        await channel.send(warning_message)

        await asyncio.sleep(60)  # Final 60 seconds

        # If the task reached this point without being cancelled, deactivate listen mode.
        if channel.id in listening_channels:
            del listening_channels[channel.id]
            if channel.id in chat_histories:
                del chat_histories[channel.id]
                logging.info(f"Chat history for channel {channel.id} has been cleared.")
            await channel.send("**Listen mode has been deactivated. Chat history for this session has been cleared.**")
            logging.info(f"Listen mode deactivated for channel {channel.id}.")

    except asyncio.CancelledError:
        # This happens when the timer is reset by the !listen command.
        # We can just log it and let the task end gracefully.
        logging.info(f"Listen mode timer for channel {channel.id} was cancelled (likely reset).")
        pass
    except Exception as e:
        logging.error(f"An error occurred in the listening timer for channel {channel.id}: {e}")
        # Ensure cleanup happens even if there's an unexpected error
        if channel.id in listening_channels:
            del listening_channels[channel.id]


def clean_negative_prompt(user_negative_prompt: str) -> str:
    """
    Adjusts the user-provided negative prompt by removing forbidden terms.
    This ensures distasteful content is less likely to be generated.
    """
    cleaned_prompt = user_negative_prompt
    for term in FORBIDDEN_NEGATIVE_TERMS:
        cleaned_prompt = cleaned_prompt.replace(term, "", -1).replace(term.capitalize(), "", -1)
        cleaned_prompt = cleaned_prompt.replace(term.upper(), "", -1)
    cleaned_prompt = " ".join(cleaned_prompt.split()).strip()
    return cleaned_prompt

# --- NEW CHECK FUNCTION ---
def is_allowed_channel():
    """Custom check to ensure commands are only run in allowed paint channels."""
    async def predicate(ctx):
        logging.info(f"DEBUG: Command '{ctx.command.name}' issued in channel ID: {ctx.channel.id}")
        logging.info(f"DEBUG: Paint channel IDs from config: {PAINT_CHANNEL_IDS}")
        if not PAINT_CHANNEL_IDS:
            logging.info("DEBUG: PAINT_CHANNEL_IDS is empty, allowing all channels (no restriction).")
            return True
        if ctx.channel.id in PAINT_CHANNEL_IDS:
            logging.info(f"DEBUG: Channel {ctx.channel.id} IS in paint channel list. Allowing command.")
            return True
        else:
            logging.warning(f"DEBUG: Channel {ctx.channel.id} is NOT in paint channel list. Denying command.")
            await ctx.send(f"Sorry, {ctx.author.mention}, I can only use paint commands in specific channels.")
            return False
    return commands.check(predicate)

# --- Bot Events ---

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f'Bot connected as {bot.user}!')
    print(f'Bot ID: {bot.user.id}')
    print(f'Using Forge API at: {forge_api.base_url}')
    print(f'Current default resolution: {current_width}x{current_height} ({current_preset_name})')
    # 'Upscaling enabled' print statement removed as there's no global Hires.fix state now
    print('--------------------------')
    await bot.change_presence(activity=discord.Game(name=f"Generating art with {COMMAND_PREFIX}generate"))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # 1. Prioritize standard commands to prevent hijacking by mention logic
    if message.content.startswith(COMMAND_PREFIX):
        await bot.process_commands(message)
        return

    # Define the full list of channels where any chat can happen
    all_chat_channels = PAINT_CHANNEL_IDS + CHAT_CHANNEL_IDS
    command_trigger = "!" + CHARACTER_NAME.lower()

    # 2. Handle !stop command to manually deactivate listen mode
    if message.content.lower() == '!stop':
        if message.channel.id in listening_channels:
            task = listening_channels[message.channel.id]
            task.cancel()
            # The timer's finally block will also delete the key, but we do it here for immediate effect.
            if message.channel.id in listening_channels:
                del listening_channels[message.channel.id]
            if message.channel.id in chat_histories:
                del chat_histories[message.channel.id]
                logging.info(f"Chat history for channel {message.channel.id} has been cleared due to !stop.")
            await message.channel.send("**Listen mode has been manually deactivated. Chat history for this session has been cleared.**")
            logging.info(f"Listen mode manually deactivated for channel {message.channel.id}.")
        return

    # 3. Handle !listen command to reset the timer
    if message.content.lower() == '!listen':
        if message.channel.id in listening_channels:
            old_task = listening_channels[message.channel.id]
            old_task.cancel()

            new_task = asyncio.create_task(listening_timer(message.channel))
            listening_channels[message.channel.id] = new_task

            await message.channel.send("Listen mode timer has been reset for another 30 minutes.")
            logging.info(f"Listen mode timer reset for channel {message.channel.id}.")
        return

    # 4. Handle chat logic
    is_direct_chat = message.content.lower().startswith(command_trigger + " ")
    is_mention_in_listen_mode = (message.channel.id in listening_channels and
                                 CHARACTER_NAME.lower() in message.content.lower())

    if is_direct_chat or is_mention_in_listen_mode:
        is_allowed = (message.channel.id in all_chat_channels or
                      (message.channel.category and message.channel.category.id in ALLOWED_CATEGORY_IDS))
        if not is_allowed:
            return

        # Activate or reset the timer whenever a direct chat command is used
        if is_direct_chat:
            if message.channel.id in listening_channels:
                listening_channels[message.channel.id].cancel()

            task = asyncio.create_task(listening_timer(message.channel))
            listening_channels[message.channel.id] = task
            # We don't send a message here to keep the chat flow clean, but log it.
            logging.info(f"Listen mode activated/reset by direct chat in channel {message.channel.id}.")

        user_message = message.content[len(command_trigger):].strip() if is_direct_chat else message.content

        if not user_message:
            return

        # Inject date/time if requested
        if 'date' in user_message.lower() or 'time' in user_message.lower():
            try:
                chicago_tz = ZoneInfo("America/Chicago")
                now = datetime.datetime.now(tz=chicago_tz)
                time_str = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
                user_message = f"[Current Time: {time_str}] {user_message}"
            except Exception as e:
                logging.error(f"Could not get timezone-aware time: {e}")
                # Fallback to simple time if zoneinfo fails for any reason
                now = datetime.datetime.now()
                time_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
                user_message = f"[Current Time: {time_str}] {user_message}"

        # Sliding window and prompt construction logic
        channel_id = message.channel.id
        if channel_id not in chat_histories:
            chat_histories[channel_id] = []

        history = chat_histories[channel_id]

        current_turn_text = f"<start_of_turn>user\n{message.author.display_name}: {user_message}<end_of_turn>"
        persona_text = f"You are {CHARACTER_NAME}. {CHARACTER_PERSONA}\n\n"

        tokens_used = get_token_count(persona_text + current_turn_text)

        history_conversation = []
        for msg in reversed(history):
            # This is part of the next plan step, but I'll do it here. It needs the user_name from this step.
            user_prefix = f"{msg['user_name']}: " if msg['user_name'] != CHARACTER_NAME else ""
            msg_text = f"<start_of_turn>{'model' if msg['user_name'] == CHARACTER_NAME else 'user'}\n{user_prefix}{msg['text']}<end_of_turn>"
            msg_tokens = get_token_count(msg_text)

            if tokens_used + msg_tokens > CONTEXT_TOKEN_LIMIT:
                break

            history_conversation.insert(0, msg_text)
            tokens_used += msg_tokens

        full_prompt = persona_text + "\n".join(history_conversation) + "\n" + current_turn_text + "\n<start_of_turn>model\n"

        response_text = await asyncio.to_thread(kobold_api.generate_text, full_prompt)

        if response_text:
            history.append({"user_name": message.author.display_name, "text": user_message})
            history.append({"user_name": CHARACTER_NAME, "text": response_text})
            await message.channel.send(response_text)
        else:
            await message.channel.send("Sorry, I couldn't get a response from the character.")
        return

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for commands."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Oops! You're missing an argument. Usage: `{COMMAND_PREFIX}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"That wasn't quite right. Please check your arguments for `{COMMAND_PREFIX}{ctx.command.name}`.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        print(f"An unhandled error occurred in command {ctx.command}: {error}")
        await ctx.send(MSG_GEN_ERROR)

# --- Bot Commands ---

@bot.command(name="res", help="Sets the image resolution. Choices: portrait, landscape, square.")
@is_allowed_channel()
async def set_resolution(ctx, preset: str):
    """
    Allows users to set one of the predefined image resolutions.
    Example: !paint res portrait
    """
    global current_width, current_height, current_preset_name

    preset = preset.lower()
    if preset in RESOLUTIONS:
        current_width = RESOLUTIONS[preset]["width"]
        current_height = RESOLUTIONS[preset]["height"]
        current_preset_name = preset
        await ctx.send(MSG_RES_SET.format(width=current_width, height=current_height, preset=current_preset_name))
    else:
        await ctx.send(MSG_INVALID_RES)

# The !upscale command has been removed
# @bot.command(name="upscale", help="Toggles upscaling (Hires. fix) for generated images.")
# @is_allowed_channel()
# async def toggle_upscale(ctx):
#     """
#     Toggles Hires. fix (upscaling) on or off.
#     Note: When enabled, specific upscaling settings from config.py are used.
#     """
#     global enable_upscale
#     enable_upscale = not enable_upscale
#
#     if enable_upscale:
#         await ctx.send(MSG_UPSCALE_ENABLED)
#     else:
#         await ctx.send(MSG_UPSCALE_DISABLED)

@bot.command(name="generate", help="Generates an image using Stable Diffusion Forge. When prompting first describe the setting, then naturally describe the picture, and finally add any specific tags separated by commas. adding :: after this allows you to add negative prompts as well.")
@is_allowed_channel()
async def generate_image(ctx, *, full_user_prompt: str):
    """
    Generates an image based on a positive and optional negative prompt.
    Usage: !paint generate [user_positive_prompt] [:: optional_user_negative_prompt]
    Example: !paint generate a cute cat in space :: ugly, blurry
    """
    if not full_user_prompt.strip():
        await ctx.send(MSG_NO_PROMPT)
        return

    user_positive_part = ""
    user_negative_part = ""

    if "::" in full_user_prompt:
        parts = full_user_prompt.split("::", 1)
        user_positive_part = parts[0].strip()
        user_negative_part = parts[1].strip()
    else:
        user_positive_part = full_user_prompt.strip()

    final_positive_prompt = f"{BASE_POSITIVE_PROMPT}, {user_positive_part}"
    final_positive_prompt = final_positive_prompt.strip(", ").replace(",,", ",").strip()

    combined_negative_prompt = f"{user_negative_part}, {BASE_NEGATIVE_PROMPT}"
    combined_negative_prompt = combined_negative_prompt.strip(", ").replace(",,", ",").strip()

    cleaned_final_negative_prompt = clean_negative_prompt(combined_negative_prompt)

    await ctx.send(MSG_GENERATING)
    logging.info(f"User '{ctx.author}' requested generation.")
    logging.info(f"Positive (final): '{final_positive_prompt}'")
    logging.info(f"Negative (final & cleaned): '{cleaned_final_negative_prompt}'")
    logging.info(f"Resolution: {current_width}x{current_height}")
    # 'Upscaling enabled' logging removed as Hires.fix is no longer controlled by bot
    logging.info(f"ADetailer enabled by default: {ADETAILER_ENABLED_BY_DEFAULT}") # Added logging for ADetailer

    # --- Construct the payload for Forge API with ADetailer only ---
    payload = {
        "prompt": final_positive_prompt,
        "negative_prompt": cleaned_final_negative_prompt,
        "steps": DEFAULT_STEPS,
        "cfg_scale": DEFAULT_CFG_SCALE,
        "sampler_name": DEFAULT_SAMPLER_NAME,
        "seed": DEFAULT_SEED,
        "width": current_width,
        "height": current_height,
        "clip_skip": DEFAULT_CLIP_SKIP,
        "override_settings": {
            "sd_model_checkpoint": DEFAULT_MODEL
        },
        "alwayson_scripts": {} # Initialize alwayson_scripts dictionary
    }

    # Hires.fix parameters removed

    # Add ADetailer parameters if enabled (which is controlled by config.py now)
    if ADETAILER_ENABLED_BY_DEFAULT:
        payload["alwayson_scripts"]["ADetailer"] = {
            "args": [
                { # First ADetailer pass settings
                    "ad_model": ADETAILER_DETECTION_MODEL,
                    "ad_prompt": ADETAILER_PROMPT,
                    "ad_negative_prompt": ADETAILER_NEGATIVE_PROMPT,
                    "ad_confidence": ADETAILER_CONFIDENCE,
                    "ad_mask_blur": ADETAILER_MASK_BLUR,
                    "ad_denoising_strength": ADETAILER_INPAINT_DENOISING,
                    "ad_inpaint_only_masked": ADETAILER_INPAINT_ONLY_MASKED,
                    "ad_inpaint_padding": ADETAILER_INPAINT_PADDING,

                    # --- Common ADetailer parameters often required by API, even if defaults ---
                    "ad_cfg_scale": DEFAULT_CFG_SCALE,
                    "ad_steps": DEFAULT_STEPS,
                    "ad_sampler": DEFAULT_SAMPLER_NAME,
                    "ad_clip_skip": 1, # ADetailer specific clip skip, usually 1
                    "ad_checkpoint": "", # Changed to empty string ""
                    "ad_vae": "", # Changed to empty string ""
                    "ad_use_inpaint_width_height": False,
                    "ad_inpaint_width": current_width,
                    "ad_inpaint_height": current_height
                }
            ]
        }

    response_from_api = await asyncio.to_thread(forge_api.txt2img, payload)

    # The API may return a tuple (image, infotext). We only need the image.
    if isinstance(response_from_api, tuple) and len(response_from_api) > 0:
        image = response_from_api[0]
    else:
        image = response_from_api

    if image:
        with io.BytesIO() as image_binary:
            image.save(image_binary, 'PNG')
            image_binary.seek(0)
            file_name = f"generated_image_{os.urandom(4).hex()}.png"
            discord_file = discord.File(fp=image_binary, filename=file_name)
            await ctx.send(f"Here's your image, {ctx.author.mention}!", file=discord_file)
            logging.info(f"Image sent for '{ctx.author}'.")
    else:
        await ctx.send(MSG_GEN_ERROR)
        logging.error("Failed to get image from Forge API.")

# --- Chat Commands ---

@bot.command(name="clearchat", help="Clears the chat history for this channel.")
@is_allowed_channel()
async def clearchat(ctx):
    """
    Clears the chat history for the current channel.
    """
    channel_id = ctx.channel.id
    if channel_id in chat_histories:
        del chat_histories[channel_id]
        await ctx.send("The chat history for this channel has been cleared.")
    else:
        await ctx.send("There is no chat history for this channel to clear.")

# --- Run the Bot ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)