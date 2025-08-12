### **Jules's Art Bot: User Guide**

Welcome! This bot uses Stable Diffusion Forge to generate images based on your prompts. Here’s how to use it.

#### **1. Generating an Image**

The main command is `!paint generate`. It has aliases to control the shape (aspect ratio) of your image.

*   **`!paint generate <your prompt>`**
    *   Creates a **square** image.

*   **`!paint generateport <your prompt>`**
    *   Creates a tall **portrait** image.

*   **`!paint generateland <your prompt>`**
    *   Creates a wide **landscape** image.

#### **2. Command Options (Flags)**

You can add optional flags to the beginning of your command to control the generation. **Flags must come before your prompt.**

*   **`--upscale`**
    *   This enables Hires.fix, which generates a higher-resolution image with more detail.

*   **`--seed <number>`** or **`--seed=<number>`**
    *   This forces the generation to use a specific seed number, which is useful for recreating an image.

#### **3. Using Negative Prompts**

To tell the bot what you *don't* want to see in the image, use a double colon `::` to separate your main (positive) prompt from your negative prompt.

*   **Format:** `... [positive prompt] :: [negative prompt]`
*   **Example:** `!paint generate a cat in space :: dog, blurry`

#### **4. Prompting Tips**

To get the best results, keep these tips in mind:

*   **No Need for Quality Tags:** The bot automatically adds common quality tags like `detailed, masterpiece, best quality` to your positive prompt, and tags like `bad quality, worst quality, ugly` to your negative prompt. You don't need to write these yourself!
*   **Focus on the Content:** Since the quality tags are handled for you, you can focus your prompt on the subject and style. Be descriptive!
*   **Negative Prompts are Powerful:** Use the negative prompt (`::`) to remove things you don't want. For example, if you're getting extra limbs, add `mutated hands, extra fingers, extra limbs` to your negative prompt.

#### **5. Putting It All Together: Full Example**

You can combine all these elements into one command.

`!paint generateland --upscale --seed=12345 a beautiful cinematic landscape of a mountain lake :: ugly, boring, text, watermark`

This command will:
*   Create a **landscape** image.
*   Use the **upscaler** for high detail.
*   Use the specific **seed** `12345`.
*   Try to create a `beautiful cinematic landscape...`
*   ...while avoiding anything `ugly, boring, text, watermark` (in addition to the standard negative tags).

#### **6. Interactive Buttons**

After an image is generated, you will see buttons underneath it.

*   **[Upscale]**
    *   This button appears on images that were not generated with `--upscale`.
    *   Clicking it will rerun the exact same prompt and seed, but with the upscaler enabled to add more detail.

*   **[🗑️ Delete]**
    *   This button appears on all images.
    *   It allows you to delete the image post.
    *   This can only be clicked by the user who originally requested the image or by a server moderator.
