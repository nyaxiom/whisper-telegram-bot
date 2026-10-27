#!/usr/bin/env python3
"""Interactive one-time configuration. Uses only the Python standard library."""
import getpass
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / '.env'
TOKEN_PATTERN = re.compile(r'^\d+:[A-Za-z0-9_-]{20,}$')


def configure(input_fn=input, secret_fn=getpass.getpass, output_fn=print) -> bool:
    if ENV_FILE.exists():
        output_fn('.env already exists; keeping your settings unchanged.')
        return False
    output_fn('=== Whisper Telegram Bot: first-time setup ===')
    output_fn('Create a bot with @BotFather, then paste its token below.')
    while True:
        token = secret_fn('Bot token (hidden): ').strip()
        if TOKEN_PATTERN.fullmatch(token):
            break
        output_fn('That token does not look valid. Expected digits:characters from @BotFather.')
    output_fn('\nWho should own this bot?')
    output_fn('  1) Enter my numeric Telegram user ID (recommended)')
    output_fn('  2) First person to send /start becomes the owner (less secure)')
    while True:
        selection = input_fn('Choose [1/2]: ').strip()
        if selection in ('1', '2'):
            break
        output_fn('Enter 1 or 2.')
    if selection == '1':
        while True:
            owner = input_fn('Your numeric Telegram user ID: ').strip()
            if owner.isascii() and owner.isdecimal() and int(owner) > 0:
                break
            output_fn('Please enter a positive numeric user ID, not a username.')
        owner_mode = 'fixed'
    else:
        output_fn('WARNING: Anyone who sends /start before you can permanently claim this bot.')
        output_fn('Do not share the bot link until you have claimed it.')
        while True:
            confirmation = input_fn('Type CLAIM to enable first-user ownership: ').strip()
            if confirmation == 'CLAIM':
                break
            output_fn('Type CLAIM exactly, or Ctrl+C to cancel.')
        owner_mode, owner = 'first', ''
    data = f'BOT_TOKEN={token}\nOWNER_MODE={owner_mode}\nTELEGRAM_USER_ID={owner}\n'
    # Exclusive creation prevents replacing an existing secret during races.
    fd = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(data)
    except BaseException:
        ENV_FILE.unlink(missing_ok=True)
        raise
    output_fn('\nSaved .env (private, permissions 600).')
    output_fn('Next: send /start to your bot after it launches.')
    return True


if __name__ == '__main__':
    try:
        configure()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit('\nSetup cancelled; no configuration saved.')
