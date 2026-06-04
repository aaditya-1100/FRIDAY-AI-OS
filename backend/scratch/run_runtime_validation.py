import asyncio
import json
import os
import sys
import time
import websockets

LOG_FILE = "C:/FRIDAY/backend/friday_runtime.log"

TEST_GROUPS = {
    "Group 1: Direct Song Playback": [
        "Play Believer",
        "Play Shape of You",
        "Play Industry Baby",
        "Play Softly Karan Aujla"
    ],
    "Group 2: Exact Title Playback": [
        "Play video \"How I Built a Million Dollar Business\"",
        "Play video \"Python Tutorial for Beginners\"",
        "Play video \"Marvel Avengers Endgame Trailer\""
    ],
    "Group 3: Latest Creator Playback": [
        "Play latest video by Think School",
        "Play latest video by Raj Shamani",
        "Play latest video by Dan Martell",
        "Play latest video by Vaibhav Sisinty"
    ],
    "Group 4: YouTube Search": [
        "Open YouTube and search Rust ownership model",
        "Open YouTube and search OpenAI",
        "Open YouTube and search AI agents"
    ],
    "Group 5: Search System Validation": [
        "Search OpenAI",
        "Search Rust ownership model",
        "Search latest AI news",
        "Open Chrome and search OpenAI",
        "Open Chrome and search Rust ownership model",
        "Open Chrome and search AI agents"
    ],
    "Group 6: Multi-Action Execution Tests": [
        "Open Calculator and tell me 2+2",
        "Open VS Code and explain recursion",
        "Open Chrome and search OpenAI",
        "Open VS Code and open Chrome",
        "Open Calculator and explain Rust ownership model"
    ],
    "Group 7: Voice Stability & Context Stress": [
        "Hello Friday",
        "Count from 1 to 20",
        "Explain recursion",
        "Explain recursion in 200 words",
        "Compare Rust and Python",
        "Tell me about Apple",
        "What is their primary product?",
        "Who owns the major equity in it?",
        "How much revenue do they make?",
        "Compare it with Microsoft",
        "Explain Rust ownership model in depth",
        "Explain it in depth",
        "What are its advantages?",
        "Compare it with garbage collection"
    ]
}

async def execute_query_ws(websocket, query: str) -> tuple[str, str]:
    # 1. Record current log size
    start_pos = 0
    if os.path.exists(LOG_FILE):
        start_pos = os.path.getsize(LOG_FILE)
        
    # 2. Send command
    cmd = {"type": "command", "text": query}
    await websocket.send(json.dumps(cmd))
    
    # 3. Wait for state to change to THINKING, then to SPEAKING, then back to LISTENING/IDLE
    start_time = time.time()
    state_history = []
    speaking_started = False
    max_wait = 18.0  # Allow up to 18 seconds for heavy search/scraping tasks
    
    while time.time() - start_time < max_wait:
        try:
            msg_str = await asyncio.wait_for(websocket.recv(), timeout=0.8)
            msg = json.loads(msg_str)
            if msg.get("type") == "state":
                state = msg.get("state")
                state_history.append(state)
                if state == "SPEAKING":
                    speaking_started = True
                elif state in ("LISTENING", "IDLE") and speaking_started:
                    break
        except asyncio.TimeoutError:
            pass
            
    # Extra brief sleep for logs to write/flush
    await asyncio.sleep(1.2)
    
    # 4. Extract new logs
    new_logs = ""
    if os.path.exists(LOG_FILE):
        end_pos = os.path.getsize(LOG_FILE)
        if end_pos > start_pos:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(start_pos)
                new_logs = f.read()
                
    # Parse final response text from logs
    response_match = []
    # Search for [TRACE] [SPEAK] or voice.speak or speak event text
    for line in new_logs.splitlines():
        if "ENTERED SAFE_SPEAK | text=" in line:
            parts = line.split("text='", 1)
            if len(parts) == 2:
                response_match.append(parts[1].split("'", 1)[0])
        elif "Speak text: " in line:
            parts = line.split("Speak text: \"", 1)
            if len(parts) == 2:
                response_match.append(parts[1].split("\"", 1)[0])
                
    observed_response = response_match[-1] if response_match else "Action executed (check logs)"
    return observed_response, new_logs

async def main():
    print("=" * 80)
    print("      FRIDAY PRODUCTION RUNTIME VALIDATION RUNNER")
    print("=" * 80)
    
    uri = "ws://127.0.0.1:8001/api/ws"
    
    # Check health first
    try:
        import requests
        requests.get("http://127.0.0.1:8001/api/health", timeout=3)
    except Exception as e:
        print(f"[FATAL ERROR] Backend is not running: {e}")
        sys.exit(1)
        
    results_report = []
    
    async with websockets.connect(uri) as websocket:
        # Drain initial messages
        try:
            await asyncio.wait_for(websocket.recv(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
            
        for group_name, queries in TEST_GROUPS.items():
            print(f"\n{'#'*40}\nStarting {group_name}\n{'#'*40}")
            results_report.append(f"\n## {group_name}\n")
            
            for query in queries:
                print(f"- Query: '{query}'")
                resp, logs = await execute_query_ws(websocket, query)
                print(f"  Response: {resp}")
                
                # Format to Markdown
                safe_logs = logs.encode("ascii", errors="replace").decode("ascii")
                results_report.append(
                    f"### Command: `{query}`\n"
                    f"- **Observed Response:** {resp}\n"
                    f"- **Runtime Logs:**\n"
                    f"```text\n{safe_logs.strip()}\n```\n"
                )
                # Brief sleep between queries to clear context and prevent API rate-limits
                await asyncio.sleep(2.0)
                
    # Save the report to artifacts
    report_path = "C:/Users/gpska/.gemini/antigravity/brain/ed77be79-4bc1-407b-986c-6851b00f25f2/runtime_validation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# FRIDAY Production App Runtime Validation Report\n\n")
        f.write(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("".join(results_report))
        
    print(f"\n[SUCCESS] Runtime validation complete. Report saved to: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
