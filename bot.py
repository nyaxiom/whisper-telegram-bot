#!/usr/bin/env python3
"""Private Telegram frontend for a locally running whisper.cpp transcription CLI."""

import asyncio
import logging
import hashlib
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = os.getenv("TELEGRAM_USER_ID", "").strip()
OWNER_MODE = os.getenv("OWNER_MODE", "fixed").strip()
# Separate state for each bot token; never saved inside the Git repository.
STATE_DIR = (
    Path.home()
    / ".local"
    / "state"
    / "whisper-telegram-bot"
    / hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:16]
)
OWNER_FILE = STATE_DIR / "owner_id"
AUDIO_DIR = Path(__file__).resolve().parent / "audiofiles"
MAX_BYTES = 20 * 1024 * 1024
SUPPORTED = {
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".m4a",
    ".aac",
    ".wma",
    ".webm",
    ".mp4",
}
logger = logging.getLogger(__name__)
processing_lock = asyncio.Lock()


def current_owner() -> int | None:
    if OWNER_MODE == "fixed":
        return int(OWNER_ID)
    try:
        return int(OWNER_FILE.read_text(encoding="ascii").strip())
    except FileNotFoundError:
        return None


async def authorized(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    if not user or not chat or chat.type != "private" or msg is None:
        return False
    owner = current_owner()
    if owner is None and OWNER_MODE == "first":
        if msg.text != "/start":
            await msg.reply_text("Сначала отправь /start, чтобы привязать бота.")
            return False
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Atomic first claim, so simultaneous requests cannot overwrite the owner.
        try:
            fd = os.open(OWNER_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            owner = current_owner()
        else:
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(str(user.id))
            owner = user.id
            logger.info("Owner claimed bot (user ID %s)", user.id)
    if owner != user.id:
        await msg.reply_text("Этот бот приватный.")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorized(update):
        await update.effective_message.reply_text(
            "Привет! Пришли голосовое или аудиофайл (до 20 МиБ). "
            "Распознавание выполняется локально на моём компьютере."
        )


def run_transcribe(audio_path: Path) -> tuple[str, Path]:
    result = subprocess.run(
        [str(ROOT / "bin" / "transcribe"), str(audio_path)],
        capture_output=True,
        text=True,
        timeout=7200,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout or "transcribe failed")[-1200:]
        )
    output = audio_path.with_suffix(".txt")
    if not output.is_file():
        raise RuntimeError("Transcription command finished but no TXT file was created")
    return output.read_text(encoding="utf-8").strip(), output


async def audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await authorized(update):
        return
    msg = update.effective_message
    item = msg.voice or msg.audio or msg.document
    if item is None:
        return
    suffix = (
        ".ogg"
        if msg.voice
        else Path(getattr(item, "file_name", "") or "").suffix.lower()
    )
    if not suffix and msg.audio:
        suffix = ".mp3"
    if suffix not in SUPPORTED:
        await msg.reply_text(
            "Неподдерживаемый формат. Отправь голосовое, MP3, WAV, FLAC, OGG или M4A."
        )
        return
    if item.file_size and item.file_size > MAX_BYTES:
        await msg.reply_text(
            "Файл больше 20 МиБ — стандартный Telegram Bot API не позволит его скачать."
        )
        return
    # Claim the lock before any await: a second incoming message cannot race into transcription.
    if processing_lock.locked():
        await msg.reply_text(
            "Сейчас обрабатываю другую запись. Пришли следующую после завершения."
        )
        return
    async with processing_lock:
        status = await msg.reply_text("⏬ Скачиваю запись…")
        job_dir = AUDIO_DIR / ("bot-" + uuid.uuid4().hex)
        try:
            job_dir.mkdir(parents=True, exist_ok=False)
            audio_path = job_dir / ("recording" + suffix)
            remote = await context.bot.get_file(item.file_id)
            await remote.download_to_drive(custom_path=audio_path)
            await status.edit_text("🧠 Распознаю через локальный Whisper…")
            transcript, txt_path = await asyncio.to_thread(run_transcribe, audio_path)
            if not transcript:
                await status.edit_text("Речь не обнаружена.")
            elif len(transcript) <= 3900:
                await status.edit_text(transcript)
            else:
                with txt_path.open("rb") as file:
                    await msg.reply_document(
                        document=file, filename="transcription.txt"
                    )
                await status.edit_text("✅ Готово. Текст отправлен файлом.")
        except subprocess.TimeoutExpired:
            logger.exception("Transcription timed out")
            await status.edit_text("Превышен лимит распознавания (2 часа).")
        except Exception:
            logger.exception("Audio processing failed")
            await status.edit_text(
                "Не получилось обработать запись. Подробности в логах бота."
            )
        finally:
            # Never delete arbitrary files in AUDIO_DIR; remove only this job's unique folder.
            if job_dir.is_dir():
                shutil.rmtree(job_dir, ignore_errors=True)


async def unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorized(update):
        await update.effective_message.reply_text(
            "Пришли голосовое сообщение или аудиофайл."
        )


def main() -> None:
    if not BOT_TOKEN or ":" not in BOT_TOKEN or "PASTE_" in BOT_TOKEN:
        raise SystemExit("Укажи BOT_TOKEN в .env (получи токен у @BotFather)")
    if OWNER_MODE not in ("fixed", "first"):
        raise SystemExit("OWNER_MODE должен быть fixed или first")
    if OWNER_MODE == "fixed" and (
        not OWNER_ID.isascii() or not OWNER_ID.isdecimal() or int(OWNER_ID) <= 0
    ):
        raise SystemExit("Для OWNER_MODE=fixed укажи числовой TELEGRAM_USER_ID в .env")
    for exe in ("ffmpeg", "whisper-cli"):
        if shutil.which(exe) is None:
            raise SystemExit(
                f"Не найдена команда {exe}. Установи ffmpeg и whisper-cpp."
            )
    model_path = Path(
        os.getenv(
            "WHISPER_MODEL",
            str(Path.home() / ".local/share/whisper/models/ggml-small.bin"),
        )
    ).expanduser()
    if not model_path.is_file():
        raise SystemExit(f"Модель не найдена: {model_path}. Смотри README.md.")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.ALL, audio)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unsupported))
    print("Бот запущен; отправь /start со своего Telegram-аккаунта.", flush=True)
    if OWNER_MODE == "first" and current_owner() is None:
        print(
            "ВНИМАНИЕ: первый пользователь, отправивший /start, станет владельцем!",
            flush=True,
        )
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
