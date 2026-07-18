import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from loguru import logger
logger.info("Importing MemoryAgent...")
from friday.agents import MemoryAgent
logger.info("Imported successfully. Instantiating MemoryAgent...")
mem = MemoryAgent()
logger.info("MemoryAgent instantiated successfully!")
