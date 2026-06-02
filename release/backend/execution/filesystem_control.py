import os

from pathlib import Path

# =========================================
# COMMON SEARCH ROOTS
# =========================================

SEARCH_ROOTS = [

    str(Path.home()),

    "C:\\"
]

# =========================================
# OPEN PATH
# =========================================

def open_path(path):

    try:

        if os.path.exists(path):

            os.startfile(path)

            return True

    except:

        pass

    return False

# =========================================
# FIND FILE OR FOLDER
# =========================================

def find_path(name):

    name = name.lower().strip()

    for root_dir in SEARCH_ROOTS:

        for root, dirs, files in os.walk(root_dir):

            # =========================================
            # FOLDER MATCH
            # =========================================

            for d in dirs:

                if name in d.lower():

                    return os.path.join(root, d)

            # =========================================
            # FILE MATCH
            # =========================================

            for f in files:

                if name in f.lower():

                    return os.path.join(root, f)

    return None

# =========================================
# OPEN ANYWHERE
# =========================================

def open_anywhere(name):

    path = find_path(name)

    if not path:

        return False

    return open_path(path)

# =========================================
# CREATE FOLDER
# =========================================

def create_folder(path):

    try:

        os.makedirs(

            path,

            exist_ok=True
        )

        return True

    except:

        return False

# =========================================
# CREATE FILE
# =========================================

def create_file(path):

    try:

        with open(path, "w"):

            pass

        return True

    except:

        return False