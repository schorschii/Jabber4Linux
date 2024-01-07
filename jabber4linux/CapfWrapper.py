#!/usr/bin/env python3

# The functionality of this script is triggered from within Jabber4Linux automatically,
# but it is also possible to call it manually (for debugging) using command line parameters:
# ./CapfWrapper.py -s SERVER_ADDRESS -p PHONE_NAME -f MY_KEY_AND_CERT.pem

import socket, ssl, struct
import asn1
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

class CapfWrapper():
    MAGIC_BYTE         = 0x55

    # operation codes
    OPCODE_SERVERHELLO = 0x01
    OPCODE_CLIENTREQ   = 0x02
    OPCODE_SERVEROK    = 0x03
    OPCODE_CLIENTCSR   = 0x04
    OPCODE_SERVERCRT   = 0x09
    OPCODE_CLIENTACK   = 0x0a
    OPCODE_SERVERFIN   = 0x0f

    # return codes
    RECODE_OK            = 0x01 # yay
    RECODE_ALREADYISSUED = 0x07 # certificate was already issued
    RECODE_NOTFOUND      = 0x09 # phone name not found

    def __init__(self, server, port=3804, debug=False):
        self.debug = debug

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(8)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers('DEFAULT')
        #context.maximum_version = ssl.TLSVersion.TLSv1_2
        #context.load_cert_chain(certfile=tlsOptions['client-cert'], keyfile=tlsOptions['client-key'])
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.sock = context.wrap_socket(self.sock, server_hostname=server)
        self.sock.connect((server, port))

        response = self.recv()
        opcode = response[1]
        if(opcode != CapfWrapper.OPCODE_SERVERHELLO):
            raise Exception(f'Unexpected opcode from server: {hex(opcode)}')

        self.sessid = response[2:6]
        if(self.debug): print('CAPF Session ID: '+self.sessid.hex())

    def recv(self):
        buf = self.sock.recv(4096)
        if(self.debug): print('> ', buf.hex())
        #print('>>', buf.decode('utf-8', errors='replace'))

        magic = buf[0]
        if(magic != CapfWrapper.MAGIC_BYTE):
            raise Exception(f'Invalid magic start byte: {hex(magic)}')

        return buf

    def send(self, payload):
        result = self.sock.sendall(payload)
        if(self.debug): print('< ', payload.hex())
        #print('<<', ''.join(c for c in payload.decode('utf-8', errors='replace') if c.isprintable()))
        return result

    def requestCertificate(self, phoneName, keyCertFile):
        # STEP 1: ask if we can get a certificate for this phone
        message = (
            self.field(b'\x07', b'\x02') +
            self.field(b'\x0d', phoneName.encode('ascii') + b'\x00') +
            self.field(b'\x01', b'\x01')
        )
        self.send( self.field(bytearray([CapfWrapper.MAGIC_BYTE, CapfWrapper.OPCODE_CLIENTREQ]) + self.sessid, message) )

        response = self.recv()
        opcode = response[1]
        errcode = self.readFields(response[8:]).get(1)
        if(opcode == CapfWrapper.OPCODE_SERVERFIN and errcode != None):
            errcode = errcode[0]
            if(errcode == CapfWrapper.RECODE_ALREADYISSUED):
                raise Exception(f'Server declined request: a certificate was already issued for this phone')
            elif(errcode == CapfWrapper.RECODE_NOTFOUND):
                raise Exception(f'Server declined request: no phone found with this name')
            else:
                raise Exception(f'Unknown error from server: {hex(opcode)}')
        elif(opcode != CapfWrapper.OPCODE_SERVEROK):
            raise Exception(f'Unexpected opcode from server: {hex(opcode)}')

        # STEP 2: generate a key and throw CSR against the server
        key = rsa.generate_private_key(
            backend=default_backend(),
            public_exponent=65537,
            key_size=2048
        )
        if(self.debug): print(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode('utf-8'))

        message = (
            self.field(b'\x09', self.generateCsr(key))
        )
        self.send( self.field(bytearray([CapfWrapper.MAGIC_BYTE, CapfWrapper.OPCODE_CLIENTCSR]) + self.sessid, message) )

        response = self.recv()
        opcode = response[1]
        if(opcode != CapfWrapper.OPCODE_SERVERCRT):
            raise Exception(f'Unexpected opcode from server: {hex(opcode)}')
        certPackage = self.readFields(response[8:]).get(4) #todo
        certBytes = self.readFields(certPackage).get(1)
        if(not certPackage): raise Exception('Got invalid cert package')
        certBytes = certBytes.lstrip(b'\x00\x01')
        certificate = x509.load_der_x509_certificate(certBytes)
        if(self.debug): print(certificate.public_bytes(encoding=serialization.Encoding.PEM).decode('utf-8'))

        # save key and cert to file
        with open(keyCertFile, 'wb') as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            f.write(certificate.public_bytes(encoding=serialization.Encoding.PEM))

        # STEP 3: acknowledge certificate
        message = (
            self.field(b'\x01', b'\x01')
        )
        self.send( self.field(bytearray([CapfWrapper.MAGIC_BYTE, CapfWrapper.OPCODE_CLIENTACK]) + self.sessid, message) )

        response = self.recv()
        opcode = response[1]
        if(opcode != CapfWrapper.OPCODE_SERVERFIN):
            raise Exception(f'Unexpected opcode from server: {hex(opcode)}')

    def field(self, identifier:bytes, value:bytes):
        return identifier + struct.pack('>H', len(value)) + value

    def readFields(self, data:bytes):
        fields = {}
        while True:
            header = int(data[0])
            length = struct.unpack('>H', data[1:3])[0]
            value = data[3:3+length]
            fields[header] = value
            data = data[3+length:]
            if(len(data) == 0): break
        return fields

    def generateCsr(self, key:rsa.RSAPrivateKey):
        encoder = asn1.Encoder()
        encoder.start()
        encoder.enter(asn1.Numbers.Sequence)
        encoder.write(key.public_key().public_numbers().n, asn1.Numbers.Integer) # the public modulus
        encoder.write(key.public_key().public_numbers().e, asn1.Numbers.Integer) # the public exponent (65537)
        encoder.leave()
        publicKeyBitString = encoder.output()

        encoder = asn1.Encoder()
        encoder.start()
        encoder.enter(asn1.Numbers.Sequence)
        encoder.enter(asn1.Numbers.Sequence)
        encoder.write('1.2.840.113549.1.1.1', asn1.Numbers.ObjectIdentifier) #rsaEncryption
        encoder.write(None, asn1.Numbers.Null) # who knows
        encoder.leave()
        encoder.write(publicKeyBitString, asn1.Numbers.BitString) # our public key
        encoder.leave()
        return encoder.output()

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--server', required=True, help='CAPF server address')
    parser.add_argument('-p', '--phone', required=True, help='phone name to request a certificate for')
    parser.add_argument('-f', '--file', required=True, help='file name for storing generated key and issued certificate')
    args, unknownargs = parser.parse_known_args()

    capf = CapfWrapper(args.server, debug=True)
    capf.requestCertificate(args.phone, args.file)
    print('CapfWrapper finished successfully!')
