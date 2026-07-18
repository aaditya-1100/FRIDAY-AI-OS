import time
print("Starting import test...")
t0 = time.time()

print("Importing spacy...")
import spacy
print(f"Imported spacy in {time.time() - t0:.2f}s")

t1 = time.time()
print("Loading en_core_web_sm...")
nlp = spacy.load("en_core_web_sm")
print(f"Loaded en_core_web_sm in {time.time() - t1:.2f}s")

t2 = time.time()
print("Importing qdrant_client...")
from qdrant_client import QdrantClient
print(f"Imported qdrant_client in {time.time() - t2:.2f}s")

t3 = time.time()
print("Importing fsm...")
from friday.core.fsm import CognitiveFSM
print(f"Imported fsm in {time.time() - t3:.2f}s")

print(f"Total time: {time.time() - t0:.2f}s")
