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
import wave
from datetime import datetime
from pathlib import Path

import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types

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

# Constants for the demo
MAX_PLAY_SECONDS = 30      # hard cap per PLAY
auto_stop_task: asyncio.Task | None = None   # will hold the running timer


# Helper function to ask user if they want to save the audio clip
def ask_to_download() -> tuple[bool, Path | None]:
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

# Function to schedule an auto-stop after MAX_PLAY_SECONDS, will then basically press "q"
# If user pressed "q" before this fires, it will be cancelled
async def schedule_auto_stop(session, send_task):
    try:
        await asyncio.sleep(MAX_PLAY_SECONDS)
        print(f"\n⏹  Auto-stopped after {MAX_PLAY_SECONDS}s (time cap reached).")
        await session.stop() # same as 'q'
        send_task.cancel() # make send() finish immediately
    except asyncio.CancelledError:
        # Timer was cancelled (user paused or quit before 30 s) — do nothing
        pass

# Main function to run the Lyria demo
async def main() -> None:
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY") or input("API Key: ").strip()

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1alpha"},
    )

    pcm_buffer = bytearray()
    pa = pyaudio.PyAudio()
    config = types.LiveMusicGenerationConfig()

    # Define the auto-stop task globally so we can modify it
    global auto_stop_task

    async with client.aio.live.music.connect(model=MODEL) as session:

        # Receiver function to handle incoming audio
        async def receive() -> None:
            chunks = 0
            stream = pa.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=OUTPUT_RATE,
                output=True,
                frames_per_buffer=CHUNK,
            )
            try:
                async for msg in session.receive():
                    if msg.server_content:
                        if chunks == 0:
                            await asyncio.sleep(BUFFER_SECONDS)
                        chunks += 1
                        data = msg.server_content.audio_chunks[0].data
                        stream.write(data)
                        pcm_buffer.extend(data)
                    elif msg.filtered_prompt:
                        print("Prompt filtered:", msg.filtered_prompt)
            except asyncio.CancelledError:
                # task cancelled by main; just exit cleanly
                pass
            finally:
                stream.close()

        # Sender function to handle user input
        async def send() -> None:
            await asyncio.sleep(5)

            global auto_stop_task # this will be mutated
            while True:
                text = await asyncio.to_thread(input, " > ")
                if not text:
                    continue
                cmd = text.lower().strip()

                # quit
                if cmd == "q":
                    await session.stop()
                    if auto_stop_task and not auto_stop_task.done():
                        auto_stop_task.cancel() # clean up timer
                    return # FIRST_COMPLETED

                # ply/ pause
                if cmd == "play":
                    await session.play()

                    # restart 30-s countdown each time we (re)start playback
                    if auto_stop_task and not auto_stop_task.done():
                        auto_stop_task.cancel()
                    auto_stop_task = asyncio.create_task(
                        schedule_auto_stop(session, asyncio.current_task())  # pass *this* send() task
                    )
                    continue

                # stop
                if cmd == "pause":
                    await session.pause()

                    # stop the countdown while paused
                    if auto_stop_task and not auto_stop_task.done():
                        auto_stop_task.cancel()
                    continue

                # bpm
                if cmd.startswith("bpm="):
                    bpm_val = cmd[4:]
                    if bpm_val == "auto":
                        config.bpm = None
                    else:
                        try:
                            config.bpm = int(bpm_val)
                        except ValueError:
                            print("BPM must be int or AUTO")
                            continue
                    await session.set_music_generation_config(config=config)
                    await session.reset_context()
                    continue

                # scale
                if cmd.startswith("scale="):
                    scale_val = cmd.split("=", 1)[1].strip().upper()
                    if scale_val == "AUTO":
                        config.scale = None
                    else:
                        try:
                            config.scale = types.Scale[scale_val]
                        except KeyError:
                            print("Unknown scale")
                            continue
                    await session.set_music_generation_config(config=config)
                    await session.reset_context()
                    continue

                # multi-prompt "text:weight"
                if ":" in text:
                    pr = []
                    for seg in text.split(","):
                        if not seg.strip():
                            continue
                        t, w = seg.split(":", 1)
                        pr.append(types.WeightedPrompt(text=t.strip(),
                                                       weight=float(w)))
                    await session.set_weighted_prompts(prompts=pr)
                    continue

                # single prompt
                await session.set_weighted_prompts(
                    prompts=[types.WeightedPrompt(text=text, weight=1.0)]
                )


        # Init config and prompts
        try:
            config.bpm = int(await asyncio.to_thread(
                input, "BPM (blank=120): ") or 120)
        except ValueError:
            config.bpm = 120

        print("Scales:")
        for i, s in enumerate(types.Scale, 1):
            print(f" {i}: {s.name}")
        sel = await asyncio.to_thread(input, "Scale #: ")
        config.scale = (
            list(types.Scale)[int(sel)-1]
            if sel.isdigit() and 1 <= int(sel) <= len(types.Scale)
            else types.Scale.A_FLAT_MAJOR_F_MINOR
        )

        init = await asyncio.to_thread(input, "Initial prompt (blank='Piano'): ") or "Piano"
        await session.set_music_generation_config(config=config)
        await session.set_weighted_prompts(
            prompts=[types.WeightedPrompt(text=init, weight=1.0)]
        )
        await session.play()

        # Start the auto-stop timer
        # auto_stop_task = asyncio.create_task(schedule_auto_stop(session))

        # Run sender and receiver concurrently
        send_t = asyncio.create_task(send(), name="send")  # sender first

        auto_stop_task = asyncio.create_task(  # start 30-s timer
            schedule_auto_stop(session, send_t)  # pass send_t handle
        )

        # Receiver task
        recv_t = asyncio.create_task(receive(), name="recv")
        done, _ = await asyncio.wait(
            {send_t, recv_t},
            return_when=asyncio.FIRST_COMPLETED
        )
        # cancel any task still running
        for t in (send_t, recv_t):
            if not t.done():
                t.cancel()
        await asyncio.gather(send_t, recv_t, return_exceptions=True)

    # Clean up PyAudio
    pa.terminate()

    # Always ask—buffer may be empty if user quit immediately
    save, path = ask_to_download()
    if save:
        if pcm_buffer:
            with wave.open(str(path), "wb") as w:
                w.setnchannels(CHANNELS)
                w.setsampwidth(SAMPLE_WIDTH_BYTES)
                w.setframerate(FRAME_RATE)
                w.writeframes(pcm_buffer)
            print(f"Saved ✔️  {path}")
        else:
            print("No audio captured—nothing to save.")
    else:
        print("Clip discarded.")

if __name__ == "__main__":
    asyncio.run(main())