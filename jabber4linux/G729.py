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


class Decoder(ctypes.Structure):
    """G729 decoder state.
    This contains the complete state of an G729 decoder.
    """
    pass
DecoderPointer = ctypes.POINTER(Decoder)

libg729_decoder_create = libg729.initBcg729DecoderChannel
libg729_decoder_create.restype = DecoderPointer
libg729_decoder_close = libg729.closeBcg729DecoderChannel
libg729_decoder_close.argtypes = (
    DecoderPointer,
)
libg729_decoder_decode = libg729.bcg729Decoder
"""libg729_decode.argtypes = (
    DecoderPointer,
    ctypes.c_ubyte, # how to correctly define an ubyte array here?
    ctypes.c_ubyte,
    ctypes.c_ubyte,
    ctypes.c_ubyte,
    ctypes.c_ubyte,
    ctypes.c_int16
)"""


class Encoder(ctypes.Structure):
    """G729 encoder state.
    This contains the complete state of an G729 encoder.
    """
    pass
EncoderPointer = ctypes.POINTER(Encoder)

libg729_encoder_create = libg729.initBcg729EncoderChannel
libg729_encoder_create.argtypes = (ctypes.c_ubyte,)
libg729_encoder_create.restype = EncoderPointer
libg729_encoder_close = libg729.closeBcg729EncoderChannel
libg729_encoder_close.argtypes = (
    EncoderPointer,
)
libg729_encoder_encode = libg729.bcg729Encoder
"""libg729_encoder_encode.argtypes = (
    EncoderPointer,
    ctypes.c_int16,
    ctypes.c_ubyte, # how to correctly define an ubyte array here?
    ctypes.POINTER(ctypes.c_ubyte)
)"""


class G729Decoder():
    def __init__(self, vad_enabled=0):
        self.decoder = libg729_decoder_create()
        self.erasure_flag = ctypes.c_ubyte()
        self.sid_flag = ctypes.c_ubyte()
        self.rfc3389_flag = ctypes.c_ubyte()

    def decode(self, g729data):
        frame_size = len(g729data)
        bitstream = (ctypes.c_ubyte * frame_size)(*g729data)

        pcm_size = frame_size * 8
        pcm_arr = (ctypes.c_int16 * pcm_size)()

        libg729_decoder_decode(
            self.decoder, bitstream, frame_size,
            self.erasure_flag, self.sid_flag, self.rfc3389_flag,
            pcm_arr
        )

        return pcm_arr


class G729Encoder():
    def __init__(self, vad_enabled=0):
        self.encoder = libg729_encoder_create(vad_enabled)

    def encode(self, pcmdata):
        frame_size = len(pcmdata)
        frame = (ctypes.c_int16 * frame_size)(*pcmdata)
        bitstream = (ctypes.c_ubyte * 10)() # TODO: calc correct output array size

        bitStreamLength = 0
        bitStreamLengthPointer = ctypes.cast(bitStreamLength, ctypes.POINTER(ctypes.c_ubyte))

        libg729_encoder_encode(
            self.encoder, frame, bitstream, bitStreamLengthPointer
        ) # TODO: boom, Segfault!

        return bitstream
