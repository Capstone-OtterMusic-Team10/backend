from datetime import datetime
from pathlib import Path

DOWNLOAD_DIR = Path.cwd() / "Music Download Files"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def ask_to_download():
    """Prompt the user to save the most-recent clip; return (save?, path)."""
    while True:
        resp = input("Save this performance to disk? [y/n] ").strip().lower()
        if resp in {"y", "yes"}:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = f"lyria_{ts}.wav"
            return True, DOWNLOAD_DIR / name
        if resp in {"n", "no"}:
            return False, None
        print("Please type y or n.")