# Web-Forge Discord Bot

This is a multi-purpose Discord bot that integrates with several local AI backends to provide a rich set of features, including image generation, AI-powered chat, and Text-to-Speech (TTS).

## Core Features

*   **AI Image Generation**: Generate high-quality images using a local Stable Diffusion Forge instance. Supports different aspect ratios, upscaling, custom seeds, and negative prompts.
*   **AI Chat**: Engage in conversation with an AI persona (`Gemma`). The bot can be triggered by direct command or by mentioning its name.
*   **Text-to-Speech (TTS)**: Bring the AI's responses to life! When requested, the bot will generate audio for its chat responses using a local Kokoro-TTS installation.
*   **User Profiles**: Users can set a personal profile that provides additional context to the AI during conversations.
*   **Automatic Service Management**: The bot can start and stop the Forge and KoboldCpp backends directly from Discord, and includes idle-timers to automatically shut them down when not in use.
*   **Web Search**: The AI can perform web searches to answer questions about recent events or specific topics it doesn't have in its knowledge base.

## Setup & Installation

1.  **Prerequisites**:
    *   Python 3.10+
    *   A local installation of [Stable Diffusion Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge).
    *   A local installation of [KoboldCpp](https://github.com/LostRuins/koboldcpp).
    *   A local installation of [Kokoro-TTS-Local](https://github.com/PierrunoYT/Kokoro-TTS-Local).

2.  **Configuration**:
    *   Clone this repository.
    *   Place your `Kokoro-TTS-Local` installation into a subdirectory of the same name within this project.
    *   Create a `.env` file in the root directory and add your Discord bot token and SerpApi key:
        ```
        DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
        SERPAPI_API_KEY=YOUR_SERPAPI_KEY_HERE
        ```
    *   Review `config.py` and update all settings, especially the launch paths for Forge and KoboldCpp, to match your environment.

3.  **Installation**:
    ```bash
    # Create and activate a virtual environment
    python -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # .\venv\Scripts\activate  # On Windows

    # Install dependencies
    pip install -r requirements.txt
    ```

4.  **Running the Bot**:
    ```bash
    python bot.py
    ```

## Full User Guide

For detailed information on all commands and features, please see the [USER_GUIDE.md](USER_GUIDE.md) file.
