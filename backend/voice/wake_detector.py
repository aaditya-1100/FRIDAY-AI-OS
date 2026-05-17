import re


WAKE_WORDS = [

    "friday",

    "hey friday",

    "hello friday",

    "wake up friday"
]


def clean_text(text: str):

    text = text.lower()

    text = re.sub(

        r"[^\w\s]",

        "",

        text
    )

    return text.strip()


def detect_wake_word(query):

    query = clean_text(query)

    return any(

        wake in query

        for wake in WAKE_WORDS
    )


def remove_wake_word(query):

    query = clean_text(query)

    for wake in WAKE_WORDS:

        query = query.replace(
            wake,
            ""
        )

    return query.strip()