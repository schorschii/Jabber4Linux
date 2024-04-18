# Cisco Certificate Authority Proxy Function "CAPF" Protocol
This document describes how the proprietary Cisco CAPF protocol works for issuing client certificates for hardware phones and softphones.

Such Locally Significant Certificates ("LSC") are only issued once; every further signing request will be denied by the CUCM server. A CUCM administrator needs to reset your softphone if the certificate got lost.

A new cert will be signed after 2/3 of existing certificate’s validity ([source](https://www.ciscolive.com/c/dam/r/ciscolive/emea/docs/2020/pdf/BRKCOL-3224.pdf)).

## Protocol Flow
You need to contact port 3804 of your CUCM server and establish a TLS tunnel. The following documentation describes the communication inside the TLS tunnel.

A CAPF packet can contain multiple fields. Bytes in curly brackets `{}` represent the field identifier (constant magic byte) and bytes in square brackets `[]` describe the length of a field.

### 1. Server Hello
After establishing the TLS tunnel, the server automatically sends the first packet with the Session ID. You need to send this Session ID in every further response to the server. The Session ID is incremented on every TCP/TLS connection.

Length   | Description     | Content (hex)
---------|-----------------|--------------
1        | CAPF Magic Byte | `55`
1        | Opcode          | `01`
4        | Session ID      | current session ID
2        | Message Length  | `00 04`
4        | Unknown Field   | `{07} [00 01] 03`

### 2. Client Request With Phone Name
The client answers with the name of the phone, for which a certificate should be issued.

Length   | Description     | Content (hex)
---------|-----------------|--------------
1        | CAPF Magic Byte | `55`
1        | Opcode          | `02`
4        | Session ID      | current session ID
2        | Message Length  | e.g. `00 12` (= 18 bytes)
4        | Unknown Field   | `{07} [00 01] 02`
e.g. 10  | Phone Name      | `{0d} [00 07]` + null terminated string e.g. "CSF123": `43 53 46 31 32 33 00`
4        | Status Code     | `{01} [00 01] 01`

### 3. Server Response
The server answers if it is willing to accept a certificate signing request for the given phone.

Length   | Description     | Content (hex)
---------|-----------------|--------------
1        | CAPF Magic Byte | `55`
1        | Opcode          | `03` (continue) or `0f` (declined)
4        | Session ID      | current session ID
2        | Message Length  | `00 05`
5        | Unknown Field   | `{0a} [00 02] 08 00`

### 4. Client CSR
The client sends the Certificate Signing Request.

Length   | Description     | Content (hex)
---------|-----------------|--------------
1        | CAPF Magic Byte | `55`
1        | Opcode          | `04`
4        | Session ID      | current session ID
2        | Message Length  | e.g. `01 29` (= 297 bytes)
e.g. 297 | CSR             | `{09} [01 26]` + your signing request, DER format

The discovered CSR seems a little bit weird and non-standard. Please have a look at the section below how to construct it.

### 5. Signed Certificate Response
The server returns the signed certificate.

Length   | Description     | Content (hex)
---------|-----------------|--------------
1        | CAPF Magic Byte | `55`
1        | Opcode          | `09`
4        | Session ID      | current session ID
2        | Message Length  | `03 df` (= 991 bytes)
4        | Unknown Field   | `{03} [00 01] 01`
e.g. 987 | Cert Package    | `{04} [03 D8]` + cert package (see below)

The cert package again consists of the following structure:

Length   | Description     | Content (hex)
---------|-----------------|--------------
e.g. 984 | First Cert      | `{01} [03 D5] 00 01` + DER encoded certificate

I don't know what the additional `00 01` is about. Please enlighten us if you have any idea. For now, we simply ignore these two bytes.

The extracted certificate can be saved into a `.crt` file and opened normally with any program like openssl.

### 6. Client Ack
The client acknowledges that it got the certificate.

Length | Description     | Content (hex)
-------|-----------------|--------------
1      | CAPF Magic Byte | `55`
1      | Opcode          | `0a`
4      | Session ID      | current session ID
2      | Message Length  | `00 04`
4      | Status Code     | `{01} [00 01] 01`

### 7. Server Fin
The server closes the connection with this message.

Length | Description     | Content (hex)
-------|-----------------|--------------
1      | CAPF Magic Byte | `55`
1      | Opcode          | `0f`
4      | Session ID      | current session ID
2      | Message Length  | `00 04`
4      | Status Code     | `{01} [00 01] 01`

## Status Codes
Discovered status codes:

- `0x01`: OK
- `0x07`: Server declined request: a certificate was already issued for this phone
- `0x09`: Server declined request: no phone found with this name

## The Certificate Signing Request (CSR)
The CSR is a DER encoded ASN.1 message with the following structure, discovered using https://lapo.it/asn1js. Please note that this is an unusual, very minimal CSR structure, only containing the [RSA public key without further metadata](https://stackoverflow.com/questions/55803033/rsa-public-key-bit-string-format). This is different from CSRs openssl normally generates.

- CertificationRequest SEQUENCE
  - CertificationRequestInfo SEQUENCE
    - version OBJECT IDENTIFIER 1.2.840.113549.1.1.1 rsaEncryption
    - subject Name NULL
  - PublicKey BIT STRING
    - SEQUENCE
      - modulus INTEGER (2048 bit)
      - exponent INTEGER 65537

Please have a look at my sample implementation `generateCsr()` in [CapfWrapper.py](../jabber4linux/CapfWrapper.py) how to correctly construct such an ASN.1 message in Python.
