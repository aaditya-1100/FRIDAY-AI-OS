import asyncio
import sys
import re

from execution.action_executor import extract_media_entities, resolve_youtube_media_url

def test_extraction():
    test_cases = [
        ("Open latest video by Mark Rober", {"creator": "Mark Rober", "title": None, "modifier": "latest", "topic": None, "platform": "youtube"}),
        ("Open fluid dynamics video by Mark Rober", {"creator": "Mark Rober", "title": "fluid dynamics", "modifier": None, "topic": None, "platform": "youtube"}),
        ("play some ASMR by arbitrary creator", {"creator": "arbitrary creator", "title": None, "modifier": None, "topic": "ASMR", "platform": "youtube"}),
        ("play lofi on spotify", {"creator": None, "title": None, "modifier": None, "topic": "lofi", "platform": "spotify"}),
        ("watch popular video of think school", {"creator": "think school", "title": None, "modifier": "popular", "topic": None, "platform": "youtube"})
    ]
    
    print("--- Running Extraction Tests ---")
    for q, expected in test_cases:
        res = extract_media_entities(q)
        for k in expected:
            assert res[k] == expected[k], f"Fail for '{q}': expected {k}={expected[k]}, got {res[k]}"
        print(f"PASS: '{q}' -> {res}")

async def test_resolution():
    print("--- Running Resolution Tests ---")
    # Resolve channel and latest video for Mark Rober (requires network)
    try:
        url = resolve_youtube_media_url("Mark Rober", None, "latest", None, "latest by Mark Rober")
        print(f"Mark Rober Latest Video Watch URL: {url}")
        assert url is not None, "Failed to resolve Mark Rober latest video watch URL!"
        assert "watch?v=" in url, f"Expected watch URL, got '{url}'"
        print("PASS: Resolved latest video from Mark Rober!")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_extraction()
    asyncio.run(test_resolution())
