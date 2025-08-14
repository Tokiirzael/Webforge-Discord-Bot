# Web-Forge Discord Bot - User Guide

This guide provides detailed information on how to use all the features of the Web-Forge Discord Bot.

## Table of Contents
1.  [Image Generation](#image-generation)
2.  [Chatting with the AI](#chatting-with-the-ai)
3.  [Text-to-Speech (TTS)](#text-to-speech-tts)
4.  [User Profiles](#user-profiles)

---

## 1. Image Generation

The core feature of the bot is generating images using Stable Diffusion Forge.

### Basic Commands

The bot's command prefix is `!paint `.

*   `!paint generate <prompt>`
    *   Generates a **square** image (e.g., 1024x1024).

*   `!paint generateport <prompt>`
    *   Generates a **portrait** image (e.g., 1024x1520).

*   `!paint generateland <prompt>`
    *   Generates a **landscape** image (e.g., 1520x1024).

### Prompting Techniques

*   **Negative Prompts**: To add a negative prompt, use `::` to separate it from your main prompt.
    *   *Example*: `!paint generate a beautiful cat :: blurry, ugly`

*   **Arguments**: You can add special arguments to your prompt for more control.
    *   `--upscale`: Enables Hires.fix for the generation, resulting in a larger, more detailed image.
    *   `--seed=<number>`: Sets a specific seed for the generation, allowing you to reproduce an image.

    *   *Full Example*: `!paint generateport --upscale --seed=12345 a cat in space :: dog, blurry`

### Interactive Buttons

After an image is generated, it will appear with a set of buttons:

*   **Upscale**: Reruns the generation with Hires.fix enabled to create a larger, more detailed version. This button is disabled if the image was already upscaled.
*   **Rerun (🔄)**: Reruns the same prompt with a new random seed to get a different image.
*   **Delete (🗑️)**: Deletes the bot's message containing the image. This can be used by the original author of the prompt or by a server moderator.

---

## 2. Chatting with the AI

You can have conversations with the bot's AI persona, "Gemma".

### Activating Chat

There are two ways to talk to Gemma:

1.  **Direct Command**: Start your message with `!gemma <your message>`. This will activate "listen mode" in the channel for 30 minutes, meaning the bot will respond to subsequent messages that mention its name.
    *   *Example*: `!gemma Hello, how are you today?`

2.  **Listen Mode**: A user can type `!listen` to activate listen mode for 30 minutes. During this time, any message that contains the word "gemma" will trigger a response.
    *   Typing `!listen` again will reset the timer.
    *   Typing `!stop` will immediately deactivate listen mode.

### Image Interrogation

If you upload an image and mention Gemma (or use the `!gemma` command with your message), the bot will attempt to describe the image and respond to your message in context.

---

## 3. Text-to-Speech (TTS)

You can make Gemma's responses audible using Text-to-Speech.

### Triggering TTS

To have a chat response read aloud, simply include the word **speak** in your message to the bot.

*   *Example*: `!gemma speak Tell me a story.`
*   *Example (in listen mode)*: `gemma can you speak your reply?`

The bot will generate the audio and post it as a `.wav` file in the channel.

---

## 4. User Profiles

You can set a user profile to give Gemma more context about who you are, leading to more personalized conversations.

### Profile Commands

*   `!paint setprofile <text>`
    *   Creates or updates your personal profile. The bot will store this text and use it to inform its chat responses.
    *   *Example*: `!paint setprofile I am a friendly artist from Canada who loves dragons.`

*   `!paint viewprofile`
    *   The bot will send you a private (ephemeral) message showing your currently saved profile.

*   `!paint deleteprofile`
    *   Permanently deletes your user profile.
