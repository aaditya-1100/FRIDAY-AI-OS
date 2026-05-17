import asyncio
import queue
import re

import numpy as np
import sounddevice as sd

from faster_whisper import WhisperModel


# =========================================
# LIGHTWEIGHT WHISPER MODEL
# =========================================

model = WhisperModel(

    "tiny.en",

    compute_type="int8"
)


# =========================================
# AUDIO CONFIG
# =========================================

SAMPLE_RATE = 16000

CHANNELS = 1

BLOCKSIZE = 8000

audio_queue = queue.Queue()


# =========================================
# CLEAN TEXT
# =========================================

def clean_text(text):

    text = text.lower()

    text = re.sub(

        r"[^\w\s]",

        "",

        text
    )

    return text.strip()


# =========================================
# AUDIO CALLBACK
# =========================================

def audio_callback(

    indata,

    frames,

    time,

    status
):

    if status:
        return

    audio_queue.put(
        indata.copy()
    )


# =========================================
# LISTEN
# =========================================

async def listen():

    print("[LISTENING...]")

    recording = []

    silence_counter = 0

    with sd.InputStream(

        samplerate=SAMPLE_RATE,

        channels=CHANNELS,

        blocksize=BLOCKSIZE,

        callback=audio_callback

    ):

        while True:

            data = audio_queue.get()

            audio_chunk = np.squeeze(data)

            volume = np.linalg.norm(
                audio_chunk
            )

            # =================================
            # SPEECH DETECTION
            # =================================

            if volume > 3:

                silence_counter = 0

                recording.extend(
                    audio_chunk
                )

            else:

                silence_counter += 1

                if silence_counter > 6:

                    break

    # =====================================
    # SHORT AUDIO IGNORE
    # =====================================

    if len(recording) < 4000:

        return None

    audio_array = np.array(

        recording,

        dtype=np.float32
    )

    # NORMALIZE AUDIO

    audio_array = audio_array / np.max(
        np.abs(audio_array)
    )

    # =====================================
    # TRANSCRIBE
    # =====================================

    segments, info = model.transcribe(

        audio_array,

        beam_size=1,

        language="en"
    )

    text = ""

    for segment in segments:

        text += segment.text

    text = clean_text(text)

    if text:

        print(f"Sir: {text}")

    return text