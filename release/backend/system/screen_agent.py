import os
import re
import base64
import subprocess
import tempfile
import asyncio
import ctypes
from pathlib import Path
import pyautogui
import psutil

def get_active_window_info() -> dict:
    """
    Retrieves the title and process name of the active foreground window natively.
    Uses standard library ctypes to query Windows APIs with zero library overhead.
    """
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return {"title": "Desktop", "process": "explorer.exe"}
            
        # Get Title
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            
        # Get Process Name
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = ""
        if pid.value:
            try:
                proc = psutil.Process(pid.value)
                process_name = proc.name()
            except Exception:
                pass
                
        return {"title": title, "process": process_name}
    except Exception as e:
        print(f"[SCREEN AGENT] Passive window tracking exception: {e}")
        return {"title": "", "process": ""}

def run_tesseract_ocr(image_path: str) -> str:
    """
    Attempts to run the local tesseract executable on the given image.
    Falls back gracefully if tesseract is not installed or on PATH.
    """
    try:
        result = subprocess.run(
            ["tesseract", image_path, "stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"[SCREEN AGENT OCR WARNING] Tesseract returned non-zero code: {result.stderr}")
            return ""
    except FileNotFoundError:
        # Tesseract is not installed or not in PATH
        print("[SCREEN AGENT OCR WARNING] Tesseract executable not found on system PATH. Skipping OCR fallback.")
        return ""
    except Exception as e:
        print(f"[SCREEN AGENT OCR ERROR] Failed running Tesseract: {e}")
        return ""

class ScreenAgent:
    """
    FRIDAY Screen Understanding & Active Cognition Agent.
    Manages lightweight passive window awareness and on-demand active screen analysis
    using PIL screenshots and local Tesseract OCR.
    """
    def __init__(self):
        pass

    async def capture_and_analyze(self, query: str) -> dict:
        """
        Active analysis mode: Capture screen and extract text via OCR.
        """
        print("[SCREEN AGENT] Active Screen Analysis Triggered...")
        
        # 1. Get active window details
        win_info = get_active_window_info()
        win_title = win_info.get("title", "Unknown Window")
        win_proc = win_info.get("process", "Unknown Process")
        
        from core.pipeline import context_manager
        import time
        
        now = time.time()
        cached_title = getattr(context_manager, "current_screen_title", None)
        cached_proc = getattr(context_manager, "current_screen_process", None)
        cached_b64 = getattr(context_manager, "last_image_b64", None)
        cached_ocr = getattr(context_manager, "current_ocr_text", None)
        cached_time = getattr(context_manager, "last_screen_capture_time", 0.0)
        
        ocr_text = ""
        image_b64 = ""
        loop = asyncio.get_running_loop()
        
        if (cached_title == win_title and 
            cached_proc == win_proc and 
            cached_b64 and 
            (now - cached_time < 60.0)):
            print("[SCREEN AGENT] Reusing cached screen capture and OCR for visual continuity.")
            ocr_text = cached_ocr
            image_b64 = cached_b64
        else:
            # Capture screen using PyAutoGUI
            try:
                screenshot = pyautogui.screenshot()
            except Exception as e:
                print(f"[SCREEN AGENT ERROR] Failed to take screenshot: {e}")
                return {
                    "type": "ai_response",
                    "response": "I'm sorry sir, but I encountered an error while trying to capture your screen."
                }

            print(f"[SCREEN AGENT] Captured screen. Active window: '{win_title}' ({win_proc})")

            # Use ThreadPoolExecutor to perform blocking I/O (file writes, OCR, base64 encoding)
            def save_and_process():
                # Convert RGBA/P formats to standard RGB before saving to JPEG
                img = screenshot
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    img = img.convert("RGB")

                # Adaptive Resizing: Max boundary of 1280px maintaining aspect ratio
                img.thumbnail((1280, 1280))

                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / "screen_capture.jpg"
                    img.save(tmp_path, format="JPEG", quality=70) # High compression, preserves text readability
                    
                    # Run local Tesseract OCR
                    extracted = run_tesseract_ocr(str(tmp_path))
                    
                    # Base64 encode the saved screenshot
                    with open(tmp_path, "rb") as f:
                        b64_str = base64.b64encode(f.read()).decode("utf-8")
                    return extracted, b64_str

            ocr_text, image_b64 = await loop.run_in_executor(None, save_and_process)
            
            # Update cache context
            context_manager.current_screen_title = win_title
            context_manager.current_screen_process = win_proc
            context_manager.current_ocr_text = ocr_text
            context_manager.last_image_b64 = image_b64
            context_manager.last_screen_capture_time = now

        # 4. Synthesize query and system instruction
        workflow_snap = context_manager.current_workflow_snapshot

        system_instruction = f"""\
You are FRIDAY's Screen Understanding System.
Analyze the user's active screen context provided in the screenshot.
The active window is currently "{win_title}" running process "{win_proc}".
"""
        if workflow_snap:
            system_instruction += f"Active workflow session context: \"{workflow_snap}\"\n"
        if ocr_text:
            system_instruction += f"\nHere is the raw extracted text from the screen using OCR:\n[OCR TEXT START]\n{ocr_text}\n[OCR TEXT END]\n"

        system_instruction += "\nProvide a clear explanation of what is on the screen based on the OCR text, matching the user's inquiry."

        # Route to GROQ for screen analysis (OCR text only, no vision)
        from llm.groq_client import ask_groq, REALTIME_MODEL
        print("[SCREEN AGENT] Sending captured screen OCR to GROQ...")
        response = await loop.run_in_executor(
            None,
            lambda: ask_groq(query, system_prompt=system_instruction, model=REALTIME_MODEL)
        )
        
        return {
            "type": "ai_response",
            "response": response
        }
