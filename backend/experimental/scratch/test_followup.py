import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pipeline import context_manager
from brain.intent_parser import parse_intent
from execution.action_executor import execute_action

async def main():
    # 1. Setup mock MapSession for "Paris to London"
    context_manager.graph.update_map_session(
        route_origin="Paris",
        route_destination="London",
        distance="470 km",
        duration="5 hours 30 mins",
        duration_in_traffic="5 hours 45 mins",
        cities_crossed=["Calais", "Dover", "Folkestone", "Maidstone"],
        travel_mode="driving",
        current_map_location="London"
    )
    
    # Verify it updated in context graph
    sess = context_manager.graph.get_map_session()
    print(f"Map Session Initialized: {sess.route_origin} -> {sess.route_destination} | Distance: {sess.distance} | Duration: {sess.duration}\n")
    
    # 2. Test "how long ?" follow-up query
    q = "how long ?"
    intent_res = parse_intent(q)
    print(f"Query: '{q}' -> Parsed Intent: {intent_res}\n")
    
    # 3. Execute action E2E
    resp = await execute_action(intent_res)
    print(f"E2E Execution Response:\n{resp}\n")
    
    # 4. Test "what cities ?" follow-up query
    q2 = "what cities ?"
    intent_res2 = parse_intent(q2)
    print(f"Query: '{q2}' -> Parsed Intent: {intent_res2}\n")
    
    # 5. Execute cities action E2E
    resp2 = await execute_action(intent_res2)
    print(f"E2E Execution Response:\n{resp2}\n")

if __name__ == "__main__":
    asyncio.run(main())
