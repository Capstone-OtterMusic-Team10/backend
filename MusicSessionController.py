import asyncio
import pyaudio
from google import genai
from google.genai import types

import utils

BUFFER_SECONDS = 1
CHUNK = 4200
FORMAT = pyaudio.paInt16
CHANNELS = 2
MODEL = "models/lyria-realtime-exp"
OUTPUT_RATE = 48_000
MAX_PLAY_SECONDS = 30

class MusicSessionController:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        self.pcm_buffer = bytearray()
        self.pa = pyaudio.PyAudio()
        self.config = types.LiveMusicGenerationConfig()
        self.session = None
        self.auto_stop_task = None

    async def receive(self):
        chunks = 0
        stream = self.pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_RATE,
            output=True,
            frames_per_buffer=CHUNK,
        )
        try:
            async for msg in self.session.receive():
                if msg.server_content:
                    if chunks == 0:
                        await asyncio.sleep(BUFFER_SECONDS)
                    chunks += 1
                    data = msg.server_content.audio_chunks[0].data
                    stream.write(data)
                    self.pcm_buffer.extend(data)
                elif msg.filtered_prompt:
                    print("Prompt filtered:", msg.filtered_prompt)
        except asyncio.CancelledError:
            pass
        finally:
            stream.close()

    async def send(self):
        await asyncio.sleep(5)
        while True:
            text = await asyncio.to_thread(input, " > ")
            if not text:
                continue
            cmd = text.lower().strip()

            if cmd == "q":
                await self.session.stop()
                if self.auto_stop_task and not self.auto_stop_task.done():
                    self.auto_stop_task.cancel()
                return

            if cmd == "play":
                await self.session.play()
                if self.auto_stop_task and not self.auto_stop_task.done():
                    self.auto_stop_task.cancel()
                self.auto_stop_task = asyncio.create_task(self.schedule_auto_stop())
                continue

            if cmd == "pause":
                await self.session.pause()
                if self.auto_stop_task and not self.auto_stop_task.done():
                    self.auto_stop_task.cancel()
                continue

            if cmd == "save":
                utils.ask_to_download()

            if cmd.startswith("bpm="):
                bpm_val = cmd[4:]
                if bpm_val == "auto":
                    self.config.bpm = None
                else:
                    try:
                        self.config.bpm = int(bpm_val)
                    except ValueError:
                        print("BPM must be int or AUTO")
                        continue
                await self.session.set_music_generation_config(config=self.config)
                await self.session.reset_context()
                continue

            if cmd.startswith("scale="):
                scale_val = cmd.split("=", 1)[1].strip().upper()
                if scale_val == "AUTO":
                    self.config.scale = None
                else:
                    try:
                        self.config.scale = types.Scale[scale_val]
                    except KeyError:
                        print("Unknown scale")
                        continue
                await self.session.set_music_generation_config(config=self.config)
                await self.session.reset_context()
                continue

            if ":" in text:
                pr = []
                for seg in text.split(","):
                    if not seg.strip():
                        continue
                    t, w = seg.split(":", 1)
                    pr.append(types.WeightedPrompt(text=t.strip(), weight=float(w)))
                await self.session.set_weighted_prompts(prompts=pr)
                continue

            await self.session.set_weighted_prompts(
                prompts=[types.WeightedPrompt(text=text, weight=1.0)]
            )

    async def schedule_auto_stop(self):
        try:
            await asyncio.sleep(MAX_PLAY_SECONDS)
            print(f"\n⏹  Auto-stopped after {MAX_PLAY_SECONDS}s (time cap reached).")
            await self.session.stop()
        except asyncio.CancelledError:
            pass

    async def close(self):
        await self.session.__aexit__(None, None, None)
        self.pa.terminate()