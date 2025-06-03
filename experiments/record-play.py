import pickle
import pyaudio
import os

audio = pyaudio.PyAudio()
audioStream = audio.open(
            format=pyaudio.paInt16, # conform with alaw2lin second parameter (2 bytes -> 16 bit)
            channels=1,
            rate=48000,
            frames_per_buffer=1024,
            output=True,
            output_device_index=None
)

with open(os.path.dirname(os.path.realpath(__file__))+'/record', 'rb') as f:

    buf = pickle.load(f)
    for audioData in buf:
        audioStream.write(audioData)
    audioStream.stop_stream()
    audioStream.close()
