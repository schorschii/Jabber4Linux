
from jabber4linux.G729 import G729Encoder, G729Decoder


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# -- record a sample from microphone
"""import pyaudio, audioop
audio = pyaudio.PyAudio()
audioStream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=48000,
            frames_per_buffer=10240,
            input=True)
print('recording...')
audioData = audioStream.read(10240)
audioData, state = audioop.ratecv(audioData, 2, 1, 48000, 8000, None)
print('recording finished ===')"""


# -- decode test file
print('Decoding...')
dec = G729Decoder()
o = open('testpayload.raw', 'wb')
i = open('testpayload.g729', 'rb')
audioData = i.read()

# captured RTP packets from Cisco jabber contain 20 bytes G729; however 10 bytes are recommended in G729 Annex A
count = 0
testPCM = b""
for chunk in chunks(audioData, 10):
    pcmdata = dec.decode(chunk)
    o.write(pcmdata)

    # take the first PCM chunk for testing encoding later
    if(count == 1): testPCM = pcmdata
    count += 1

# created testpayload.raw can be opened in Audacity: File -> Import -> Raw: choose 16bit PCM, 8kHz, 1 channel
o.close()


# -- encode test
print('Encoding...', len(testPCM))
enc = G729Encoder()
bitstream = enc.encode(testPCM)
print(bitstream)
