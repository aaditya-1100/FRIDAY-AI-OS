import pyaudio
import sys

pa = pyaudio.PyAudio()
idx = 20

print(f"Device 20 Info:")
try:
    info = pa.get_device_info_by_index(idx)
    for k, v in info.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"Error getting info: {e}")
    sys.exit(1)

print("\nAttempting to open stream at various settings:")
for rate in [16000, 44100, 48000]:
    for channels in [1, 2]:
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=idx,
                frames_per_buffer=512
            )
            print(f"  SUCCESS! rate={rate}, channels={channels}")
            stream.close()
        except Exception as e:
            print(f"  FAILED rate={rate}, channels={channels}: {e}")

pa.terminate()
