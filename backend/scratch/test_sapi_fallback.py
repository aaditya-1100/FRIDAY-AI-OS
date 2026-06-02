import asyncio
import os
import sys
from unittest.mock import patch

# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from voice.speak import speak
from core.state_manager import AssistantState, set_state

async def main():
    # Force state to SPEAKING
    set_state(AssistantState.SPEAKING, force=True)
    
    print("Testing speak function with gTTS and Edge-TTS mocked to fail...")
    # Mock gTTS and Edge-TTS to raise exceptions, forcing offline SAPI5 fallback
    with patch("gtts.gTTS.save", side_effect=Exception("Mocked network error")), \
         patch("edge_tts.Communicate.save", side_effect=Exception("Mocked forbidden error")):
         
         await speak("Hello Aaditya, this is a local offline SAPI5 fallback test.", web_mode=False)
         
    print("Speak offline fallback verification completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
