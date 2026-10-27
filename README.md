# Whisper Telegram Bot

A small **self-hosted Telegram voice-to-text bot** for Linux, powered by [whisper.cpp](https://github.com/ggml-org/whisper.cpp). No cloud transcription API, no GPU and no Docker required. Send a voice message or audio file to your Telegram bot; Whisper runs **on your computer** and returns the transcript.

**How it works:** Telegram → download to your Linux machine → `ffmpeg` → `whisper-cli` (local inference) → transcript returned via Telegram → delete temporary job directory.

> Telegram still handles the message and audio transfer. Telegram bot chats are **not end-to-end encrypted**. Your computer must be turned on and connected to the internet for the bot to receive/send messages. The speech model itself can run offline.

## Supported features

- Telegram voice messages and files: MP3, WAV, OGG/OPUS, FLAC, M4A, AAC, WEBM, MP4 and others supported by ffmpeg
- Multilingual recognition, including Russian and English
- Short texts directly in chat; long transcripts attached as `.txt`
- One recognition task at a time to avoid overwhelming the CPU
- Private bot: choose a fixed owner ID or opt in to first-`/start` claiming during setup
- Downloads into `~/Downloads/audiofiles/bot-<random-id>/` and removes **only the task folder**, not the whole `audiofiles` directory
- Existing Whisper model can be reused: no duplication or retraining

## Installation on Arch Linux

### 1. System dependencies

```bash
sudo pacman -Syu --needed python python-pip ffmpeg whisper-cpp curl git
```

Check the binary is available:

```bash
command -v whisper-cli
command -v ffmpeg
```

The Arch `whisper-cpp` package supplies `whisper-cli`. For other Linux distributions, [build whisper.cpp from source](https://github.com/ggml-org/whisper.cpp#quick-start) and ensure `whisper-cli` is in `PATH`.

### 2. Download a local speech recognition model

**Whisper Small multilingual** is a practical starting point for CPU-only computers. Download it once (~466 MiB):

```bash
mkdir -p ~/.local/share/whisper/models
curl -fL https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin \
  -o ~/.local/share/whisper/models/ggml-small.bin
```

If you **already downloaded this file**, skip this step. This is the **model**, not the bot: it does the actual speech-to-text conversion on your CPU. Once downloaded, inference does not require an internet connection.

Optional: you can use another whisper.cpp-compatible GGML model. Put its file on disk and set `WHISPER_MODEL` in `.env` to its absolute path.

### 3. Download this bot

```bash
git clone https://github.com/nyaxiom/whisper-telegram-bot.git
cd whisper-telegram-bot
```

The repository already contains `bin/transcribe`: no need to create a separate command in `~/.local/bin`.

### 4. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather), send `/newbot` and create your bot.
2. Copy the **bot token**. Do not share or commit it.
3. Optionally find your numeric Telegram user ID (not your username). You only need it for fixed-owner mode.

**You do not need to create `.env` manually.** The first `./run.sh` will ask for the token (hidden input) and then offer two choices:

- **1 — Fixed owner (recommended):** enter your numeric Telegram user ID, so only that account may use the bot.
- **2 — First user claims bot:** whoever sends `/start` first becomes the owner, permanently for this bot on this computer. **This can be a stranger.** Only choose it when you can claim the bot immediately; never share the bot's link before claiming it.

After you finish setup, credentials are stored in `.env` with file permissions `0600`. This file is ignored by Git. Subsequent launches use it without asking again. The first user's ID is persisted under `~/.local/state/whisper-telegram-bot/` in a separate directory derived from the bot token, so restarting does not reset ownership.

**Manual/non-interactive alternative:**

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

For a fixed owner, set `BOT_TOKEN`, `OWNER_MODE=fixed`, and `TELEGRAM_USER_ID=your_numeric_id`. For first-user claiming, set `OWNER_MODE=first` (the numeric ID can remain blank). A fake placeholder token cannot start a real bot.

**Optional settings** (uncomment in `.env` only if needed):

| Variable | Default | Purpose |
| --- | --- | --- |
| `WHISPER_MODEL` | `~/.local/share/whisper/models/ggml-small.bin` | Path to your Whisper GGML model |
| `WHISPER_LANGUAGE` | `auto` | Auto-detect, or use `ru`/`en` |
| `WHISPER_THREADS` | `8` | Number of whisper.cpp CPU threads |
| `AUDIO_DIR` | `~/Downloads/audiofiles` | Temporary downloads folder |

### 5. Start the bot

```bash
./run.sh
```

On first run, the script asks for your bot token and ownership method and saves `.env`. It then creates `.venv` and installs the Python dependencies from `requirements.txt` (internet required for initial installation). Next, it starts long polling Telegram.

Open **your new bot** in Telegram and send `/start`. Then send a voice message or audio file. The bot replies with the recognized text, or sends a TXT file for long recordings.

Stop it with **Ctrl+C**. The bot only responds while this terminal process is running and your computer has internet access. You don't need a VPS or to train a model.

### 6. Use the same speech model in the terminal (without Telegram)

```bash
./bin/transcribe ~/Downloads/example.mp3
```

A `~/Downloads/example.txt` file will appear. This command works offline after installing the model. It is also the exact script the bot calls internally.

### 7. Test and troubleshoot

```bash
# Verify the model file exists
ls -lh ~/.local/share/whisper/models/ggml-small.bin

# Test conversion without Telegram
./bin/transcribe ~/Downloads/example.mp3

# Restart the bot after editing .env
./run.sh
```

- **Missing model:** Download the model in step 2 or set `WHISPER_MODEL` to an existing absolute path.
- **Missing `whisper-cli`:** Install `whisper-cpp` or put the built binary on `PATH`.
- **Private bot / access denied:** In fixed-owner mode, check `TELEGRAM_USER_ID`. In first-user mode, only the account that claimed the bot with `/start` may use it. The saved owner ID is located under `~/.local/state/whisper-telegram-bot/<token-hash>/owner_id`. Do not delete it unless you deliberately want to reset ownership.
- **File too large:** Telegram's hosted Bot API normally only allows bots to download files up to **20 MB**. Compress or split larger audio recordings before sending.
- **Slow processing:** CPU-only recognition can take some time, especially for long files. Try another model or adjust `WHISPER_THREADS`.
- **Multiple instances:** Don't run more than one instance with the same bot token while using long polling.
- **Cleanup:** Only uniquely named per-job folders are deleted. If the process crashes or is killed abruptly, unfinished files may remain in `~/Downloads/audiofiles/`; inspect them before removing them manually.

## Project structure

```text
whisper-telegram-bot/
├── bot.py                 # Telegram handlers, ownership, and transcription
├── setup.py               # Interactive first-launch setup (stdlib only)
├── bin/transcribe         # Audio conversion and local whisper.cpp CLI wrapper
├── run.sh                 # Creates Python venv, installs dependencies, runs bot
├── requirements.txt       # Python libraries
├── .env.example           # Optional template for manual setup
├── .gitignore             # Prevents publishing tokens, weights, files, .venv
├── LICENSE                # MIT
└── README.md
```

## Safety & privacy

- `BOT_TOKEN` must stay in **`.env`**; never put it in `bot.py` or a public commit. If leaked, revoke and regenerate it using BotFather.
- Fixed-owner mode requires `TELEGRAM_USER_ID`. First-user mode is explicitly opt-in and can be claimed by anyone who sends `/start` first. Claim as soon as possible.
- To change your settings, stop the bot and edit `.env`, or delete `.env` to rerun the wizard. Deleting `.env` does **not** remove the saved first-owner ID. Switching tokens starts a separate owner record.
- Files are downloaded from Telegram, transcribed locally with `whisper.cpp`, and transcript text goes back through Telegram. No OpenAI API is called.
- Only per-job directories are cleaned; existing files in `~/Downloads/audiofiles` are not touched.
- The bot does not persist transcripts, but Telegram may store messages and your computer may retain logs/leftovers after an abrupt crash.

## License

MIT for this bot's code. [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and model files are separate third-party components with their own licensing terms.
