import pyaudio
import audioop
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

pa = pyaudio.PyAudio()
count = pa.get_device_count()

print("==============================================================")
print("             FRIDAY STEADY-STATE MIC SIGNAL SCAN")
print("==============================================================\n")

for i in range(count):
    try:
        info = pa.get_device_info_by_index(i)
        ch = info.get('maxInputChannels', 0)
        name = info.get('name', 'unknown')
        if ch > 0:
            # Try to open stream
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    input_device_index=i,
                    frames_per_buffer=256
                )
                
                # Read 15 chunks
                rms_list = []
                for chunk_idx in range(15):
                    data = stream.read(256, exception_on_overflow=False)
                    rms = audioop.rms(data, 2)
                    rms_list.append(rms)
                stream.close()
                
                # Calculate steady-state RMS (last 5 chunks, ignoring pop)
                steady_rms = sum(rms_list[10:15]) / 5
                initial_rms = sum(rms_list[0:3]) / 3
                pop_rms = max(rms_list[3:10])
                
                status = "ACTIVE/WORKING" if steady_rms > 15.0 else "SILENT/EMPTY"
                print(f"Device [{i:02d}] '{name}':")
                print(f"  Startup (Chunks 0-2):  RMS={initial_rms:.1f}")
                print(f"  Transient Pop (3-9):   Peak RMS={pop_rms:.1f}")
                print(f"  Steady-State (10-14):  RMS={steady_rms:.1f} -> {status}\n")
                
            except Exception as e:
                print(f"Device [{i:02d}] '{name}': Failed to open stream: {e}\n")
    except Exception as e:
        print(f"Device [{i:02d}] Error: {e}\n")

pa.terminate()
