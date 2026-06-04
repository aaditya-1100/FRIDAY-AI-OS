import os
import sys
import time
import pythoncom
import win32com.client

def run_direct_sapi(text: str, path: str):
    print("Initializing COM...")
    pythoncom.CoInitialize()
    try:
        print("Dispatching SpVoice and SpFileStream...")
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        filestream = win32com.client.Dispatch("SAPI.SpFileStream")
        
        # Select female/zira voice if available
        voices = voice.GetVoices()
        selected_voice = None
        for i in range(voices.Count):
            v = voices.Item(i)
            name = v.GetDescription().lower()
            if "zira" in name or "female" in name:
                selected_voice = v
                break
        if selected_voice:
            voice.Voice = selected_voice
            print(f"Selected voice: {selected_voice.GetDescription()}")
            
        # 3 = SSFMCreateForWrite
        print(f"Opening file stream: {path}")
        filestream.Open(path, 3, False)
        voice.AudioOutputStream = filestream
        
        print("Speaking text...")
        voice.Speak(text)
        filestream.Close()
        print("SAPI5 Direct COM synthesis success!")
    except Exception as e:
        print(f"Direct COM SAPI5 error: {e}")
        raise e
    finally:
        print("Uninitializing COM...")
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    path = "test_sapi_direct.wav"
    if os.path.exists(path):
        os.remove(path)
    run_direct_sapi("This is a direct COM SAPI5 test on the main thread.", path)
    print(f"File exists: {os.path.exists(path)} | Size: {os.path.getsize(path) if os.path.exists(path) else 0} bytes")
