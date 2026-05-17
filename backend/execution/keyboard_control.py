import pyautogui

# =========================================
# PRESS KEY
# =========================================

def press_key(key):

    try:

        pyautogui.press(key)

        return True

    except:

        return False

# =========================================
# HOTKEY
# =========================================

def hotkey(*keys):

    try:

        pyautogui.hotkey(*keys)

        return True

    except:

        return False

# =========================================
# TYPE TEXT
# =========================================

def type_text(text):

    try:

        pyautogui.write(

            text,

            interval=0.03
        )

        return True

    except:

        return False