"""
## Setup

To install the dependencies for this script, run:

```
pip install pyaudio websockets
```

Before running this script, ensure the `GOOGLE_API_KEY` environment
variable is set to the api-key you obtained from Google AI Studio.

## Run

To run the script:

```
python LyriaRealTime_EAP.py
```

The script takes a prompt from the command line and streams the audio back over
websockets.
"""
import asyncio
import os
import threading
import wave
from datetime import datetime
from pathlib import Path
import sys
import pyaudio
import subprocess
from dotenv import load_dotenv
from google import genai
from google.genai import types
import logging
# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
# Audio/model constants - from Google demo
BUFFER_SECONDS = 1
CHUNK = 4200
FORMAT = pyaudio.paInt16
CHANNELS = 2
MODEL = "models/lyria-realtime-exp"
OUTPUT_RATE = 48_000
SAMPLE_WIDTH_BYTES = 2
FRAME_RATE = OUTPUT_RATE
# Directory to save downloaded audio files
DOWNLOAD_DIR = Path.cwd() / "MusicDownloadFiles"
DOWNLOAD_DIR.mkdir(exist_ok=True) # create if it doesn't exist
# Demucs separation constants
BASE_DIR = Path.cwd()
load_dotenv()
usevenv = os.getenv("USEVENV")
if usevenv == "true":
    CONDA_ENV_PATH = BASE_DIR / "venv"
else:
    CONDA_ENV_PATH = "/opt/anaconda3/envs/demucs-env"
SEPARATED_DIR = BASE_DIR / "separated_music"
DEMUCS_MODEL_NAME = "htdemucs_ft" # music model!
# Ensure the output directory exists
SEPARATED_DIR.mkdir(exist_ok=True)
# Constants for the demo
MAX_PLAY_SECONDS = 30 # hard cap per PLAY
auto_stop_task: asyncio.Task | None = None # will hold the running timer
# Run Demucs separation in a background thread to avoid blocking the API.
def run_demucs_in_background(input_path, output_path):
    if os.name == 'nt':
        python_executable = os.path.join(CONDA_ENV_PATH, "Scripts", "python.exe")
    else:
        python_executable = os.path.join(CONDA_ENV_PATH, "bin", "python")
    script_path = BASE_DIR / "separator.py"
    if not os.path.exists(python_executable):
        logger.error(f"FATAL ERROR: Python executable not found at {python_executable}")
        return
    command = [python_executable, str(script_path), str(input_path), str(output_path)]
    logger.debug(f"Starting background Demucs process: {' '.join(command)}")
    # Use Popen to run the command in the background
    subprocess.Popen(command)
    logger.info("Background Demucs process started.")
# Start Demucs separation immediately after Lyria generates audio.
# This runs in the background so users don't have to wait when they get to the mixer page
def start_demucs_separation_after_lyria(chat_id, prompt_id):
    try:
        input_filename = f"lyria_{chat_id}_{prompt_id}.wav"
        input_path = DOWNLOAD_DIR / input_filename
        if not input_path.exists():
            logger.warning(f"Audio file not found: {input_path}")
            return
        # Start Demucs separation in background
        thread = threading.Thread(
            target=run_demucs_in_background,
            args=(input_path, SEPARATED_DIR)
        )
        thread.daemon = True
        thread.start()
        logger.info(f"Started Demucs separation for {input_filename} in background")
    except Exception as e:
        logger.error(f"Failed to start Demucs separation: {e}")
# Helper function to ask user if they want to save the audio clip
def download(chat_id, prompt_id) -> tuple[bool, Path | None]:
    """Prompt the user to save the most-recent clip; return (save?, path)."""
    logger.debug(f"Preparing to download audio for chat_id: {chat_id}, prompt_id: {prompt_id}")
    while True:
        name = f"lyria_{chat_id}_{prompt_id}.wav"
        return True, DOWNLOAD_DIR / name
# Function to schedule an auto-stop after MAX_PLAY_SECONDS, will then basically press "q"
# If user pressed "q" before this fires, it will be cancelled
async def schedule_auto_stop(session, send_task):
    try:
        await asyncio.sleep(MAX_PLAY_SECONDS)
        logger.info(f"Auto-stopping after {MAX_PLAY_SECONDS}s (time cap reached).")
        await session.stop() # same as 'q'
        send_task.cancel() # make send() finish immediately
    except asyncio.CancelledError:
        logger.debug("Auto-stop timer cancelled")
        # Timer was cancelled (user paused or quit before 30 s) — do nothing
        pass
# Main function to run the Lyria demo
async def generate_audio(bpm, key, prompt, chat_id, prompt_id) -> None:
    logger.debug(f"Starting generate_audio with bpm: {bpm}, key: {key}, prompt: '{prompt}', chat_id: {chat_id}, prompt_id: {prompt_id}")
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not found in environment, attempting interactive input")
            api_key = input("API Key: ").strip()
        logger.debug("API key retrieved successfully")
    except Exception as e:
        logger.error(f"Failed to retrieve API key: {e}")
        raise
    try:
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1alpha"},
        )
        logger.debug("Google client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Google client: {e}")
        raise
    pcm_buffer = bytearray()
    try:
        pa = pyaudio.PyAudio()
        logger.debug("PyAudio initialized")
    except Exception as e:
        logger.error(f"Failed to initialize PyAudio: {e}")
        raise
    config = types.LiveMusicGenerationConfig()
    global auto_stop_task
    try:
        async with client.aio.live.music.connect(model=MODEL) as session:
            logger.debug("Lyria session connected")
            async def receive() -> None:
                chunks = 0
                try:
                    stream = pa.open(
                        format=FORMAT,
                        channels=CHANNELS,
                        rate=OUTPUT_RATE,
                        output=True,
                        frames_per_buffer=CHUNK,
                    )
                    logger.debug("Audio stream opened")
                except Exception as e:
                    logger.error(f"Failed to open audio stream: {e}")
                    raise
                try:
                    async for msg in session.receive():
                        if msg.server_content:
                            if chunks == 0:
                                await asyncio.sleep(BUFFER_SECONDS)
                            chunks += 1
                            data = msg.server_content.audio_chunks[0].data
                            try:
                                stream.write(data)
                                pcm_buffer.extend(data)
                                logger.debug(f"Processed audio chunk {chunks}")
                            except Exception as e:
                                logger.error(f"Failed to write audio chunk {chunks}: {e}")
                        elif msg.filtered_prompt:
                            logger.warning(f"Prompt filtered: {msg.filtered_prompt}")
                except asyncio.CancelledError:
                    logger.debug("Receive task cancelled")
                    pass
                except Exception as e:
                    logger.error(f"Error in receive loop: {e}")
                    raise
                finally:
                    try:
                        stream.close()
                        logger.debug("Audio stream closed")
                    except Exception as e:
                        logger.error(f"Failed to close audio stream: {e}")
            async def send() -> None:
                await asyncio.sleep(5)
                global auto_stop_task
                while True:
                    try:
                        text = await asyncio.to_thread(input, " > ")
                        logger.debug(f"Received input: {text}")
                    except EOFError:
                        logger.warning("EOFError in input (non-interactive mode), stopping session")
                        await session.stop()
                        if auto_stop_task and not auto_stop_task.done():
                            auto_stop_task.cancel()
                        logger.info("Session stopped due to EOFError")
                        return
                    except Exception as e:
                        logger.error(f"Failed to get input: {e}")
                        continue
                    if not text:
                        continue
                    cmd = text.lower().strip()
                    if cmd == "q":
                        await session.stop()
                        if auto_stop_task and not auto_stop_task.done():
                            auto_stop_task.cancel()
                        logger.info("Session stopped via 'q' command")
                        return
                    if cmd == "play":
                        try:
                            await session.play()
                            logger.debug("Session playback started")
                            if auto_stop_task and not auto_stop_task.done():
                                auto_stop_task.cancel()
                            auto_stop_task = asyncio.create_task(
                                schedule_auto_stop(session, asyncio.current_task())
                            )
                        except Exception as e:
                            logger.error(f"Failed to start playback: {e}")
                        continue
                    if cmd == "pause":
                        try:
                            await session.pause()
                            logger.debug("Session paused")
                            if auto_stop_task and not auto_stop_task.done():
                                auto_stop_task.cancel()
                        except Exception as e:
                            logger.error(f"Failed to pause session: {e}")
                        continue
                    if cmd.startswith("bpm="):
                        bpm_val = cmd[4:]
                        if bpm_val == "auto":
                            config.bpm = None
                        else:
                            try:
                                config.bpm = int(bpm_val)
                            except ValueError:
                                logger.warning("Invalid BPM value, must be int or AUTO")
                                continue
                        try:
                            await session.set_music_generation_config(config=config)
                            await session.reset_context()
                            logger.debug(f"BPM set to {config.bpm}")
                        except Exception as e:
                            logger.error(f"Failed to set BPM config: {e}")
                        continue
                    if cmd.startswith("scale="):
                        scale_val = cmd.split("=", 1)[1].strip().upper()
                        if scale_val == "AUTO":
                            config.scale = None
                        else:
                            try:
                                config.scale = types.Scale[scale_val]
                            except KeyError:
                                logger.warning("Unknown scale value")
                                continue
                        try:
                            await session.set_music_generation_config(config=config)
                            await session.reset_context()
                            logger.debug(f"Scale set to {config.scale}")
                        except Exception as e:
                            logger.error(f"Failed to set scale config: {e}")
                        continue
                    if ":" in text:
                        pr = []
                        for seg in text.split(","):
                            if not seg.strip():
                                continue
                            try:
                                t, w = seg.split(":", 1)
                                pr.append(types.WeightedPrompt(text=t.strip(), weight=float(w)))
                            except ValueError:
                                logger.warning("Invalid multi-prompt format")
                                continue
                        try:
                            await session.set_weighted_prompts(prompts=pr)
                            logger.debug("Multi-prompt set")
                        except Exception as e:
                            logger.error(f"Failed to set multi-prompt: {e}")
                        continue
                    try:
                        await session.set_weighted_prompts(
                            prompts=[types.WeightedPrompt(text=text, weight=1.0)]
                        )
                        logger.debug("Single prompt set via input")
                    except Exception as e:
                        logger.error(f"Failed to set single prompt: {e}")
            try:
                config.bpm = bpm
                logger.debug(f"BPM configured to {bpm}")
            except ValueError:
                config.bpm = 120
                logger.warning(f"Invalid BPM, defaulting to 120")
            config.scale = key
            logger.debug(f"Scale configured to {key}")
            try:
                await session.set_music_generation_config(config=config)
                logger.debug("Music generation config set")
            except Exception as e:
                logger.error(f"Failed to set music config: {e}")
                raise
            try:
                await session.set_weighted_prompts(
                    prompts=[types.WeightedPrompt(text=prompt, weight=1.0)]
                )
                logger.debug("Initial prompt set")
            except Exception as e:
                logger.error(f"Failed to set initial prompt: {e}")
                raise
            try:
                await session.play()
                logger.debug("Session playback initiated")
            except Exception as e:
                logger.error(f"Failed to initiate session play: {e}")
                raise
            send_t = asyncio.create_task(send(), name="send")
            auto_stop_task = asyncio.create_task(schedule_auto_stop(session, send_t))
            recv_t = asyncio.create_task(receive(), name="recv")
            done, _ = await asyncio.wait(
                {send_t, recv_t},
                return_when=asyncio.FIRST_COMPLETED
            )
            logger.debug("One of send/recv tasks completed")
            for t in (send_t, recv_t):
                if not t.done():
                    t.cancel()
                    logger.debug(f"Cancelled task: {getattr(t, 'name', 'unnamed_task')}")
            await asyncio.gather(send_t, recv_t, return_exceptions=True)
            logger.debug("All tasks gathered")
    except Exception as e:
        logger.error(f"Error in Lyria session: {e}")
        raise
    finally:
        try:
            pa.terminate()
            logger.debug("PyAudio terminated")
        except Exception as e:
            logger.error(f"Failed to terminate PyAudio: {e}")
    save, path = download(chat_id, prompt_id)
    if save:
        if pcm_buffer:
            try:
                with wave.open(str(path), "wb") as w:
                    w.setnchannels(CHANNELS)
                    w.setsampwidth(SAMPLE_WIDTH_BYTES)
                    w.setframerate(FRAME_RATE)
                    w.writeframes(pcm_buffer)
                logger.info(f"Saved audio to {path}")
                start_demucs_separation_after_lyria(chat_id, prompt_id)
            except Exception as e:
                logger.error(f"Failed to save audio file: {e}")
                raise Exception(f"Audio save failed: {e}")
        else:
            logger.warning("No audio captured—nothing to save.")
            raise Exception("No audio captured")
    else:
        logger.info("Clip discarded.")
        raise Exception("Clip discarded")
# prompt = input("Enter music prompt <<< ")
# asyncio.run(generate_audio(120, 2, prompt, 1, 1))
# if __name__ == "__main__":
# asyncio.run(generate_audio())