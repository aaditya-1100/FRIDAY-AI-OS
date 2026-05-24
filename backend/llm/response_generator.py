from llm.groq_client import ask_groq


# =========================================
# GENERATE RESPONSE
# =========================================

def generate_response(

    memory,

    query
):

    try:

        if not isinstance(query, str):

            return (
                "I did not understand sir"
            )

        query = query.strip()

        if len(query) == 0:

            return (
                "I did not understand sir"
            )

        history_list = None
        if memory:
            history_list = memory.get()

        return ask_groq(query, history=history_list)

    except Exception as e:

        print(
            f"[RESPONSE ERROR] {e}"
        )

        return (
            "Something went wrong sir"
        )