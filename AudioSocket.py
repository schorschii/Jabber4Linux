#!/usr/bin/env python3

import socket
import pyaudio
import wave
import threading
import struct
import time
import re
import os, sys

# codec imports
import audioop
import opuslib


class InputAudioSocket(threading.Thread):
    CHUNK = 1024

    def __init__(self, interface, audio, deviceName=None, ptMap={}, *args, **kwargs):
        self.sock = None
        self.audioStream = None
        self.soundcardSampleRate = 8000 # use 8khz as default, so we do not need to convert PCMU and PCMA
        self.sampleRateConverterState = None
        self.outputSocketReference = None
        self.stopFlag = False
        self.applyPtMap(ptMap)

        # open RTP UDP socket for incoming audio data
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((interface, 0))

        # find audio device
        deviceIndex = None # fallback: system default
        info = audio.get_host_api_info_by_index(0)
        for i in range(0, info.get('deviceCount')):
            deviceInfo = audio.get_device_info_by_host_api_device_index(0, i)
            if((deviceInfo.get('maxOutputChannels')) > 0):
                if(deviceName != None and deviceName in deviceInfo.get('name')):
                    deviceIndex = i
                    self.soundcardSampleRate = int(deviceInfo.get('defaultSampleRate')) # use specific soundcard sample rate, otherwise error
        if deviceIndex == None: print(':: using default output device ', deviceName)
        # open sound card
        self.audioStream = audio.open(
            format=pyaudio.paInt16, # conform with alaw2lin second parameter (2 bytes -> 16 bit)
            channels=1,
            rate=self.soundcardSampleRate,
            frames_per_buffer=self.CHUNK,
            output=True,
            output_device_index=deviceIndex)

        # call Thread constructor
        super(InputAudioSocket, self).__init__(*args, **kwargs)
        self.daemon = True

    def applyPtMap(self, ptMap):
        # init opuslib if given in payload type map
        self.opusPayloadType = -1
        for payloadTypeNumber, payloadTypeDescription in ptMap.items():
            splitter = payloadTypeDescription.lower().split('/')
            if(len(splitter) < 2): continue
            if(splitter[0] == 'opus' and int(splitter[1]) >= 8000):
                self.opusPayloadType = payloadTypeNumber
                self.opusSampleRate = int(splitter[1])
                self.opusDecoder = opuslib.Decoder(int(splitter[1]), 1)

    def run(self, *args, **kwargs):
        print(f':: opened UDP socket on port {self.sock.getsockname()[1]} for incoming RTP stream')

        try:
            payloadType = -1
            counter = 0
            while True:
                # read from RTP socket
                if(self.stopFlag): break
                datagram, address = self.sock.recvfrom(1024)

                if(len(datagram) < 12): continue # ignore invalid RTP packets
                if(len(datagram) == 20): continue # ignore STUN binding request

                rtpHead = datagram[:12]
                if(payloadType == -1):
                    payloadType = rtpHead[1] & 0b01111111

                # store information for outgoing sender report RTCP packets
                if(self.outputSocketReference != None):
                    self.outputSocketReference.remoteSsrc = rtpHead[8:12]
                    self.outputSocketReference.hsnr = rtpHead[2:4]

                # decode payload
                rtpBody = datagram[12:]
                audioData = b''
                payloadSampleRate = 8000 # PCMA and PCMU always uses 8khz
                if(payloadType == 0):
                    audioData = audioop.ulaw2lin(rtpBody, 2)
                elif(payloadType == 8):
                    audioData = audioop.alaw2lin(rtpBody, 2)
                elif(payloadType == self.opusPayloadType):
                    payloadSampleRate = self.opusSampleRate
                    audioData = self.opusDecoder.decode(rtpBody, 960)
                else:
                    print(f'Unsupported codec / payload type {payloadType}')

                # sample rate conversion
                if(self.soundcardSampleRate != payloadSampleRate):
                    audioData, state = audioop.ratecv(audioData, 2, 1, payloadSampleRate, self.soundcardSampleRate, self.sampleRateConverterState)
                    self.sampleRateConverterState = state

                # write to soundcard
                self.audioStream.write(audioData)

        except OSError:
            pass

        self.sock.close()
        self.audioStream.stop_stream()
        self.audioStream.close()
        print(f':: closed UDP socket for incoming RTP stream')

    def stop(self):
        self.stopFlag = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        self.sock.close()
        self.audioStream.stop_stream()
        self.audioStream.close()

class OutputAudioSocket(threading.Thread):
    CHUNK = 160

    def __init__(self, sock, dstAddress, dstPort, payloadType, audio, deviceName=None, ptMap={}, *args, **kwargs):
        self.dstAddress = None
        self.dstPort = None
        self.dstPortCtrl = None
        self.sock = None
        self.audioStream = None
        self.payloadType = payloadType
        self.ssrc = os.urandom(4)
        self.remoteSsrc = bytes([0x00, 0x00, 0x00, 0x00])
        self.hsnr = bytes([0x00, 0x00])
        self.soundcardSampleRate = 8000 # use 8khz as default, so we do not need to convert PCMU and PCMA
        self.sampleRateConverterState = None
        self.stopFlag = False

        # init opuslib if given in payload type map
        self.opusPayloadType = -1
        for payloadTypeNumber, payloadTypeDescription in ptMap.items():
            splitter = payloadTypeDescription.lower().split('/')
            if(len(splitter) < 2): continue
            if(splitter[0] == 'opus' and int(splitter[1]) >= 8000):
                self.opusPayloadType = payloadTypeNumber
                self.opusSampleRate = int(splitter[1])
                self.opusEncoder = opuslib.Encoder(int(splitter[1]), 1, 'voip')

        # prepare UDP socket for outgoing audio data
        self.dstAddress = dstAddress
        self.dstPort = dstPort
        self.dstPortCtrl = dstPort + 1
        # setup RTP socket
        self.sock = sock
        # setup RTCP socket (using RTP port + 1)
        self.sockCtrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockCtrl.bind(('0.0.0.0', self.sock.getsockname()[1] + 1))
        time.sleep(0.1)

        # find audio device
        deviceIndex = None # fallback: system default
        info = audio.get_host_api_info_by_index(0)
        for i in range(0, info.get('deviceCount')):
            deviceInfo = audio.get_device_info_by_host_api_device_index(0, i)
            if((deviceInfo.get('maxInputChannels')) > 0):
                if(deviceName != None and deviceName in deviceInfo.get('name')):
                    deviceIndex = i
                    self.soundcardSampleRate = int(deviceInfo.get('defaultSampleRate')) # use specific soundcard sample rate, otherwise error
        if deviceIndex == None: print(':: using default input device ', deviceName)
        # open sound card
        self.audioStream = audio.open(
            format=pyaudio.paInt16, # conform with lin2alaw second parameter (2 bytes -> 16 bit)
            channels=1,
            rate=self.soundcardSampleRate,
            frames_per_buffer=self.CHUNK,
            input=True,
            input_device_index=deviceIndex)

        # call Thread constructor
        super(OutputAudioSocket, self).__init__(*args, **kwargs)
        self.daemon = True

    def run(self, *args, **kwargs):
        print(f':: starting outgoing UDP RTP stream to {self.dstAddress}:{self.dstPort}')

        # STUN binding indication
        stunInitPacket = bytes([
            0x00, 0x11, # binding indication
            0x00, 0x00, # message length
            0x21, 0x12, 0xa4, 0x42, # message cookie
            0x4b, 0x65, 0x65, 0x70, 0x61, 0x20, 0x52, 0x54, 0x50, 0x00, 0x00, 0x00 # transaction ID
        ])
        self.sock.sendto(stunInitPacket, (self.dstAddress, self.dstPort))
        self.sockCtrl.sendto(stunInitPacket, (self.dstAddress, self.dstPortCtrl))

        try:
            timestamp = self.CHUNK
            sequenceNumber = 1
            marker = 0x80
            while True:
                if(self.stopFlag): break

                # compile RTP head
                sequenceNumberBytes = struct.pack('>H', sequenceNumber)
                timestampBytes = struct.pack('>I', timestamp)
                rtpHead = bytes([
                    0x80, # RTP version = 2; no padding; no extension
                    self.payloadType + marker, # payload type with marker bit
                    sequenceNumberBytes[0], sequenceNumberBytes[1],
                    timestampBytes[0], timestampBytes[1], timestampBytes[2], timestampBytes[3],
                    self.ssrc[0], self.ssrc[1], self.ssrc[2], self.ssrc[3],
                ])

                # read from soundcard
                audioData = self.audioStream.read(self.CHUNK)

                # sample rate conversion
                payloadSampleRate = 8000 # PCMA and PCMU always uses 8khz
                if(self.payloadType == self.opusPayloadType):
                    payloadSampleRate = self.opusSampleRate
                if(self.soundcardSampleRate != payloadSampleRate):
                    audioData, state = audioop.ratecv(audioData, 2, 1, self.soundcardSampleRate, payloadSampleRate, self.sampleRateConverterState)
                    self.sampleRateConverterState = state

                # encode payload
                if(self.payloadType == 0x08):
                    rtpBody = audioop.lin2alaw(audioData, 2)
                elif(self.payloadType == self.opusPayloadType):
                    rtpBody = self.opusEncoder.encode(audioData, 960)
                else: # use PCMU as fallback
                    rtpBody = audioop.lin2ulaw(audioData, 2)

                # write to RTP socket
                self.sock.sendto(rtpHead+rtpBody, (self.dstAddress, self.dstPort))

                marker = 0
                timestamp += self.CHUNK
                sequenceNumber += 1
                if(sequenceNumber > 65536): sequenceNumber = 0

        except OSError:
            pass

        self.sock.close()
        self.sockCtrl.close()
        self.audioStream.stop_stream()
        self.audioStream.close()
        print(f':: stopped outgoing UDP RTP stream')

    def stop(self):
        self.stopFlag = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sockCtrl.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        self.sock.close()
        self.sockCtrl.close()
        self.audioStream.stop_stream()
        self.audioStream.close()


class AudioPlayer(threading.Thread):
    CHUNK = 4098

    def __init__(self, waveFile, audio, deviceNames=[], *args, **kwargs):
        #audio = pyaudio.PyAudio()
        self.audioStreams = []
        self.audioFileSampleRate = 44100
        self.stopFlag = False

        # open wave file
        self.wf = wave.open(waveFile, 'rb')
        self.audioFileSampleRate = self.wf.getframerate()

        # open sound card
        info = audio.get_host_api_info_by_index(0)
        for i in range(0, info.get('deviceCount')):
            deviceInfo = audio.get_device_info_by_host_api_device_index(0, i)
            if((deviceInfo.get('maxOutputChannels')) > 0
            and re.sub('[\(\[].*?[\)\]]', '', deviceInfo.get('name')).strip() in deviceNames):
                self.audioStreams.append({
                    'stream': audio.open(
                        format=audio.get_format_from_width(self.wf.getsampwidth()),
                        channels=self.wf.getnchannels(),
                        rate=int(deviceInfo.get('defaultSampleRate')),
                        frames_per_buffer=self.CHUNK,
                        output=True,
                        output_device_index=i),
                    'rate': int(deviceInfo.get('defaultSampleRate')),
                    'state': None
                })
        if(len(self.audioStreams) == 0): # fallback: system default
            print(':: using default ringtone output device ', deviceNames)
            self.audioStreams.append({
                'stream':audio.open(
                    format=audio.get_format_from_width(self.wf.getsampwidth()),
                    channels=self.wf.getnchannels(),
                    rate=self.audioFileSampleRate,
                    frames_per_buffer=self.CHUNK,
                    output=True),
                'rate': self.audioFileSampleRate,
                'state': None
            })

        # call Thread constructor
        super(AudioPlayer, self).__init__(*args, **kwargs)
        self.daemon = True

    def run(self, *args, **kwargs):
        data = self.wf.readframes(self.CHUNK)
        while data != b'':
            if(self.stopFlag): break
            for s in self.audioStreams:
                audioData = data
                if(self.audioFileSampleRate != s['rate']):
                    audioData, state = audioop.ratecv(audioData, 2, 1, self.audioFileSampleRate, s['rate'], s['state'])
                    s['state'] = state
                s['stream'].write(audioData)
            data = self.wf.readframes(self.CHUNK)
        for s in self.audioStreams:
            s['stream'].close()

    def stop(self):
        self.stopFlag = True
        time.sleep(0.1) # wait one moment to finish playback of current chunk, otherwise InputAudioSocket will throw "device unavailable" when trying to write on the same device
