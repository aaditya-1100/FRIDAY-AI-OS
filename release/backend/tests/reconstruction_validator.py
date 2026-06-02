"""
reconstruction_validator.py — Exhaustive 500-Test Validation Suite for FRIDAY.
Runs 100 tests per category, verifying weighted semantic routing correctness
and writing detailed execution logs.
"""

import sys
import os
import time

# Ensure backend root is on path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_path)

from brain.planner import PlannerBrain


def generate_command_cases():
    cases = []
    # 1. App opens (20)
    apps = ["chrome", "spotify", "vscode", "notepad", "calculator", "paint", "cmd", "settings", "explorer", "file explorer"]
    for app in apps:
        cases.append((f"open {app}", "NATIVE_OS", True))
        cases.append((f"start {app}", "NATIVE_OS", True))
    
    # 2. Closings (20)
    for app in apps:
        cases.append((f"close {app}", "NATIVE_OS", True))
        cases.append((f"quit {app}", "NATIVE_OS", False)) # Complex closing/fuzzy
        
    # 3. Media Controls (20)
    cases.extend([
        ("volume up", "MEDIA", True),
        ("volume down", "MEDIA", True),
        ("mute volume", "MEDIA", False),
        ("unmute volume", "MEDIA", False),
        ("play some lofi", "MEDIA", False),
        ("pause the music", "MEDIA", False),
        ("resume spotify playback", "MEDIA", False),
        ("skip this track", "MEDIA", False),
        ("next song", "MEDIA", False),
        ("previous song", "MEDIA", False)
    ] * 2)
    
    # 4. Folder opens (20)
    folders = ["downloads", "documents", "desktop", "c drive", "d drive"]
    for folder in folders:
        cases.append((f"open {folder}", "NATIVE_OS", True))
        cases.append((f"start {folder}", "NATIVE_OS", True))
        cases.append((f"show my {folder}", "NATIVE_OS", False))
        cases.append((f"navigate to {folder}", "NATIVE_OS", False))
        
    # 5. System commands (20)
    sys_cmds = ["shutdown", "restart", "sleep", "lock pc"]
    for cmd in sys_cmds:
        cases.append((cmd, "NATIVE_OS", True))
        cases.append((f"please {cmd} my computer", "NATIVE_OS", False))
        cases.append((f"force {cmd}", "NATIVE_OS", False))
        cases.append((f"go to {cmd} mode", "NATIVE_OS", False))
        cases.append((f"pc {cmd}", "NATIVE_OS", False))
        
    return cases[:100]


def generate_memory_cases():
    cases = []
    # 1. Creator (20)
    creator_queries = [
        "who is aaditya", "tell me about aaditya", "who built you", "who is my creator",
        "who is your developer", "who is your master", "built by aaditya", "aaditya's details",
        "know about aaditya", "tell me creator name", "developer of friday", "who designed friday",
        "master developer aaditya", "built by who", "creator identity", "who is the creator",
        "developer details", "master aaditya profile", "origin of friday", "aaditya credentials"
    ]
    for q in creator_queries:
        cases.append((q, "MEMORY", False))
        
    # 2. Companion Identity (20)
    companion_queries = [
        "who are you", "what is your name", "are you friday", "who is friday",
        "tell me about yourself", "your background friday", "explain yourself",
        "introduce yourself", "friday name origin", "identity of friday",
        "are you a robot", "what is your function", "who developed friday",
        "whats your name", "who is the assistant", "tell me about friday",
        "are you the real friday", "friday identity check", "your creator name", "friday resume"
    ]
    for q in companion_queries:
        cases.append((q, "MEMORY", False))
        
    # 3. User info (20)
    user_queries = [
        "what is my name", "do you know me", "who am i", "remember my details",
        "what do you know about me", "my profile", "my identity", "who am i sir",
        "my target name", "know about me", "my profile summary", "personal details",
        "tell me about me", "what is my target", "what are my goals", "my target goal",
        "my targets", "my preferences", "my class details", "who is logged in"
    ]
    for q in user_queries:
        cases.append((q, "MEMORY", False))
        
    # 4. Preferences / Goals (20)
    pref_queries = [
        "what are my goals", "my favorite app", "my target JEE score", "my class targets",
        "what do i want to achieve", "my target exam", "my target class", "my preferences",
        "my favorite genre", "my default city", "my preferred location", "my workspace targets",
        "my current goals", "my class targets", "my class target details", "what is my default city",
        "my favorite desktop app", "my target JEE exam", "goals list for me", "my target workspaces"
    ]
    for q in pref_queries:
        cases.append((q, "MEMORY", False))
        
    # 5. General Memory Keys (20)
    general_queries = [
        "what do you remember about me", "my relational facts", "facts about me",
        "my personal profile", "what are my goals listed", "my target workspaces list",
        "relational facts about me", "what do you know of me", "who am i to you",
        "my favorite programming language", "my mapped favorite app", "my default city name",
        "what is my favorite music", "my target score details", "my goal list", "who built this system",
        "what is my creator's name", "tell me who built friday", "who is aaditya sir", "my target class name"
    ]
    for q in general_queries:
        cases.append((q, "MEMORY", False))
        
    return cases[:100]


def generate_search_cases():
    cases = []
    # 1. Weather (20)
    cities = ["delhi", "mumbai", "london", "paris", "tokyo", "kashipur", "new york", "sydney", "berlin", "moscow"]
    for city in cities:
        cases.append((f"weather in {city}", "RETRIEVAL", False))
        cases.append((f"is it raining in {city} today", "RETRIEVAL", False))
        
    # 2. News (20)
    topics = ["ai", "tech", "election", "sports", "world news", "business", "market updates", "spacex", "apple", "google"]
    for topic in topics:
        cases.append((f"latest news about {topic}", "RETRIEVAL", False))
        cases.append((f"what happened in {topic} recently", "RETRIEVAL", False))
        
    # 3. Stocks (20)
    companies = ["tesla", "apple", "microsoft", "nvidia", "google", "meta", "amazon", "reliance", "tcs", "tata"]
    for comp in companies:
        cases.append((f"stock price of {comp}", "RETRIEVAL", False))
        cases.append((f"current price of {comp} stock today", "RETRIEVAL", False))
        
    # 4. Sports / Recency (20)
    sports = [
        "ipl match score today", "cricket match score", "who won the match today",
        "who leads the standings", "nba leaderboard score", "premier league standings news",
        "champions league match result", "world cup schedule updates", "nfl live score currently",
        "who leads the championship", "formula 1 standings today", "who won the game tonight",
        "tennis match schedule", "who leads the leaderboard match", "ipl score live now",
        "cricket standings today", "t20 score currently", "news match live scores",
        "latest sports score news", "who leads the tournament score"
    ]
    for q in sports:
        cases.append((q, "RETRIEVAL", False))
        
    # 5. General Recency (20)
    recency = [
        "trending news right now", "viral video today", "breaking news this hour",
        "what's new in AI updates", "latest announcement from openai", "current prime minister of uk",
        "who won the election today", "what is happening in global events now", "upcoming tech launches",
        "tesla share price now", "weather forecast today", "bitcoin price at the moment",
        "headlines news right now", "newest iphone features updates", "news summit event today",
        "viral trending matches right now", "ipl points table today", "latest box office records",
        "who won the cricket cup today", "trending news headlines currently"
    ]
    for q in recency:
        cases.append((q, "RETRIEVAL", False))
        
    return cases[:100]


def generate_conversation_cases():
    cases = []
    # 1. Greetings (20)
    greetings = [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening", "good night",
        "sup", "yo", "what's up", "hey friday how's your day", "hello there companion",
        "sup buddy", "yo friday", "greetings companion", "good morning friday", "good evening buddy",
        "how's everything going", "greetings", "hello friday"
    ]
    for q in greetings:
        cases.append((q, "LLM", False))
        
    # 2. Acknowledgments (20)
    acks = [
        "thank you", "thanks", "got it", "nice", "gotcha", "cool", "perfect", "awesome",
        "alright", "okay", "thanks buddy", "great job", "perfect friday", "got it thank you",
        "awesome thanks", "cool buddy", "gotcha sir", "alright got it", "nice work", "thanks a lot"
    ]
    for q in acks:
        cases.append((q, "LLM", False))
        
    # 3. Chit-chat / Jokes (20)
    chitchat = [
        "how are you", "are you fine", "tell me a joke", "make me laugh", "say a joke",
        "how is your day", "are you happy", "tell me a funny story", "are you doing well",
        "how is the system feeling", "make a funny joke", "are you awake right now",
        "are you a human", "are you alive", "tell me something funny", "how do you feel",
        "are you happy with your code", "are you feeling good", "tell me a joke buddy", "humor me"
    ]
    for q in chitchat:
        cases.append((q, "LLM", False))
        
    # 4. Knowledge (40)
    knowledge = [
        "explain gravity", "what is a cpu", "how does a compiler work", "define recursion",
        "difference between compiler and interpreter", "what are prime numbers", "explain photosynthesis",
        "how does the heart work", "what is quantum computing", "explain machine learning",
        "what is dark matter", "how do stars form", "what is thermodynamics", "explain relativity",
        "how does internet work", "what is dns", "how do databases index data", "explain tcp ip",
        "what is neural network", "how does cell division work", "explain gravity in simple words",
        "what is absolute zero", "how do black holes work", "explain dna structure",
        "what is artificial intelligence", "how does wind energy work", "what is cellular respiration",
        "explain evolution", "what is chemical equilibrium", "how do batteries store energy",
        "what is clean energy", "explain water cycle", "what is plate tectonics",
        "how does radar work", "what is virtual memory", "explain sorting algorithms",
        "what is binary search", "how does encryption work", "explain blockchain tech", "what is cloud computing"
    ]
    for q in knowledge:
        cases.append((q, "LLM", False))
        
    return cases[:100]


def generate_mixed_cases():
    cases = []
    # 1. Pronoun resolution cases (30)
    pronoun_queries = [
        "open it", "close that", "play that again", "do it again", "what's the weather there",
        "tell me more about him", "how old is he", "what is its population", "minimize it",
        "maximize that", "close it again", "start it up", "launch that application",
        "show me a map there", "is it raining there", "how is he doing", "is it running",
        "focus on that window", "bring it to front", "hide that", "restore it",
        "play some music using it", "what's the forecast there", "who is the prime minister there",
        "what is the price of it", "is it trending", "open documents inside it", "open documents there",
        "lock it now", "restart it"
    ]
    for q in pronoun_queries:
        # Pronoun resolution is handled in ContextManager/IntentParser,
        # but the Planner routes based on pronouns.
        # "open it" has verb "open" -> routes to COMMAND (NATIVE_OS/MEDIA)
        # "how old is he" has "how" -> routes to LLM or memory
        # Let's map target brain based on keywords:
        if any(w in q for w in ("open", "close", "minimize", "maximize", "lock", "restart", "focus", "bring", "hide", "restore", "start", "launch")):
            cases.append((q, "NATIVE_OS", False))
        elif "play" in q:
            cases.append((q, "MEDIA", False))
        elif "weather" in q or "forecast" in q or "raining" in q or "price" in q or "trending" in q or "prime minister" in q:
            cases.append((q, "RETRIEVAL", False))
        else:
            cases.append((q, "LLM", False))
            
    # 2. Ambiguity bare commands (20)
    bare = ["open", "start", "launch", "play", "search", "find", "show", "close", "run", "browse"]
    for b in bare:
        cases.append((b, "LLM", False)) # Ambiguity / Clarification routes to LLM/CLARIFICATION
        cases.append((f"please {b}", "LLM", False))
        
    # 3. Day of week 'friday' references (25)
    # MUST NOT trigger Memory-First Gate! Verifies Correction 2 & 4!
    friday_days = [
        "what's the weather on friday", "will it rain this friday", "friday night forecast",
        "what is the date on friday", "are you busy this friday", "friday evening temperature",
        "friday morning weather in mumbai", "is friday a holiday", "tell me friday's forecast",
        "what should i do this friday night", "friday show match times", "ipl match score on friday",
        "trending topics this friday", "current stock price on friday", "weather on next friday",
        "is friday the last day", "can you check friday weather", "what are friday night plans",
        "cricket match on friday", "friday score standings", "what's the temperature on friday",
        "is it raining friday morning", "friday weather forecast details", "news updates on friday",
        "what is trending this friday"
    ]
    for q in friday_days:
        # Weather/Forecast/Match days trigger RETRIEVAL freshness score
        if any(x in q for x in ("weather", "rain", "forecast", "temperature", "match", "score", "stock", "price", "trending", "news")):
            cases.append((q, "RETRIEVAL", False))
        else:
            cases.append((q, "LLM", False))
            
    # 4. Conversational corrections (25)
    corrections = [
        "no wait open chrome instead", "actually open notepad", "scratch that mute volume",
        "no show map of delhi instead of mumbai", "actually close it", "wait play some lofi music",
        "scratch that restart pc", "no wait start vs code", "actually open documents",
        "no open downloads folder", "wait close this window", "actually make it louder",
        "no wait what is the weather in delhi", "scratch that tell me news about tesla",
        "actually explain gravity instead", "no wait who is aaditya", "actually who built you",
        "no wait who are you", "scratch that what is my target", "actually set a timer",
        "no cancel reminder", "actually what is the current time", "wait lock my pc",
        "scratch that volume up", "no wait show map of paris"
    ]
    for q in corrections:
        if any(w in q for w in ("open chrome", "open notepad", "restart pc", "start vs code", "open documents", "open downloads", "close this", "close it", "lock my")):
            cases.append((q, "NATIVE_OS", False))
        elif any(w in q for w in ("mute volume", "play some lofi", "make it louder", "volume up")):
            cases.append((q, "MEDIA", False))
        elif any(w in q for w in ("weather in delhi", "news about tesla", "current time")):
            cases.append((q, "RETRIEVAL", False))
        elif any(w in q for w in ("who is aaditya", "who built you", "who are you", "what is my target")):
            cases.append((q, "MEMORY", False))
        else:
            cases.append((q, "LLM", False))
            
    return cases[:100]


def run_test_suite():
    print("=" * 60)
    print("FRIDAY RECONSTRUCTION VALIDATION TEST SUITE RUNNER")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    planner = PlannerBrain()
    
    categories = {
        "1. COMMAND TESTS": generate_command_cases(),
        "2. MEMORY TESTS": generate_memory_cases(),
        "3. SEARCH TESTS": generate_search_cases(),
        "4. CONVERSATION TESTS": generate_conversation_cases(),
        "5. MIXED-CONTEXT TESTS": generate_mixed_cases()
    }
    
    log_dir = os.path.join(backend_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "reconstruction_test_results.log")
    
    total_passed = 0
    total_cases = 0
    
    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write("=" * 70 + "\n")
        log_file.write(f"FRIDAY 500-TEST SUITE EXECUTION LOG — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write("=" * 70 + "\n\n")
        
        for category_name, cases in categories.items():
            print(f"Running {category_name} (Count: {len(cases)})...")
            log_file.write(f"=== {category_name} ===\n")
            
            cat_passed = 0
            cat_total = len(cases)
            
            for idx, (query, expected_brain, expected_bypass) in enumerate(cases):
                decision = planner.plan(query)
                resolved = decision.target_brain
                bypass = decision.is_simple_command
                
                # Verify match
                is_correct = (resolved == expected_brain)
                
                # Check direct bypass mapping for commands
                if expected_brain in ("NATIVE_OS", "MEDIA", "TEMPORAL") and expected_bypass:
                    # Assert simple command bypasses are correctly mapped
                    if not bypass:
                        is_correct = False
                
                status = "PASS" if is_correct else "FAIL"
                if is_correct:
                    cat_passed += 1
                    total_passed += 1
                
                total_cases += 1
                
                # Log entry
                log_file.write(
                    f"[{status}] Case #{idx+1:03d} | Query: '{query}'\n"
                    f"      Expected: Brain={expected_brain} Bypass={expected_bypass}\n"
                    f"      Resolved: Brain={resolved} Bypass={bypass} | Score={decision.freshness_score:.1f}\n\n"
                )
                
            pass_rate = (cat_passed / cat_total) * 100
            print(f"      -> Passed: {cat_passed}/{cat_total} ({pass_rate:.1f}%)")
            log_file.write(f"-> CATEGORY RESULT: Passed {cat_passed}/{cat_total} ({pass_rate:.1f}%)\n\n")
            log_file.write("-" * 50 + "\n\n")
            
        overall_rate = (total_passed / total_cases) * 100
        print("=" * 60)
        print(f"OVERALL SUMMARY: Passed {total_passed}/{total_cases} ({overall_rate:.1f}%)")
        print(f"Full log written to: {log_path}")
        print("=" * 60)
        
        log_file.write("=" * 70 + "\n")
        log_file.write(f"OVERALL VALIDATION SUMMARY: Passed {total_passed}/{total_cases} ({overall_rate:.1f}%)\n")
        log_file.write("=" * 70 + "\n")


if __name__ == "__main__":
    run_test_suite()
