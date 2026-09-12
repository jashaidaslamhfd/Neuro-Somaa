import os
import wave

import numpy as np

SR = 44100
OUT_DIR = "assets/music"


def generate_jump_scare_stinger(name, freq_start=150, freq_end=60, duration=0.8, volume=0.6):
    """Generates a sharp, dissonant mystery stinger for retention spikes."""
    n = int(SR * duration)
    t = np.arange(n) / SR

    # 1. Pitch Slide (Downward for dread)
    freq = np.linspace(freq_start, freq_end, n)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sig = np.sin(phase)

    # 2. Add Dissonance (The 'Scary' part)
    sig += 0.5 * np.sin(phase * 1.51)  # Discordant interval
    sig += 0.3 * np.sin(phase * 2.05)

    # 3. Aggressive Attack Envelope
    env = np.exp(-t * 5.0)  # Sharp start, quick decay
    sig *= env

    # 4. Distortion (Crunchy feel)
    sig = np.tanh(sig * 2.0)

    # Master
    sig = (sig * volume * 32767).astype(np.int16)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(sig.tobytes())
    print(f"Generated: {path}")


if __name__ == "__main__":
    generate_jump_scare_stinger("mystery_stinger.wav")
