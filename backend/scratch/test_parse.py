import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.intent_parser import parse_intent

queries = [
    "Open latest video by Paramvir Beniwal",
    "Open latest video by Mark Rober",
    "Show newest upload from Think School",
    "Play latest video by Raj Shamani",
    "Open newest video from Tanmay Bhat",
    "Search YouTube for AI news",
    "Search YouTube for Marvel trailers",
    "Search YouTube for JEE Physics lectures",
    "Search YouTube for Python tutorials",
    "Search YouTube for Tesla news",
    "Open latest short by Mark Rober",
    "Show newest short by Paramvir Beniwal",
    "Open video titled X",
    "Play video X",
]

for q in queries:
    res = parse_intent(q)
    print(f"Query: '{q}'\n  -> Intent: {res.get('intent')}\n  -> Creator: {res.get('creator')}\n  -> Query Field: {res.get('query')}\n  -> Title: {res.get('title')}\n")
