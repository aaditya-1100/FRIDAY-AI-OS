from voice.speak import cancel_play

def cancel_speak() -> None:
    """Signal the current TTS to stop immediately."""
    cancel_play()
    
    # Transition FSM to IDLE state
    try:
        from friday.core.fsm import cognitive_core
        from friday.core.events import AssistantState
        if cognitive_core and cognitive_core.fsm:
            # Force transition to IDLE
            cognitive_core.fsm.transition_to(AssistantState.IDLE, reason="Cancellation requested", force=True)
    except Exception:
        pass
