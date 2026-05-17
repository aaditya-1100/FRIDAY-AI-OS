class SemanticMemory:

    def __init__(self):

        self.last_subject = None

        self.last_intent = None

        self.last_action = None

        self.last_platform = None

    def update(

        self,

        subject=None,

        intent=None,

        action=None,

        platform=None
    ):

        if subject:
            self.last_subject = subject

        if intent:
            self.last_intent = intent

        if action:
            self.last_action = action

        if platform:
            self.last_platform = platform
