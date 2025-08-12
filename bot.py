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

# Import our custom modules
from config import (
    DISCORD_TOKEN_NAME, COMMAND_PREFIX, FORGE_API_URL, TXT2IMG_ENDPOINT,
    ALLOWED_CHANNEL_IDS,
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
    MSG_GENERATING, MSG_GEN_ERROR, MSG_NO_PROMPT, MSG_API_ERROR
)
from forge_api import ForgeAPIClient

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

# --- Helper Functions for Prompts ---
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
    """Custom check to ensure commands are only run in allowed channels."""
    async def predicate(ctx):
        logging.info(f"DEBUG: Command '{ctx.command.name}' issued in channel ID: {ctx.channel.id}")
        logging.info(f"DEBUG: Allowed channel IDs from config: {ALLOWED_CHANNEL_IDS}")
        if not ALLOWED_CHANNEL_IDS:
            logging.info("DEBUG: ALLOWED_CHANNEL_IDS is empty, allowing all channels (no restriction).")
            return True
        if ctx.channel.id in ALLOWED_CHANNEL_IDS:
            logging.info(f"DEBUG: Channel {ctx.channel.id} IS in allowed list. Allowing command.")
            return True
        else:
            logging.warning(f"DEBUG: Channel {ctx.channel.id} is NOT in allowed list. Denying command.")
            await ctx.send(f"Sorry, {ctx.author.mention}, I can only respond to commands in specific channels. Please use one of the designated bot channels.")
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

    image = await asyncio.to_thread(forge_api.txt2img, payload)

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

# --- Run the Bot ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)