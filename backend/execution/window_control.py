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

        window.close()

        return True

    except:

        return False

# =========================================
# FOCUS WINDOW
# =========================================

def focus_window(title):

    try:

        windows = gw.getWindowsWithTitle(title)

        if not windows:
            return False

        windows[0].activate()

        return True

    except:

        return False