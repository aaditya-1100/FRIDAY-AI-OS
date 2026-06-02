import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.intent_parser import parse_intent

def test():
    query = "Open latest video by Mark Rober"
    print(f"Query: '{query}'")
    result = parse_intent(query)
    print("Result:")
    print(result)

if __name__ == "__main__":
    test()
