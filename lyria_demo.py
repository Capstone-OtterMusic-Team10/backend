import asyncio
import os
import sys  # ### DEBUG ###
import inspect  # ### DEBUG ###
import sounddevice as sd
import numpy as np
from dotenv import load_dotenv
import pprint  # NEW: for pretty-printing messages
import requests
import json

# ### DEBUG ### Print the exact path of the python interpreter running this script
print(f"--- Python Executable: {sys.executable}")
print("-" * 20)

from google import genai
from google.genai import types

# ### DEBUG ### Print the version and location of the imported google-genai library
print(f"--- google-genai version: {genai.__version__}")
print(f"--- google-genai location: {genai.__file__}")
print("-" * 20)

load_dotenv(".env")

# Debug: Check if API key is loaded
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    print(f"✅ API Key loaded: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else '***'}")
else:
    print("❌ No API key found! Please set GOOGLE_API_KEY environment variable")
    print("Get your API key from: https://aistudio.google.com/app/apikey")
    sys.exit(1)

client = genai.Client(
    http_options=types.HttpOptions(api_version="v1alpha")
)


async def list_available_models():
    """List available models to see what's supported"""
    print("Listing available models...")
    try:
        # Use the correct method to list models
        models = await client.aio.models.list()
        print("Available models:")
        for model in models:
            print(f"  - {model.name}")
            # Print all available attributes for debugging
            print(f"    Available attributes: {[attr for attr in dir(model) if not attr.startswith('_')]}")
    except Exception as e:
        print(f"Error listing models: {e}")


async def test_batch_api():
    """Test the batch prediction API instead of real-time streaming"""
    print("Testing Lyria batch prediction API...")
    
    # For the batch API, we need to use the Google AI Studio API key directly
    # The URL format is different from the curl example
    #url = "https://generativelanguage.googleapis.com/v1/models/lyria-002:generateContent"
    url = "https://api.openai.com/v1/music/generate"

    headers = {
        "Content-Type": "application/json"
    }

    data = {
        "model": "lyria-002",
        "input": {
            "prompt": "energetic electronic music with heavy bass"
        }
    }
    """
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Generate a lo-fi hip-hop beat with smooth jazz elements"
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.8,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024
        }
    }
    """
    print(f"Making request to: {url}")
    print(f"Request data: {json.dumps(data, indent=2)}")
    
    try:
        # Add API key as query parameter
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=data, timeout=60)
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Success! Response:")
            pprint.pprint(result)
            
            # Try to extract and play audio if available
            if "candidates" in result and result["candidates"]:
                candidate = result["candidates"][0]
                if "content" in candidate and candidate["content"]["parts"]:
                    for part in candidate["content"]["parts"]:
                        if "inlineData" in part and part["inlineData"]["mimeType"].startswith("audio/"):
                            print("🎵 Audio data found in response!")
                            # Handle audio data - this might be base64 encoded
                        else:
                            print(f"📡 Response part: {part}")
                else:
                    print("📡 Response contains candidates but no content")
        else:
            print(f"❌ Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")


async def main():
    print("Connecting to the Lyria service...")
    try:
        # Try the original model name that was working for connection
        model_name = "models/lyria-002:predict"
        print(f"Using model: {model_name}")
        
        async with client.aio.live.music.connect(model=model_name) as session:

            print("✅ Music session connected.")

            # ### DEBUG ### Print the type and capabilities of the session object
            print("-" * 20)
            print(f"--- Session object type: {type(session)}")
            print(f"--- Available methods: {[m for m in dir(session) if not m.startswith('_')]}")
            print("-" * 20)

            print("Setting prompts...")
            await session.set_weighted_prompts(
                [types.WeightedPrompt(text="lo-fi hip-hop beat", weight=1.0)])
            print("✅ Prompts set")
            
            print("Setting music generation config...")
            await session.set_music_generation_config(
                types.LiveMusicGenerationConfig(bpm=85, temperature=1.0))
            print("✅ Config set")

            print("🎹 Prompts and config set. Starting stream...")
            print("Waiting for first message (this may take a moment)...")

            start_time = asyncio.get_event_loop().time()
            timeout = 30  # 30 seconds timeout
            message_count = 0
            
            try:
                # Add a timeout to the entire receive loop
                async with asyncio.timeout(timeout):
                    async for msg in session.receive():
                        message_count += 1
                        current_time = asyncio.get_event_loop().time()
                        
                        # NEW: Print the full message for debugging
                        print(f"\n--- Received message #{message_count} at {current_time - start_time:.1f}s ---")
                        pprint.pprint(msg)
                        print("------------------------\n")
                        
                        if hasattr(msg, 'server_content') and msg.server_content and hasattr(msg.server_content, 'audio_chunks') and msg.server_content.audio_chunks:
                            pcm = msg.server_content.audio_chunks[0].data
                            audio = (np.frombuffer(pcm, dtype=np.int16)
                                     .astype(np.float32) / 32768.0)
                            sd.play(audio, 48_000, blocking=True)
                            print(f"🎵 Playing audio chunk at {current_time - start_time:.1f}s")
                        else:
                            print(f"📡 Received message without audio at {current_time - start_time:.1f}s")
                            
            except asyncio.TimeoutError:
                print(f"⏰ Timeout reached ({timeout}s). No messages received.")
                print("This could mean:")
                print("1. The model is not available or not responding")
                print("2. There's an authentication issue")
                print("3. The service is experiencing issues")
            except Exception as stream_e:
                print(f"Stream error: {stream_e}")

    except TypeError as e:
        print(f"\n💥 CAUGHT EXPECTED ERROR: {e}\n")
    except Exception as e:
        print(f"\n💥 CAUGHT UNEXPECTED ERROR: {type(e).__name__} - {e}\n")
    finally:
        # Using a broad try/except here because session.stop() might not exist on an old object
        try:
            print("Stopping music generation...")
            await session.stop()
            print("🛑 Stream stopped.")
        except Exception as stop_e:
            print(f"Could not stop session: {stop_e}")


if __name__ == "__main__":
    # List available models first
    print("=" * 50)
    print("LISTING AVAILABLE MODELS")
    print("=" * 50)
    asyncio.run(list_available_models())
    
    # Try the batch API
    print("\n" + "=" * 50)
    print("TESTING BATCH PREDICTION API")
    print("=" * 50)
    asyncio.run(test_batch_api())
    
    # Try the real-time streaming API
    print("\n" + "=" * 50)
    print("TESTING REAL-TIME STREAMING API")
    print("=" * 50)
    asyncio.run(main())