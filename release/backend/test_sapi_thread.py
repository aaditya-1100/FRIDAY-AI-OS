import asyncio
import concurrent.futures
import traceback
import sys
import os

def _run_sapi_tts_thread(text: str, path: str) -> None:
    import pythoncom
    import pyttsx3
    
    print("Background thread: calling CoInitialize...")
    pythoncom.CoInitialize()
    try:
        print("Background thread: initializing pyttsx3 local engine...")
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        selected_voice = None
        for voice in voices:
            name_lower = voice.name.lower()
            if "zira" in name_lower or "hazel" in name_lower or "female" in name_lower:
                selected_voice = voice.id
                break
        if selected_voice:
            engine.setProperty('voice', selected_voice)
        
        engine.setProperty('rate', int(engine.getProperty('rate') * 1.15))
        print("Background thread: saving to file...")
        engine.save_to_file(text, path)
        engine.runAndWait()
        print("Background thread: synthesis success!")
        del engine
    except Exception as e:
        print(f"Background thread SAPI5 error: {e}")
        raise e
    finally:
        print("Background thread: calling CoUninitialize...")
        pythoncom.CoUninitialize()

async def main():
    loop = asyncio.get_running_loop()
    path = "test_sapi_thread.wav"
    if os.path.exists(path):
        os.remove(path)
        
    print("Dispatching SAPI5 synthesis to background thread pool...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        await loop.run_in_executor(executor, _run_sapi_tts_thread, "This is a thread-safe local SAPI5 test.", path)
        
    print(f"File exists: {os.path.exists(path)} | Size: {os.path.getsize(path) if os.path.exists(path) else 0} bytes")
    assert os.path.exists(path) and os.path.getsize(path) > 0, "Failed to generate valid wav file!"
    print("SUCCESS: Thread-safe SAPI5 local fallback verified!")

if __name__ == "__main__":
    asyncio.run(main())
