import sys
import os
import asyncio

sys.path.append(os.path.abspath("backend"))

from brain.intent_parser import parse_intent

async def main():
    q = "Show route to London."
    print("Parsing query:", q)
    res = parse_intent(q)
    print("Parsed result:", res)

if __name__ == "__main__":
    asyncio.run(main())
