import asyncio
import os
import sys
import time

# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from voice.speak import speak
from core.state_manager import AssistantState, set_state

QUERIES = {
    "Hello": "Hello! I am online and fully functional, ready to assist you.",
    
    "PM of India": "The Prime Minister of India is Narendra Modi, who has been serving in this capacity since May 2014.",
    
    "Quantum Mechanics": (
        "Quantum mechanics is a fundamental theory in physics that describes the physical properties of nature "
        "at the scale of atoms and subatomic particles. It is the foundation of all quantum physics including "
        "quantum chemistry, quantum field theory, quantum technology, and quantum information science. Unlike classical physics, "
        "energy, momentum, angular momentum, and other quantities of a bound system are restricted to discrete values, known as quanta. "
        "Objects have characteristics of both particles and waves, and there are limits to how accurately the value of a physical quantity "
        "can be predicted prior to its measurement, which is known as the uncertainty principle."
    ),
    
    "Iron Man Story": (
        "Tony Stark, a brilliant industrialist and master engineer, is captured by terrorists while demonstrating weapons in Afghanistan. "
        "Sufferring a severe chest injury from shrapnel, Stark builds an armored suit with a miniature arc reactor in his chest to keep him alive "
        "and escape captivity. Returning home, he refines the armor into a high tech suit of gold and titanium, transforming into the superhero Iron Man. "
        "He dedicates his life and immense resources to protecting the world, confronting his own past, battles corporate villains, "
        "forms the Avengers, and ultimately sacrifices his life to defeat Thanos and save the entire universe using the Infinity Stones."
    ),
    
    "Black Holes": (
        "A black hole is a region of spacetime where gravity is so strong that nothing, including light or other electromagnetic waves, "
        "has enough energy to escape its event horizon. The theory of general relativity predicts that a sufficiently compact mass "
        "can deform spacetime to form a black hole. The boundary of no escape is called the event horizon. Although it has a catastrophic "
        "effect on the fate and circumstances of an object crossing it, it has no locally detectable features according to general relativity. "
        "In many ways, a black hole acts like an ideal black body, as it reflects no light."
    ),
    
    "AI Comparison": (
        "ChatGPT, Claude, and Gemini are the leading generative artificial intelligence models, each with unique architectural strengths. "
        "ChatGPT, developed by OpenAI, is highly versatile, excellent for coding, creative writing, and has broad multi modal integration. "
        "Claude, created by Anthropic, is renowned for its exceptional logical reasoning, massive context window, adherence to safety parameters, "
        "and superior long form reading comprehension. Gemini, engineered by Google, is natively multimodal from the ground up, boasting ultra fast "
        "integration with the Google ecosystem, real time search capabilities, and highly sophisticated logical deduction across video, audio, and code."
    )
}

async def validate_query(name, text):
    set_state(AssistantState.SPEAKING, force=True)
    temp_path = None
    
    start_time = time.time()
    
    # We will invoke speak locally with web_mode=False to verify synthesis + local playback
    # To avoid long audio delays, we'll bypass pygame's blocking sleep by passing an empty text or mock saving
    # Actually, we can run it completely through the speak() engine to get exact files and sizes!
    try:
        print(f"\n--- VALIDATING QUERY: {name} ---")
        # Run speak with web_mode=False (local pygame playback)
        await speak(text, web_mode=False)
        duration = time.time() - start_time
        print(f"[SUCCESS] Query: '{name}' | Text Length: {len(text)} chars | Synthesis & Playback Duration: {duration:.2f}s")
        return True, len(text), duration
    except Exception as e:
        print(f"[FAILED] Query: '{name}' | Error: {e}")
        return False, 0, 0

async def main():
    print("=============================================================")
    print("      FRIDAY SPECIFIC VOICE VALIDATION RUNNER")
    print("=============================================================")
    
    results = {}
    for name, text in QUERIES.items():
        ok, char_count, duration = await validate_query(name, text)
        results[name] = {"ok": ok, "chars": char_count, "duration": duration}
        
    print("\n=============================================================")
    print("                  FINAL VALIDATION SUMMARY")
    print("=============================================================")
    for name, data in results.items():
        status = "PASSED" if data["ok"] else "FAILED"
        print(f"- {name:20} : {status:6} | Chars: {data['chars']:4} | Time: {data['duration']:.2f}s")
    print("=============================================================")

if __name__ == "__main__":
    asyncio.run(main())
