#!/usr/bin/python3

import socket
import pyaudio
import wave
import threading
import struct
import time
import os, sys

# codec imports
import audioop


class InputAudioSocket(threading.Thread):
    CHUNK = 1024

    sock = None
    audioStream = None

    stopFlag = False

    def __init__(self, interface, audio, *args, **kwargs):
        # open RTP UDP socket for incoming audio data
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((interface, 0))
        # open sound card
        self.audioStream = audio.open(
            format=pyaudio.paInt16, # conform with alaw2lin second parameter (2 bytes -> 16 bit)
            channels=1,
            rate=8000, # a-law always uses 8khz
            frames_per_buffer=self.CHUNK,
            output=True)
        # call Thread constructor
        super(InputAudioSocket, self).__init__(*args, **kwargs)
        self.daemon = True

    def run(self, *args, **kwargs):
        print(f':: opened UDP socket on port {self.sock.getsockname()[1]} for incoming RTP stream')

        payloadType = -1
        counter = 0
        while True:
            if(self.stopFlag): break
            datagram, address = self.sock.recvfrom(1024)

            if(len(datagram) < 12): continue # ignore invalid RTP packets
            if(len(datagram) == 20): continue # ignore STUN binding request

            if(payloadType == -1):
                rtpHead = datagram[:12]
                payloadType = rtpHead[1] & 0b01111111

            rtpBody = datagram[12:]
            if(payloadType == 0):
                self.audioStream.write(audioop.ulaw2lin(rtpBody, 2))
            elif(payloadType == 8):
                self.audioStream.write(audioop.alaw2lin(rtpBody, 2))
            else:
                raise Exception(f'Unsupported codec / payload type {payloadType}')
                # todo: support dynamic payloadTypes negotiated in SDP packets

        self.sock.close()
        self.audioStream.stop_stream()
        self.audioStream.close()
        print(f':: closed UDP socket for incoming RTP stream')

    def stop(self):
        self.stopFlag = True

class OutputAudioSocket(threading.Thread):
    CHUNK = 160

    dstAddress = None
    dstPort = None
    dstPortCtrl = None
    sock = None
    audioStream = None
    ssrc = bytes([0xce, 0x4d, 0x91, 0x2f]) #os.urandom(4)

    stopFlag = False

    def __init__(self, sock, dstAddress, dstPort, audio, *args, **kwargs):
        # prepare UDP socket for outgoing audio data
        self.dstAddress = dstAddress
        self.dstPort = dstPort
        self.dstPortCtrl = dstPort + 1
        # setup RTP socket
        self.sock = sock
        # setup RTCP socket
        #self.sockCtrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        #self.sockCtrl.bind(('0.0.0.0', self.sock.getsockname()[1] + 1))
        time.sleep(0.1)
        # open sound card
        self.audioStream = audio.open(
            format=pyaudio.paInt16, # conform with lin2alaw second parameter (2 bytes -> 16 bit)
            channels=1,
            rate=8000, # a-law always uses 8khz
            frames_per_buffer=self.CHUNK,
            input=True)
        # call Thread constructor
        super(OutputAudioSocket, self).__init__(*args, **kwargs)
        self.daemon = True

    def run(self, *args, **kwargs):
        print(f':: starting outgoing UDP RTP stream to {self.dstAddress}:{self.dstPort}')

        # STUN binding indication
        self.sock.sendto(bytes([
            0x00, 0x11, # binding indication
            0x00, 0x00, # message length
            0x21, 0x12, 0xa4, 0x42, # message cookie
            0x4b, 0x65, 0x65, 0x70, 0x61, 0x20, 0x52, 0x54, 0x50, 0x00, 0x00, 0x00 # transaction ID
        ]), (self.dstAddress, self.dstPort))
        #self.sockCtrl.sendto(bytes([
        #    0x00, 0x11, # binding indication
        #    0x00, 0x00, # message length
        #    0x21, 0x12, 0xa4, 0x42, # message cookie
        #    0x4b, 0x65, 0x65, 0x70, 0x61, 0x20, 0x52, 0x54, 0x50, 0x00, 0x00, 0x00 # transaction ID
        #]), (self.dstAddress, self.dstPortCtrl))

        timestamp = self.CHUNK
        sequenceNumber = 1
        marker = 0x80
        while True:
            if(self.stopFlag): break
            sequenceNumberBytes = struct.pack('>H', sequenceNumber)
            timestampBytes = struct.pack('>I', timestamp)
            rtpHead = bytes([
                0x80, # RTP version = 2; no padding; no extension
                0x08 + marker, # payload type 8 = PCMA (a-law); marker bit
                sequenceNumberBytes[0], sequenceNumberBytes[1],
                timestampBytes[0], timestampBytes[1], timestampBytes[2], timestampBytes[3],
                self.ssrc[0], self.ssrc[1], self.ssrc[2], self.ssrc[3],
            ])
            rtpBody = audioop.lin2alaw(self.audioStream.read(self.CHUNK), 2)
            self.sock.sendto(rtpHead+rtpBody, (self.dstAddress, self.dstPort))

            marker = 0
            timestamp += self.CHUNK
            sequenceNumber += 1
            if(sequenceNumber > 65536): sequenceNumber = 0

        self.sock.close()
        self.audioStream.stop_stream()
        self.audioStream.close()
        print(f':: stopped outgoing UDP RTP stream')

    def stop(self):
        self.stopFlag = True

class AudioPlayer(threading.Thread):
    CHUNK = 1024

    stopFlag = False

    def __init__(self, waveFile, audio, *args, **kwargs):
        # open wave file
        self.wf = wave.open(waveFile, 'rb')
        # open sound card
        self.audioStream = audio.open(
            format=audio.get_format_from_width(self.wf.getsampwidth()),
            channels=self.wf.getnchannels(),
            rate=self.wf.getframerate(),
            frames_per_buffer=self.CHUNK,
            output=True)
        # call Thread constructor
        super(AudioPlayer, self).__init__(*args, **kwargs)
        self.daemon = True

    def run(self, *args, **kwargs):
        data = self.wf.readframes(self.CHUNK)
        while data != b'':
            if(self.stopFlag): break
            self.audioStream.write(data)
            data = self.wf.readframes(self.CHUNK)
        self.audioStream.close()

    def stop(self):
        self.stopFlag = True
