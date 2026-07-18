import pyaudio
import audioop
import time

pa = pyaudio.PyAudio()
idx = 1

try:
    print(f"--- Continuous Test of Device [{idx}] ---")
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        input_device_index=idx,
        frames_per_buffer=1024
    )
    
    # Read for 3 seconds (approx 46 chunks of 1024 frames at 16kHz)
    for i in range(46):
        data = stream.read(1024, exception_on_overflow=False)
        rms = audioop.rms(data, 2)
        print(f"Chunk {i:02d}: RMS={rms:.2f}")
        
    stream.close()
except Exception as e:
    print(f"Failed: {e}")

pa.terminate()
