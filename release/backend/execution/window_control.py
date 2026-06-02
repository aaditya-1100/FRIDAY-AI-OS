import pygetwindow as gw

# =========================================
# GET ACTIVE WINDOW
# =========================================

def get_active_window():

    try:

        window = gw.getActiveWindow()

        if not window:
            return None

        return window.title

    except:

        return None

# =========================================
# MINIMIZE WINDOW
# =========================================

def minimize_active_window():

    try:

        window = gw.getActiveWindow()

        if not window:
            return False

        window.minimize()

        return True

    except:

        return False

# =========================================
# MAXIMIZE WINDOW
# =========================================

def maximize_active_window():

    try:

        window = gw.getActiveWindow()

        if not window:
            return False

        window.maximize()

        return True

    except:

        return False

# =========================================
# CLOSE WINDOW
# =========================================

def close_active_window():

    try:

        window = gw.getActiveWindow()

        if not window:
            return False

        # USER REQUEST SAFETY GUARD: Do not close chrome or antigravity windows during testing
        title_lower = (window.title or "").lower()
        if "chrome" in title_lower or "antigravity" in title_lower or "gemini" in title_lower or "electron" in title_lower:
            print(f"[WINDOW CONTROL SAFETY] Prevented closing window: '{window.title}'")
            return True

        window.close()

        return True

    except:

        return False

# =========================================
# FOCUS WINDOW
# =========================================

def focus_window(title):
    try:
        target = title.lower().strip()
        all_windows = gw.getAllWindows()
        
        matched_window = None
        for w in all_windows:
            if not w.title:
                continue
            w_title = w.title.lower()
            if target in w_title or (target == "vscode" and "code" in w_title) or (target == "chrome" and "google chrome" in w_title):
                matched_window = w
                break
                
        if matched_window:
            if matched_window.isMinimized:
                matched_window.restore()
            matched_window.activate()
            return True
            
        return False
    except Exception as e:
        print(f"[WINDOW CONTROL] focus_window failed: {e}")
        return False

# =========================================
# CLOSE ACTIVE TAB
# =========================================

def close_active_tab():
    try:
        import pyautogui
        pyautogui.hotkey('ctrl', 'w')
        return True
    except Exception as e:
        print(f"[WINDOW CONTROL] close_active_tab failed: {e}")
        return False