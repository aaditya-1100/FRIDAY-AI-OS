def extract_entity(query):

    q = query.lower()

    keywords = [

        "india",
        "australia",
        "csk",
        "youtube",
        "spotify",
        "mr beast",
        "karan aujla"
    ]

    for word in keywords:

        if word in q:

            return word

    return None