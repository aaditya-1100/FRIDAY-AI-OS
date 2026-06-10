import asyncio
from loguru import logger
from playwright.async_api import async_playwright

async def test():
    logger.info("Starting Playwright...")
    p = await async_playwright().start()
    logger.info("Playwright started. Launching Chromium...")
    b = await p.chromium.launch(headless=True)
    logger.info("Chromium launched successfully!")
    await b.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(test())
