import asyncio
import os
import re
from uuid import uuid4
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from friday.vision.screen_reader import screen_reader
from friday.system.context import system_context


def vision_response_formatter(text: str) -> str:
    """Post-process VLM screen descriptions before sending to TTS.

    - Strips markdown: **, *, ##, leading - bullet markers
    - Removes generic openers: 'I can see', 'I notice', 'The screen shows'
    - Normalises symbols for speech: % -> percent, & -> and, > -> greater than
    - Truncates to 3 sentences maximum
    """
    if not text or not text.strip():
        return text

    # Strip markdown formatting characters
    t = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)  # **bold** and *italic*
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)  # ## headers
    t = re.sub(r'^[-\*]\s+', '', t, flags=re.MULTILINE)   # - bullet points

    # Remove generic openers that add no information
    openers = [
        r'^I can see[,:]?\s*',
        r'^I notice[,:]?\s*',
        r'^The screen (shows|displays|is showing)[,:]?\s*',
        r'^Looking at the screen[,:]?\s*',
        r'^On the screen[,:]?\s*',
        r'^Currently[,:]?\s*',
    ]
    for pattern in openers:
        t = re.sub(pattern, '', t, flags=re.IGNORECASE)

    # Capitalise first letter after stripping opener
    t = t.strip()
    if t:
        t = t[0].upper() + t[1:]

    # Normalise symbols for spoken output
    t = t.replace('%', ' percent')
    t = t.replace('&', ' and ')
    t = re.sub(r'(?<=[0-9])>(?=[0-9])', ' greater than ', t)
    t = re.sub(r'\s{2,}', ' ', t)  # collapse double spaces

    # Truncate to 3 sentences
    # Split on sentence-ending punctuation followed by a space or end of string
    sentences = re.split(r'(?<=[.!?])\s+', t.strip())
    if len(sentences) > 3:
        t = ' '.join(sentences[:3])
        if not t.endswith(('.', '!', '?')):
            t += '.'

    return t.strip()


class VisionAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.VISION_AGENT)

    async def startup(self) -> None:
        logger.info("[VisionAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[VisionAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return ["SCREEN_READ", "SCREEN_FIND", "SCREEN_SCREENSHOT", "SCREEN_DESCRIBE",
                "SCREEN_UNDERSTANDING", "SCREENSHOT", "SCREEN_CLICK"]

    def _ok(self, dispatch, payload):
        return TaskResult(
            task_id=dispatch.task_id, agent_id=self.agent_id,
            status=TaskStatus.SUCCESS, payload=payload,
            correlation_id=dispatch.correlation_id
        )

    def _fail(self, dispatch, error: str):
        return TaskResult(
            task_id=dispatch.task_id, agent_id=self.agent_id,
            status=TaskStatus.FAILED, payload={"error": error},
            correlation_id=dispatch.correlation_id
        )

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        parameters = dispatch.parameters or {}

        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[VisionAgent] Permission denied for intent: {intent}")
            return self._fail(dispatch, "Permission denied")

        try:
            if intent == "SCREEN_READ":
                image = await asyncio.to_thread(screen_reader.screenshot)
                result = await asyncio.to_thread(screen_reader.extract_structured, image)
                full_text = result.get("full_text", "").strip() if isinstance(result, dict) else ""
                if not full_text:
                    logger.warning("[VisionAgent] SCREEN_READ returned empty OCR result.")
                    return self._fail(dispatch, "could not read text from screen")
                return self._ok(dispatch, {"text": result, "response": full_text, **(result if isinstance(result, dict) else {})})

            elif intent == "SCREEN_FIND":
                query = parameters.get("query") or ""
                image = await asyncio.to_thread(screen_reader.screenshot)
                bbox = await asyncio.to_thread(screen_reader.find_text, image, query)
                return self._ok(dispatch, {"found": bbox is not None, "bbox": bbox})

            elif intent in ("SCREEN_SCREENSHOT", "SCREENSHOT"):
                # SCREENSHOT: capture and save without continuous background capture
                image = await asyncio.to_thread(screen_reader.screenshot)
                from config.paths import get_data_path
                SCREENSHOTS_DIR = get_data_path("screenshots")
                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                path = os.path.join(SCREENSHOTS_DIR, f"{uuid4()}.png")
                await asyncio.to_thread(image.save, path)
                return self._ok(dispatch, {"path": path, "response": f"Screenshot saved, sir."})

            elif intent == "SCREEN_DESCRIBE":
                query = parameters.get("query", "")
                image = await asyncio.to_thread(screen_reader.screenshot)
                description = await asyncio.to_thread(screen_reader.describe_screen, image, query)
                description = vision_response_formatter(description)
                active_window = system_context.get_context().get("active_window", "")
                return self._ok(dispatch, {"ocr_text": description, "description": description, "active_window": active_window, "response": description})

            elif intent == "SCREEN_UNDERSTANDING":
                # Routes to ScreenAgent.capture_and_analyze() — identical to monolith path
                # No continuous/background capture — single-shot only
                from system.screen_agent import ScreenAgent
                query = parameters.get("query", "what is on my screen?")
                agent = ScreenAgent()
                result = await agent.capture_and_analyze(query)
                if isinstance(result, dict):
                    # Apply voice formatter to any text response from the VLM
                    if "response" in result:
                        result["response"] = vision_response_formatter(result["response"])
                    return self._ok(dispatch, result)
                return self._ok(dispatch, {"response": vision_response_formatter(str(result))})

            elif intent == "SCREEN_CLICK":
                target = parameters.get("target") or parameters.get("query") or ""
                if not target:
                    return self._fail(dispatch, "No target element specified to click.")
                
                import pyautogui
                screen_w, screen_h = pyautogui.size()
                
                target_lower = target.lower().strip()
                coords = None
                
                if "search bar" in target_lower or "search box" in target_lower:
                    coords = (int(screen_w * 0.5), int(screen_h * 0.08))
                
                found = False
                if coords:
                    x, y = coords
                    found = True
                    element_name = target
                else:
                    image = await asyncio.to_thread(screen_reader.screenshot)
                    import io, base64
                    buffered = io.BytesIO()
                    image.save(buffered, format="JPEG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    
                    import httpx
                    import json
                    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
                    if not ollama_host.startswith("http://") and not ollama_host.startswith("https://"):
                        ollama_host = f"http://{ollama_host}"
                        
                    model_name = "qwen2.5-vl:7b"
                    prompt = (
                        f"In this screenshot, find the UI element described as '{target}'. "
                        f"Return ONLY a raw JSON object (no markdown formatting, no backticks, no other text): "
                        f'{{"x": <int>, "y": <int>, "found": <bool>, "element": "{target}"}} '
                        f"where x and y are the exact pixel coordinates of the center of that element on a screen of width {screen_w} and height {screen_h}."
                    )
                    
                    try:
                        payload = {
                            "model": model_name,
                            "prompt": prompt,
                            "system": "You are a precise screen coordinate finder. Always respond with raw JSON only.",
                            "images": [img_base64],
                            "stream": False
                        }
                        loop = asyncio.get_running_loop()
                        
                        def call_ollama():
                            r = httpx.post(f"{ollama_host}/api/generate", json=payload, timeout=30.0)
                            if r.status_code == 200:
                                return r.json().get("response", "").strip()
                            return ""
                            
                        response_str = await loop.run_in_executor(None, call_ollama)
                        if response_str:
                            clean_json = response_str
                            if "```" in clean_json:
                                clean_json = clean_json.split("```")[-2]
                                if clean_json.startswith("json"):
                                    clean_json = clean_json[4:]
                            clean_json = clean_json.strip()
                            
                            data = json.loads(clean_json)
                            if data.get("found"):
                                coords = (int(data["x"]), int(data["y"]))
                                found = True
                                element_name = data.get("element", target)
                    except Exception as e_vlm:
                        logger.error(f"[VisionAgent] VLM coordinate query failed: {e_vlm}")
                        
                if found and coords:
                    x, y = coords
                    TASKBAR_EXCLUSION_PX = 60
                    if not (0 <= x <= screen_w and 0 <= y <= screen_h - TASKBAR_EXCLUSION_PX):
                        logger.warning(f"[VisionAgent] Click coordinate ({x}, {y}) rejected because it falls in protected taskbar or off-screen.")
                        return self._fail(dispatch, "Click target is in a protected system area or outside screen bounds.")
                    
                    await asyncio.to_thread(pyautogui.click, x, y)
                    await asyncio.sleep(0.3)
                    return self._ok(dispatch, {"response": f"Clicked the {element_name} at ({x}, {y}), sir.", "x": x, "y": y})
                else:
                    return self._fail(dispatch, f"I could not locate the element '{target}' on the screen, sir.")

            else:
                return self._fail(dispatch, f"Unknown vision intent: {intent}")

        except Exception as e:
            logger.error(f"[VisionAgent] Failed to handle task {intent}: {e}")
            return self._fail(dispatch, str(e))
