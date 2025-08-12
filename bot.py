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

# Import settings from the config file
from config import (
    DISCORD_TOKEN_NAME, COMMAND_PREFIX, ALLOWED_CHANNEL_IDS, MODERATOR_ROLE_IDS, GENERATION_ROLE_ID,
    DEFAULT_STEPS, DEFAULT_CFG_SCALE, DEFAULT_SAMPLER_NAME, DEFAULT_SEED, DEFAULT_MODEL,
    DEFAULT_CLIP_SKIP, RESOLUTIONS, FORBIDDEN_NEGATIVE_TERMS,
    BASE_POSITIVE_PROMPT, BASE_NEGATIVE_PROMPT,
    ADETAILER_ENABLED_BY_DEFAULT, ADETAILER_DETECTION_MODEL, ADETAILER_PROMPT,
    ADETAILER_NEGATIVE_PROMPT, ADETAILER_CONFIDENCE, ADETAILER_MASK_BLUR,
    ADETAILER_INPAINT_DENOISING, ADETAILER_INPAINT_ONLY_MASKED, ADETAILER_INPAINT_PADDING,
    HIRES_UPSCALER, HIRES_STEPS, HIRES_DENOISING, HIRES_UPSCALE_BY,
    HIRES_RESIZE_WIDTH, HIRES_RESIZE_HEIGHT,
    MSG_GENERATING, MSG_GEN_ERROR, MSG_NO_PROMPT, MSG_API_ERROR
)
from forge_api import ForgeAPIClient

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

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
forge_api = ForgeAPIClient()

# --- Helper Functions ---

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

def check_permissions():
    """
    A custom check to ensure the user has the required roles and is in an allowed channel.
    """
    async def predicate(ctx):
        # Check 1: Channel check
        if ALLOWED_CHANNEL_IDS and ctx.channel.id not in ALLOWED_CHANNEL_IDS:
            await ctx.send(f"Sorry, {ctx.author.mention}, you can only use me in designated channels.", ephemeral=True)
            return False

        # Check 2: Role check
        user_roles = [role.id for role in ctx.author.roles]
        has_gen_role = GENERATION_ROLE_ID in user_roles
        has_mod_role = any(role_id in user_roles for role_id in MODERATOR_ROLE_IDS)

        if not has_gen_role and not has_mod_role:
            await ctx.send(f"Sorry, {ctx.author.mention}, you don't have the required role to generate images.", ephemeral=True)
            return False

        return True
    return commands.check(predicate)

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

        # The "Upscale" button should not be shown if the image is already an upscale.
        if is_upscaled:
            self.upscale_button.disabled = True
            self.upscale_button.style = discord.ButtonStyle.secondary

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
        payload["alwayson_scripts"]["img2img hires fix"] = {"args": [{
            "hr_upscaler": HIRES_UPSCALER, "hr_second_pass_steps": HIRES_STEPS,
            "denoising_strength": HIRES_DENOISING, "hr_scale": HIRES_UPSCALE_BY,
            "hr_sampler": "DPM++ 2M", "hr_resize_x": HIRES_RESIZE_WIDTH,
            "hr_resize_y": HIRES_RESIZE_HEIGHT,
        }]}

    # If ADetailer is enabled in the config, add its script settings
    if ADETAILER_ENABLED_BY_DEFAULT:
        payload["alwayson_scripts"]["ADetailer"] = {"args": [{
            "ad_model": ADETAILER_DETECTION_MODEL, "ad_prompt": ADETAILER_PROMPT,
            "ad_negative_prompt": ADETAILER_NEGATIVE_PROMPT, "ad_confidence": ADETAILER_CONFIDENCE,
            "ad_mask_blur": ADETAILER_MASK_BLUR, "ad_denoising_strength": ADETAILER_INPAINT_DENOISING,
            "ad_inpaint_only_masked": ADETAILER_INPAINT_ONLY_MASKED, "ad_inpaint_padding": ADETAILER_INPAINT_PADDING,
        }]}

    # --- Send request and handle response ---
    await ctx.send(f"{MSG_GENERATING} (`{preset_name}`)")
    logging.info(f"User '{ctx.author}' request: Upscale={upscale}, Seed={generation_seed}, Prompt='{prompt}'")

    image, info_json = await asyncio.to_thread(forge_api.txt2img, payload)

    if image and info_json:
        try:
            info_data = json.loads(info_json)
            final_seed = info_data.get("seed", "unknown")
        except json.JSONDecodeError:
            final_seed = "unknown"

        with io.BytesIO() as image_binary:
            image.save(image_binary, 'PNG')
            image_binary.seek(0)
            discord_file = discord.File(fp=image_binary, filename=f"seed_{final_seed}.png")

            # Create the view with the buttons
            view = GenerationView(
                original_ctx=ctx,
                prompt=prompt,
                seed=final_seed,
                preset_name=preset_name,
                is_upscaled=upscale
            )

            message = await ctx.send(
                f"Here's your image, {ctx.author.mention}! (Seed: `{final_seed}`)",
                file=discord_file,
                view=view
            )

            # Store the message object in the view so we can edit it later (e.g., on timeout)
            view.message = message

            logging.info(f"Image sent for '{ctx.author}'. Seed: {final_seed}")
    else:
        await ctx.send(MSG_GEN_ERROR)
        logging.error("Failed to get image from Forge API.")

# --- Bot Events ---

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f'Bot connected as {bot.user}!')
    print(f'Using Forge API at: {forge_api.base_url}')
    await bot.change_presence(activity=discord.Game(name=f"Art with {COMMAND_PREFIX}generate"))

@bot.event
async def on_command_error(ctx, error):
    """A global error handler for all bot commands."""
    if isinstance(error, commands.CommandNotFound) or isinstance(error, commands.CheckFailure):
        return # Ignore commands that don't exist or fail the channel check

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Oops! You forgot the prompt. Usage: `{COMMAND_PREFIX}{ctx.command.name} [options] <prompt>`")
    else:
        await ctx.send(MSG_GEN_ERROR)
        logging.error(f"An unhandled error occurred in command {ctx.command}: {error}", exc_info=True)

# --- Bot Commands ---

@bot.command(name="generate", aliases=["generateport", "generateland"],
             help="Generates an image. Aliases: generateport, generateland.")
@check_permissions()
async def generate(ctx, *, full_prompt_string: str):
    """Generates an image with a specified orientation and optional arguments.

    This command has three aliases that control the image's aspect ratio:
      - `!paint generate`: Creates a square image.
      - `!paint generateport`: Creates a portrait image.
      - `!paint generateland`: Creates a landscape image.

    You can also add arguments to control the generation:
      `--upscale`: Enables Hires.fix for this generation.
      `--seed=<number>`: Sets a specific seed.

    To provide a negative prompt, use `::` to separate it from the positive part.

    Full Example:
      `!paint generateport --upscale --seed=12345 a cat in space :: dog, blurry`
    """
    try:
        args, cleaned_prompt = parse_generate_args(full_prompt_string)
    except ValueError as e:
        await ctx.send(f"Error parsing arguments: {e}. Please check your command format.")
        return

    # Determine orientation from the specific command used (e.g., generateport)
    invoked_command = ctx.invoked_with.lower()
    preset_name = "square"
    if invoked_command == "generateport":
        preset_name = "portrait"
    elif invoked_command == "generateland":
        preset_name = "landscape"

    # Call the main generation function with the parsed arguments
    await _generate_image(
        ctx,
        prompt=cleaned_prompt,
        preset_name=preset_name,
        upscale=args.get('upscale', False),
        seed=args.get('seed')
    )

# --- Run the Bot ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)