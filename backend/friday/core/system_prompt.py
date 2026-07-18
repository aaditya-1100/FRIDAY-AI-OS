# backend/friday/core/system_prompt.py

from typing import Dict, Any, Optional
from uuid import UUID

def assemble_system_prompt(working_memory: Dict[str, Any], system_context_data: Dict[str, Any], screen_context: Optional[Dict[str, Any]] = None) -> str:
    # 1. Identity (never truncated)
    detected_lang = working_memory.get("detected_language", "en")
    lang_name = "Hindi" if detected_lang == "hi" else ("English" if detected_lang == "en" else detected_lang)
    if detected_lang == "hi":
        lang_instruction = " The user's message is in Hindi/Hinglish. Respond in the same language. If the message is in Hindi or Hinglish, respond in Hindi or Hinglish to match."
    else:
        lang_instruction = f" The user's message is in {lang_name}. Respond in the same language."
    identity_str = f"You are FRIDAY, a personal AI assistant. You are helpful, concise, and intelligent. You never pad responses unnecessarily.{lang_instruction}"
    
    # 2. Behavioral rules (never truncated)
    rules_str = "Rules: Be direct. Never verbosely restate the question. If uncertain: say so. If information is unavailable: say so clearly. Never ask the user to confirm their intent or ask confirmation-style questions. Execute commands directly. Only ask 'yes or no' style questions if it is a file deletion request."
    
    plan_type = working_memory.get("plan_type")
    if plan_type not in ("DIRECT_LLM", "WEB_SYNTHESIS"):
        from friday.core.proactive_engine import proactive_engine
        context_mode = getattr(proactive_engine, "_detected_context_mode", "idle")
        if context_mode == "coding":
            rules_str += " User is currently coding. Prioritize code-related answers, use technical language."
        elif context_mode == "study":
            rules_str += " User is currently studying. Prioritize study and learning assistance, skew answers toward learning."
        elif context_mode == "gaming":
            rules_str += " User is currently gaming. Keep responses extremely short, suppress proactive recommendations, prioritize minimal interruptions."
    
    # 3. System context
    def get_system_context(compact=False) -> str:
        lines = []
        if system_context_data.get("current_time"):
            lines.append(f"time: {system_context_data.get('current_time')}")
        if system_context_data.get("current_date"):
            lines.append(f"date: {system_context_data.get('current_date')}")
        if not compact:
            if system_context_data.get("battery_level") is not None:
                lines.append(f"battery: {system_context_data.get('battery_level')}%")
            if system_context_data.get("active_window"):
                lines.append(f"active_window: {system_context_data.get('active_window')}")
            if system_context_data.get("cpu_percent") is not None:
                lines.append(f"cpu: {system_context_data.get('cpu_percent')}%")
            if system_context_data.get("memory_percent") is not None:
                lines.append(f"memory: {system_context_data.get('memory_percent')}%")
        return "\n".join(lines)

    system_context_str = get_system_context(compact=False)
    
    # 3b. Screen Context
    screen_context_str = ""
    if screen_context and isinstance(screen_context, dict):
        active_window = screen_context.get("active_window") or "Unknown"
        ocr_text = screen_context.get("ocr_text") or ""
        ocr_excerpt = ocr_text[:500]
        screen_context_str = f"Current screen: {active_window}\nScreen text (excerpt): {ocr_excerpt}"

    # 4. Tool results
    def get_tool_results(limit=1000) -> str:
        results_list = []
        for r in working_memory.get("agent_results", []):
            res_str = f"- Task ID: {r.get('task_id')}, Status: {r.get('status')}, Payload: {r.get('payload')}"
            if len(res_str) > limit:
                res_str = res_str[:limit] + "... [truncated]"
            results_list.append(res_str)
        return "\n".join(results_list)

    tool_results_str = get_tool_results(limit=1000)
    
    # 5. Memory context (omitted entirely if empty)
    mem_ctx = working_memory.get("memory_context") or {}
    sem_facts = mem_ctx.get("semantic_facts") or []
    rec_epi = mem_ctx.get("recent_episodes") or []
    
    memory_context_str = ""
    if sem_facts or rec_epi:
        memory_lines = []
        if sem_facts:
            memory_lines.append(f"Relevant context from memory: {sem_facts}")
        if rec_epi:
            memory_lines.append(f"Recent conversation history: {rec_epi}")
        memory_context_str = "\n".join(memory_lines)

    # 6. Conversation history
    def get_history(num_turns=6) -> str:
        history_turns = working_memory.get("conversation_history", [])[-num_turns:]
        history_list = []
        for turn in history_turns:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            history_list.append(f"{role}: {content}")
        return "\n".join(history_list)

    history_str = get_history(num_turns=6)
    
    # Helper to construct
    def construct(s3: str, s3b: str, s4: str, s5: str, s6: str) -> str:
        parts = [
            f"1. Identity\n{identity_str}",
            f"2. Behavioral Rules\n{rules_str}"
        ]
        if s3:
            parts.append(f"3. System Context\n{s3}")
        if s3b:
            parts.append(f"3b. Screen Context\n{s3b}")
        if s4:
            parts.append(f"4. Tool Results\n{s4}")
        if s5:
            parts.append(f"5. Memory Context\n{s5}")
        if s6:
            parts.append(f"6. Conversation History\n{s6}")
        return "\n\n".join(parts)

    prompt = construct(system_context_str, screen_context_str, tool_results_str, memory_context_str, history_str)
    
    # Check budget
    if len(prompt) / 3 > 8000:
        # Step 0: truncate screen context to 200 chars
        if screen_context_str:
            screen_context_str = screen_context_str[:200] + "... [truncated]"
        prompt = construct(system_context_str, screen_context_str, tool_results_str, memory_context_str, history_str)
        
    if len(prompt) / 3 > 8000:
        # Step 0b: drop screen context entirely
        screen_context_str = ""
        prompt = construct(system_context_str, screen_context_str, tool_results_str, memory_context_str, history_str)
        
    if len(prompt) / 3 > 8000:
        # Step 1: truncate section 5 (memory context) to 500 chars
        if len(memory_context_str) > 500:
            memory_context_str = memory_context_str[:500] + "... [truncated]"
        prompt = construct(system_context_str, screen_context_str, tool_results_str, memory_context_str, history_str)
        
    if len(prompt) / 3 > 8000:
        # Step 2: truncate section 6 (history) to last 2 turns
        history_str = get_history(num_turns=2)
        prompt = construct(system_context_str, screen_context_str, tool_results_str, memory_context_str, history_str)
        
    if len(prompt) / 3 > 8000:
        # Step 3: truncate section 3 (system context) to time+date only
        system_context_str = get_system_context(compact=True)
        prompt = construct(system_context_str, screen_context_str, tool_results_str, memory_context_str, history_str)
        
    if len(prompt) / 3 > 8000:
        # Step 4: truncate section 4 (tool results) to 200 chars each
        tool_results_str = get_tool_results(limit=200)
        prompt = construct(system_context_str, screen_context_str, tool_results_str, memory_context_str, history_str)
        
    return prompt
