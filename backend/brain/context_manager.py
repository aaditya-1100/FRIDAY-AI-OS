from brain.entity_tracker import extract_entity

class ContextManager:

    def __init__(self):

        self.current_entity = None

    def update(self, query):

        entity = extract_entity(query)

        if entity:

            self.current_entity = entity

    def resolve_reference(self, query):

        q = query.lower()

        references = [

            "it",
            "that",
            "him",
            "her",
            "latest one"
        ]

        if any(x in q for x in references):

            return self.current_entity

        return None