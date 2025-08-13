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
    STATS_FILE, GENERATION_TIERS,
    DEFAULT_STEPS, DEFAULT_CFG_SCALE, DEFAULT_SAMPLER_NAME, DEFAULT_SEED, DEFAULT_MODEL,
    DEFAULT_CLIP_SKIP, RESOLUTIONS, FORBIDDEN_NEGATIVE_TERMS,
    BASE_POSITIVE_PROMPT, BASE_NEGATIVE_PROMPT,
    ADETAILER_ENABLED_BY_DEFAULT, ADETAILER_DETECTION_MODEL, ADETAILER_PROMPT,
    ADETAILER_NEGATIVE_PROMPT, ADETAILER_CONFIDENCE, ADETAILER_MASK_BLUR,
    ADETAILER_INPAINT_DENOISING, ADETAILER_INPAINT_ONLY_MASKED, ADETAILER_INPAINT_PADDING,
    HIRES_UPSCALER, HIRES_STEPS, HIRES_DENOISING, HIRES_UPSCALE_BY,
    HIRES_RESIZE_WIDTH, HIRES_RESIZE_HEIGHT,
    MSG_GENERATING, MSG_GEN_ERROR, MSG_NO_PROMPT, MSG_API_ERROR,
    KOBOLDCPP_API_URL, CHARACTER_NAME, CHARACTER_PERSONA, CONTEXT_TOKEN_LIMIT
)
from forge_api import ForgeAPIClient
from kobold_api import KoboldAPIClient

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
user_stats = {} # In-memory cache for user generation stats
chat_histories = {} # key: channel_id, value: list of messages
listening_channels = {} # {channel_id: asyncio.Task}

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
            "hr_sampler": "Euler a", "hr_resize_x": HIRES_RESIZE_WIDTH,
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

# --- Bot Events ---

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    global user_stats
    user_stats = load_stats()
    print(f'Bot connected as {bot.user}!')
    print(f'Loaded stats for {len(user_stats)} users.')
    print(f'Using Forge API at: {forge_api.base_url}')
    print(f'Using KoboldCpp API at: {kobold_api.base_url}')
    await bot.change_presence(activity=discord.Game(name=f"Art & Chat"))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Define the full list of channels where any chat can happen
    all_chat_channels = PAINT_CHANNEL_IDS + CHAT_CHANNEL_IDS

    # Handle Image Attachments for Gemma
    if message.attachments:
        attachment = message.attachments[0]
        if "image" in attachment.content_type:

            is_allowed = (message.channel.id in all_chat_channels or
                          (message.channel.category and message.channel.category.id in ALLOWED_CATEGORY_IDS))
            if not is_allowed:
                return

            try:
                await message.add_reaction("🤔")

                image_bytes = await attachment.read()
                base64_image = base64.b64encode(image_bytes).decode('utf-8')

                # The new endpoint does not use the text prompt, only the image.
                response_text = await asyncio.to_thread(
                    kobold_api.interrogate_image,
                    base64_image=base64_image
                )

                await message.remove_reaction("🤔", bot.user)

                if response_text:
                    await message.channel.send(response_text)
                else:
                    await message.channel.send("Sorry, I couldn't interpret that image.")

            except Exception as e:
                logging.error(f"Error processing image attachment: {e}")
                await message.channel.send("Sorry, an error occurred while processing the image.")

            return # Stop further processing after handling the image

    # 1. Prioritize standard commands to prevent hijacking by mention logic
    if message.content.startswith(COMMAND_PREFIX):
        await bot.process_commands(message)
        return

    command_trigger = "!" + CHARACTER_NAME.lower()

    # 2. Handle !stop command to manually deactivate listen mode
    if message.content.lower() == '!stop':
        if message.channel.id in listening_channels:
            task = listening_channels.pop(message.channel.id)
            task.cancel()
            if message.channel.id in chat_histories:
                del chat_histories[message.channel.id]
            await message.channel.send("**Listen mode has been manually deactivated. Chat history for this session has been cleared.**")
        return

    # 3. Handle !listen command to reset the timer
    if message.content.lower() == '!listen':
        if message.channel.id in listening_channels:
            listening_channels[message.channel.id].cancel()

        listening_channels[message.channel.id] = bot.loop.create_task(listening_timer(message.channel))
        await message.channel.send("Listen mode timer has been reset for another 30 minutes.")
        return

    # 4. Handle chat logic
    if message.content.lower() == command_trigger:
        # If the user just types the trigger word, respond with the greeting
        await message.channel.send(config.CHARACTER_GREETING)
        return

    is_direct_chat = message.content.lower().startswith(command_trigger + " ")
    is_mention_in_listen_mode = (message.channel.id in listening_channels and
                                 CHARACTER_NAME.lower() in message.content.lower())

    if is_direct_chat or is_mention_in_listen_mode:
        is_allowed = (message.channel.id in all_chat_channels or
                      (message.channel.category and message.channel.category.id in ALLOWED_CATEGORY_IDS))
        if not is_allowed:
            return

        if is_direct_chat:
            if message.channel.id in listening_channels:
                listening_channels[message.channel.id].cancel()
            listening_channels[message.channel.id] = bot.loop.create_task(listening_timer(message.channel))
            logging.info(f"Listen mode activated/reset by direct chat in channel {message.channel.id}.")

        user_message = message.content[len(command_trigger):].strip() if is_direct_chat else message.content
        if not user_message: return

        if 'date' in user_message.lower() or 'time' in user_message.lower():
            try:
                chicago_tz = ZoneInfo("America/Chicago")
                now = datetime.datetime.now(tz=chicago_tz)
                time_str = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
                user_message = f"[Current Time: {time_str}] {user_message}"
            except Exception as e:
                logging.error(f"Could not get timezone-aware time: {e}")
                now = datetime.datetime.now()
                time_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
                user_message = f"[Current Time: {time_str}] {user_message}"

        channel_id = message.channel.id
        if channel_id not in chat_histories:
            chat_histories[channel_id] = []
        history = chat_histories[channel_id]

        current_turn_text = f"<start_of_turn>user\n{message.author.display_name}: {user_message}<end_of_turn>"
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

            if len(response_text) <= 2000:
                await message.channel.send(response_text)
            else: # Handle long messages
                for i in range(0, len(response_text), 1990):
                    await message.channel.send(response_text[i:i + 1990])
                    await asyncio.sleep(1)
        else:
            await message.channel.send("Sorry, I couldn't get a response from the character.")
        return

@bot.event
async def on_command_error(ctx, error):
    """A global error handler for all bot commands."""
    if isinstance(error, commands.CommandNotFound) or isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Oops! You forgot the prompt. Usage: `{COMMAND_PREFIX}{ctx.command.name} [options] <prompt>`")
    else:
        await ctx.send(MSG_GEN_ERROR)
        logging.error(f"An unhandled error occurred in command {ctx.command}: {error}", exc_info=True)

# --- Bot Commands ---

@bot.command(name="generate", aliases=["generateport", "generateland"],
             help="Generates an image. Aliases: generateport, generateland.")
@is_allowed_paint_channel()
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

@bot.command(name="clearchat", help="Clears the chat history for this channel.")
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