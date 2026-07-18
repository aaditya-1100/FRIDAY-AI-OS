class ShortTermMemory:

    def __init__(self):

        self.history = []

    def add(self, role, content):

        self.history.append({

            "role": role,

            "content": content
        })

        if len(self.history) > 12:

            self.history = self.history[-12:]

    def get(self):

        return self.history

    def clear(self):

        self.history = []
