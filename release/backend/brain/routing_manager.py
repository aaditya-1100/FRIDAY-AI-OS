import os
import re

class RoutingManager:
    """
    Simple API Router for FRIDAY.
    Routes to GROQ for general queries, SERPER for live information.
    No model arbitration, no escalation, no duplicate responses.
    """

    def __init__(self):
        # Keywords indicating need for live information
        self.live_info_keywords = {
            "latest", "current", "breaking news", "headlines", "weather", 
            "temperature", "stock price", "sports score", "who won", 
            "trending now", "who is the prime minister", "crypto prices",
            "Sensex", "Nifty", "ipl schedule", "current events", "today's updates",
            "news", "election", "price", "recent", "today"
        }

    def needs_live_info(self, query: str) -> bool:
        """
        Determines if query requires live information from SERPER.
        Returns True for: current events, news, weather, sports, elections, prices, recent information.
        """
        q = query.lower()
        return any(keyword in q for keyword in self.live_info_keywords)

    def execute_route(self, query: str, system_prompt: str = None, history: list = None, image_b64: str = None) -> str:
        """
        Executes the query with simple routing:
        - If needs live info: SERPER -> GROQ
        - Otherwise: GROQ directly
        """
        if self.needs_live_info(query):
            print(f"[ROUTER] Query needs live info: '{query[:50]}' -> SERPER -> GROQ")
            from system.live_data import realtime_web_query
            return realtime_web_query(query)
        else:
            print(f"[ROUTER] Query to GROQ: '{query[:50]}'")
            from llm.groq_client import ask_groq, DEFAULT_MODEL
            return ask_groq(query, system_prompt=system_prompt, model=DEFAULT_MODEL, history=history)
