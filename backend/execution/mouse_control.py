import pyautogui

# =========================================
# MOVE MOUSE
# =========================================

def move_mouse(x, y):

    try:

        pyautogui.moveTo(

            x,

            y,

            duration=0.2
        )

        return True

    except:

        return False

# =========================================
# CLICK
# =========================================

def click():

    try:

        pyautogui.click()

        return True

    except:

        return False

# =========================================
# RIGHT CLICK
# =========================================

def right_click():

    try:

        pyautogui.rightClick()

        return True

    except:

        return False

# =========================================
# SCROLL
# =========================================

def scroll(amount):

    try:

        pyautogui.scroll(amount)

        return True

    except:

        return False