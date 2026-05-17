def parse_intent(query: str):

    if not query:
        return None

    query = query.lower().strip()

    # OPEN YOUTUBE

    if "open youtube" in query:

        if "search for" in query:

            search_query = query.replace(
                "open youtube and search for",
                ""
            ).strip()

            return {
                "intent": "youtube_search",
                "query": search_query
            }

        return {
            "intent": "open_youtube"
        }

    # PLAY SONG/VIDEO

    if query.startswith("play"):

        media_query = query.replace(
            "play",
            ""
        ).strip()

        return {
            "intent": "play_media",
            "query": media_query
        }

    # SCREENSHOT

    if "screenshot" in query:

        return {
            "intent": "take_screenshot"
        }

    # OPEN APP

    if query.startswith("open"):

        app_name = query.replace(
            "open",
            ""
        ).strip()

        return {
            "intent": "open_app",
            "app": app_name
        }

    # EXIT / SLEEP

    if (
        "goodbye" in query
        or "sleep" in query
        or "stop listening" in query
    ):

        return {
            "intent": "sleep"
        }

    # FALLBACK

    return {
        "intent": "general",
        "query": query
    }