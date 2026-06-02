import pyaudio
import audioop
import time

pa = pyaudio.PyAudio()

for idx in [1, 8]:
    try:
        print(f"\n--- Testing Device [{idx}] ---")
        info = pa.get_device_info_by_index(idx)
        print(f"Name: {info['name']}")
        
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=idx,
            frames_per_buffer=512
        )
        
        print("Reading 20 chunks of 256 frames:")
        for i in range(20):
            data = stream.read(256, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            print(f"  Chunk {i:02d}: RMS={rms:.2f}")
            
        stream.close()
    except Exception as e:
        print(f"Failed to test device [{idx}]: {e}")

pa.terminate()
