"""
ws_test.py — WebSocket pipeline end-to-end test.
Sends commands and collects all responses for 20 seconds each.
"""
import asyncio
import json
import websockets

WS_URL = "ws://127.0.0.1:8001/api/ws"

async def send_command(cmd: str, timeout: float = 20.0):
    """Connect, send a command, collect all messages until timeout or IDLE."""
    print(f"\n{'='*60}")
    print(f"CMD: {cmd!r}")
    print(f"{'='*60}")
    responses = []
    try:
        async with websockets.connect(WS_URL) as ws:
            # Send mic sync first
            await ws.send(json.dumps({"type": "mic_on"}))
            # Send command
            await ws.send(json.dumps({"type": "command", "text": cmd}))

            try:
                deadline = asyncio.get_event_loop().time() + timeout
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        print("  [TIMEOUT]")
                        break
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 3.0))
                    data = json.loads(msg)
                    responses.append(data)
                    t = data.get("type")
                    if t == "state":
                        print(f"  [STATE] {data.get('state')}")
                        if data.get("state") == "IDLE" and len(responses) > 2:
                            # Back to IDLE after doing work = done
                            break
                    elif t == "transcript":
                        print(f"  [TRANSCRIPT] {data.get('text')!r}")
                    elif t == "speak":
                        print(f"  [SPEAK] {data.get('text')!r}")
                    elif t == "audio":
                        b64 = data.get("audioBase64", "")
                        print(f"  [AUDIO] {len(b64)} bytes base64")
                    elif t == "result":
                        ok = data.get("ok")
                        intent = data.get("intent")
                        print(f"  [RESULT] ok={ok} intent={intent}")
                    elif t == "show_map":
                        print(f"  [MAP] location={data.get('location')!r}")
                    else:
                        print(f"  [{t.upper()}] {data}")
            except asyncio.TimeoutError:
                pass

    except Exception as e:
        print(f"  [ERROR] {e}")

    return responses


async def main():
    print("FRIDAY WEBSOCKET PIPELINE TESTS")

    # Test 1: Weather query
    r = await send_command("what is the weather in Mumbai")
    speak_msgs = [m for m in r if m.get("type") == "speak"]
    audio_msgs = [m for m in r if m.get("type") == "audio"]
    print(f"  -> speak: {len(speak_msgs)}, audio: {len(audio_msgs)}")

    # Test 2: Map command
    r = await send_command("show me a map of Tokyo")
    map_msgs = [m for m in r if m.get("type") == "show_map"]
    print(f"  -> map events: {len(map_msgs)}")

    # Test 3: AI query
    r = await send_command("what is the speed of light")
    speak_msgs = [m for m in r if m.get("type") == "speak"]
    print(f"  -> speak: {len(speak_msgs)}")

    # Test 4: Realtime query
    r = await send_command("who won the last IPL match")
    speak_msgs = [m for m in r if m.get("type") == "speak"]
    print(f"  -> speak: {len(speak_msgs)}")

    # Test 5: Context continuity (follow-up)
    r1 = await send_command("show me a map of London")
    r2 = await send_command("what is the weather there")  # 'there' should resolve to London
    speak_msgs = [m for m in r2 if m.get("type") == "speak"]
    if speak_msgs:
        print(f"  -> context followup response: {speak_msgs[0].get('text')[:100]!r}")

    print("\nAll WebSocket tests complete.")


if __name__ == "__main__":
    asyncio.run(main())
