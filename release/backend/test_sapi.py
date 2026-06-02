import pyttsx3
import traceback
import sys

try:
    print("Initializing pyttsx3...")
    engine = pyttsx3.init()
    print("SAPI5 Engine initialized successfully!")
    voices = engine.getProperty('voices')
    for voice in voices:
        print(f"Voice found: {voice.name} | ID: {voice.id}")
    engine.save_to_file("Hello, this is a local SAPI5 synthesis test.", "test_sapi.wav")
    engine.runAndWait()
    print("SAPI5 test file generated successfully!")
except Exception as e:
    print(f"SAPI5 failure: {e}")
    traceback.print_exc()
    sys.exit(1)
