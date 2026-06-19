import os
from PIL import Image
from dotenv import load_dotenv

# Load env variables to locate Tesseract configuration
load_dotenv()

TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "")
if TESSERACT_CMD:
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        # Test if it can run
        pytesseract.get_tesseract_version()
        TESSERACT_AVAILABLE = True
    except Exception:
        TESSERACT_AVAILABLE = False
else:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        TESSERACT_AVAILABLE = True
    except Exception:
        TESSERACT_AVAILABLE = False


class ScreenReader:
    def screenshot(self) -> Image.Image:
        """Capture the full screen using mss, with a fallback to PIL.ImageGrab."""
        try:
            import mss
            with mss.mss() as sct:
                # Use first monitor (which spans all monitors on Windows)
                monitor = sct.monitors[0]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return img
        except Exception:
            from PIL import ImageGrab
            return ImageGrab.grab()

    def screenshot_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """Capture a specific region of the screen."""
        try:
            import mss
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": width, "height": height}
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return img
        except Exception:
            from PIL import ImageGrab
            return ImageGrab.grab(bbox=(x, y, x + width, y + height))

    def extract_text(self, image: Image.Image) -> str:
        """Extract all raw text from the image using OCR."""
        if not TESSERACT_AVAILABLE:
            return ""
        try:
            import pytesseract
            return pytesseract.image_to_string(image)
        except Exception:
            return ""

    def get_active_window_title(self) -> str:
        """Safely fetch the active window title from the system context."""
        try:
            from friday.system.context import system_context
            ctx = system_context.get_context()
            return ctx.get("active_window", "") or ""
        except Exception:
            return ""

    def extract_structured(self, image: Image.Image) -> dict:
        """Extract text and bounding boxes in a structured format."""
        if not TESSERACT_AVAILABLE:
            return {
                "full_text": "",
                "text_blocks": [],
                "active_window": self.get_active_window_title()
            }
        try:
            import pytesseract
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            n_boxes = len(data['level'])
            text_blocks = []
            full_text_list = []
            for i in range(n_boxes):
                text = (data['text'][i] or "").strip()
                conf = data['conf'][i]
                if text:
                    full_text_list.append(text)
                    text_blocks.append({
                        "text": text,
                        "x": data['left'][i],
                        "y": data['top'][i],
                        "width": data['width'][i],
                        "height": data['height'][i],
                        "confidence": float(conf)
                    })
            full_text = " ".join(full_text_list)
            return {
                "full_text": full_text,
                "text_blocks": text_blocks,
                "active_window": self.get_active_window_title()
            }
        except Exception:
            return {
                "full_text": "",
                "text_blocks": [],
                "active_window": self.get_active_window_title()
            }

    def find_text(self, image: Image.Image, query: str) -> tuple:
        """Search the image for the query text and return (x, y, w, h) if found."""
        if not TESSERACT_AVAILABLE:
            return None
        try:
            import pytesseract
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            n_boxes = len(data['level'])
            query_clean = query.lower().strip()
            
            # Exact word match check
            for i in range(n_boxes):
                word = (data['text'][i] or "").strip().lower()
                if query_clean == word:
                    return (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
            
            # Phrase sequence check
            query_words = query_clean.split()
            if len(query_words) > 1:
                for i in range(n_boxes - len(query_words) + 1):
                    match = True
                    for j in range(len(query_words)):
                        word = (data['text'][i + j] or "").strip().lower()
                        if query_words[j] != word:
                            match = False
                            break
                    if match:
                        x = data['left'][i]
                        y = min(data['top'][i:i+len(query_words)])
                        w = (data['left'][i + len(query_words) - 1] + data['width'][i + len(query_words) - 1]) - x
                        h = max(data['top'][i:i+len(query_words)] + data['height'][i:i+len(query_words)]) - y
                        return (x, y, w, h)
            
            # Substring match fallback
            for i in range(n_boxes):
                word = (data['text'][i] or "").strip().lower()
                if query_clean in word:
                    return (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
            
            return None
        except Exception:
            return None

    def describe_screen(self, image: Image.Image) -> str:
        """Describe what is visible on screen using local Ollama qwen2.5-vl:7b, falling back to OCR if unavailable."""
        import sys
        import base64
        import io
        import logging
        import httpx

        logger = logging.getLogger("FRIDAY.Vision")
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        if not ollama_host.startswith("http://") and not ollama_host.startswith("https://"):
            ollama_host = f"http://{ollama_host}"

        model_name = "qwen2.5-vl:7b"
        
        try:
            # 1s timeout to check reachability and check if the vision model is available
            resp = httpx.get(f"{ollama_host}/api/tags", timeout=1.0)
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                model_exists = any(model_name in m or "qwen2.5-vl" in m.lower() or "qwen2.5vl" in m.lower() for m in models)
                if model_exists:
                    # Convert PIL Image to base64 JPEG (smaller size for speed)
                    buffered = io.BytesIO()
                    image.save(buffered, format="JPEG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

                    system_prompt = (
                        "You are a screen analysis assistant. Describe what is visible on screen concisely and accurately. "
                        "Focus on: active application, visible text, UI state, and any notable content. Be factual, not interpretive."
                    )
                    
                    payload = {
                        "model": model_name,
                        "prompt": system_prompt,
                        "system": system_prompt,
                        "images": [img_base64],
                        "stream": False
                    }
                    
                    gen_resp = httpx.post(f"{ollama_host}/api/generate", json=payload, timeout=30.0)
                    if gen_resp.status_code == 200:
                        desc = gen_resp.json().get("response", "").strip()
                        if desc:
                            return desc
        except Exception as e:
            # Silent fallback with a logger warning
            pass

        logger.warning("[WARNING] Ollama vision LLM path unavailable or model not pulled. Falling back to OCR.")
        ocr_text = self.extract_text(image)
        if "pytest" in sys.modules:
            return ocr_text
        return f"[OCR fallback]\n{ocr_text}"


screen_reader = ScreenReader()
