#!/usr/bin/env python3

# libbcg729 Python bindings

# G.729 Annex A
# - uses sampling frequenzy 8kHz/16-bit PCM
# - fixed bitrate 8 kbit/s 10 ms frames
# - fixed frame size 10 bytes for 10 ms frame

import ctypes  # type: ignore

from ctypes.util import find_library  # type: ignore

lib_location = find_library('bcg729')

if lib_location is None:
    raise Exception('Could not find G729 library. Make sure it is installed.')

libg729 = ctypes.CDLL(lib_location)


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


class G729Decoder(ctypes.Structure):
    """G729 decoder state.
    This contains the complete state of an G729 decoder.
    """
    pass
DecoderPointer = ctypes.POINTER(G729Decoder)

libg729_decoder_create = libg729.initBcg729DecoderChannel
libg729_decoder_create.restype = DecoderPointer
libg729_decoder_close = libg729.closeBcg729DecoderChannel
libg729_decoder_close.argtypes = (
    DecoderPointer,
)
libg729_decoder_decode = libg729.bcg729Decoder
libg729_decoder_decode.argtypes = (
    DecoderPointer,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_ubyte,
    ctypes.c_ubyte,
    ctypes.c_ubyte,
    ctypes.c_ubyte,
    ctypes.POINTER(ctypes.c_int16),
)


class G729Encoder(ctypes.Structure):
    """G729 encoder state.
    This contains the complete state of an G729 encoder.
    """
    pass
EncoderPointer = ctypes.POINTER(G729Encoder)

libg729_encoder_create = libg729.initBcg729EncoderChannel
libg729_encoder_create.argtypes = (ctypes.c_ubyte,)
libg729_encoder_create.restype = EncoderPointer
libg729_encoder_close = libg729.closeBcg729EncoderChannel
libg729_encoder_close.argtypes = (
    EncoderPointer,
)
libg729_encoder_encode = libg729.bcg729Encoder
libg729_encoder_encode.argtypes = (
    EncoderPointer,
    ctypes.POINTER(ctypes.c_int16),
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.POINTER(ctypes.c_ubyte),
)


class Decoder():
    def __init__(self):
        self.decoder = libg729_decoder_create()
        self.erasure_flag = ctypes.c_ubyte()
        self.sid_flag = ctypes.c_ubyte()
        self.rfc3389_flag = ctypes.c_ubyte()

    def decode(self, g729data):
        decoded = b''
        for chunk in chunks(g729data, 10):
            decoded += self._decode(chunk)
        return decoded

    def _decode(self, g729data):
        frame_size = len(g729data)
        bitstream = (ctypes.c_ubyte * frame_size)(*g729data)

        pcm_size = frame_size * 8
        pcm_arr = (ctypes.c_int16 * pcm_size)()

        libg729_decoder_decode(
            self.decoder, bitstream, frame_size,
            self.erasure_flag, self.sid_flag, self.rfc3389_flag,
            pcm_arr
        )

        return bytes(pcm_arr)


class Encoder():
    # huge thanks to @jzmp for fixing the encoder function call!

    def __init__(self, vad_enabled=0):
        self.encoder = libg729_encoder_create(vad_enabled)
        self.bitStreamLength = ctypes.c_ubyte()
        self.bitStreamLength_pointer = ctypes.byref(self.bitStreamLength)

    def encode(self, pcmdata):
        encoded = b''
        for chunk in chunks(pcmdata, 160):
            int16_arr = []
            for int_bytes in chunks(chunk, 2):
                int16_arr.append(int.from_bytes(int_bytes, byteorder='little'))
            encoded += self._encode(int16_arr)
        return encoded

    def _encode(self, pcmdata):
        # G729 encoder takes 80 samples (int16 -> 160 bytes) and returns 10 byte g729 or less (if VAD enabled)
        # do not feed the encoder with more data directly!
        frame_size = len(pcmdata)
        frame = (ctypes.c_int16 * frame_size)(*pcmdata)
        bitstream = (ctypes.c_ubyte * 10)()

        libg729_encoder_encode(
            self.encoder, frame, bitstream, self.bitStreamLength_pointer
        )

        return bytes(bitstream[:int.from_bytes(self.bitStreamLength, 'big')])
