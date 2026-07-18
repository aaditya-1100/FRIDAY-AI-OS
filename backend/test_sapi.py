import sys
import traceback

import pyttsx3


def main() -> int:
    try:
        print("Initializing pyttsx3...")
        engine = pyttsx3.init()
        print("SAPI5 Engine initialized successfully!")
        voices = engine.getProperty("voices")
        for voice in voices:
            print(f"Voice found: {voice.name} | ID: {voice.id}")
        engine.save_to_file("Hello, this is a local SAPI5 synthesis test.", "test_sapi.wav")
        engine.runAndWait()
        print("SAPI5 test file generated successfully!")
        return 0
    except Exception as e:
        print(f"SAPI5 failure: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
