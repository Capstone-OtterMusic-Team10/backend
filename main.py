import asyncio
import os
import wave
from dotenv import load_dotenv
from google.genai import types

from MusicSessionController import MusicSessionController
from utils import ask_to_download

CHANNELS = 2
SAMPLE_WIDTH_BYTES = 2
FRAME_RATE = 48_000
MODEL = "models/lyria-realtime-exp"

async def main():
    load_dotenv()
    api_key = input("API Key: ").strip()

    controller = MusicSessionController(api_key)

    async with controller.client.aio.live.music.connect(model=MODEL) as session:
        controller.session = session  # Set the session for the controller

        # Init config and prompts
        try:
            controller.config.bpm = int(await asyncio.to_thread(input, "BPM (blank=120): ") or 120)
        except ValueError:
            controller.config.bpm = 120

        print("Scales:")
        for i, s in enumerate(types.Scale, 1):
            print(f" {i}: {s.name}")
        sel = await asyncio.to_thread(input, "Scale #: ")
        controller.config.scale = (
            list(types.Scale)[int(sel) - 1]
            if sel.isdigit() and 1 <= int(sel) <= len(types.Scale)
            else types.Scale.A_FLAT_MAJOR_F_MINOR
        )

        init = await asyncio.to_thread(input, "Initial prompt (blank='Piano'): ") or "Piano"
        await controller.session.set_music_generation_config(config=controller.config)
        await controller.session.set_weighted_prompts(
            prompts=[types.WeightedPrompt(text=init, weight=1.0)]
        )
        await controller.session.play()

        send_task = asyncio.create_task(controller.send(), name="send")
        controller.auto_stop_task = asyncio.create_task(controller.schedule_auto_stop())
        recv_task = asyncio.create_task(controller.receive(), name="recv")

        done, _ = await asyncio.wait({send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED)

        for t in (send_task, recv_task):
            if not t.done():
                t.cancel()
        await asyncio.gather(send_task, recv_task, return_exceptions=True)

        await controller.close()

        save, path = ask_to_download()
        if save:
            if controller.pcm_buffer:
                with wave.open(str(path), "wb") as w:
                    w.setnchannels(CHANNELS)
                    w.setsampwidth(SAMPLE_WIDTH_BYTES)
                    w.setframerate(FRAME_RATE)
                    w.writeframes(controller.pcm_buffer)
                print(f"Saved ✔️  {path}")
            else:
                print("No audio captured—nothing to save.")
        else:
            print("Clip discarded.")

if __name__ == "__main__":
    asyncio.run(main())