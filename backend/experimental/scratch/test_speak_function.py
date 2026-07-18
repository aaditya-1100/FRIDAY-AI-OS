import asyncio
import os
import sys

# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from voice.speak import speak
from core.state_manager import AssistantState, set_state

async def main():
    # Force state to SPEAKING
    set_state(AssistantState.SPEAKING, force=True)
    
    print("Testing speak function with a short response...")
    # Test local playback mode (web_mode=False) to run it locally
    await speak("Hello, this is a local synthesis test of the recovered FRIDAY voice pipeline.", web_mode=False)
    print("Speak function execution completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
