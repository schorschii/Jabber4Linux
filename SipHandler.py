#!/usr/bin/python3

import socket
import datetime
import random
import time
import pyaudio
import threading
import os, sys

from Tools import ignoreStderr
from AudioSocket import InputAudioSocket, OutputAudioSocket


class SipSocket(socket.socket):
    debug = False

    def __init__(self, debug=False, *args, **kwargs):
        self.debug = debug
        super(SipSocket, self).__init__(*args, **kwargs)

    def sendall(self, payload):
        if(self.debug):
            print('=== OUTGOING SIP MESSAGE ===')
            print(payload.decode('utf-8', errors='replace'))
        socket.socket.sendall(self, payload)

class SipHandler(threading.Thread):
    serverFqdn = None
    serverPort = None

    sipSender = None
    sipNumber = None
    deviceName = None
    contactId = None

    sock = None

    audio = None
    audioIn = None
    audioOut = None

    debug = False

    currentCall = None

    evtRegistrationStatusChanged = None
    evtIncomingCall = None
    evtOutgoingCall = None
    evtCallClosed = None

    # status constants
    REGISTRATION_REGISTERED = 1
    REGISTRATION_FAILED = 2

    INCOMING_CALL_RINGING = 1
    INCOMING_CALL_CANCELED = 2
    INCOMING_CALL_ACCEPTED = 3
    INCOMING_CALL_FAILED = 4

    OUTGOING_CALL_RINGING = 1
    OUTGOING_CALL_ACCEPTED = 2
    OUTGOING_CALL_FAILED = 3

    def __init__(self, serverFqdn, serverPort, sipSender, sipNumber, deviceName, contactId, debug=False, *args, **kwargs):
        self.serverFqdn = serverFqdn
        self.serverPort = serverPort
        self.sipSender = sipSender
        self.sipNumber = sipNumber
        self.deviceName = deviceName
        self.contactId = contactId
        self.debug = debug

        # initialize audio interface
        with ignoreStderr(): self.audio = pyaudio.PyAudio()

        # call Thread constructor
        super(SipHandler, self).__init__(*args, **kwargs)
        self.daemon = True

    def run(self, *args, **kwargs):
        try:
            # start SIP connection
            self.sock = SipSocket(self.debug, socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.serverFqdn, self.serverPort))

            # start registration
            senddata = self.compileRegisterHead(self.sock.getsockname()[0], str(self.sock.getsockname()[1]), '101 REGISTER', self.compileRegisterBody())
            self.sock.sendall(senddata.encode('utf-8'))
        except Exception as e:
            self.evtRegistrationStatusChanged.emit(self.REGISTRATION_FAILED, str(e))
            return

        # wait for incoming messages and handle them when they received completely
        recvdata = ''
        while True:
            newdata = self.sock.recv(4096)
            recvdata += newdata.decode('utf-8', errors='replace')

            # received data can contain multiple SIP messages - handle all separately
            while True:
                if("\r\n\r\n" not in recvdata): break
                splitter = recvdata.split("\r\n\r\n", 1)
                header = splitter[0]
                headerParsed = self.parseSipHead(header)
                if('Content-Length' not in headerParsed): break
                contentLength = int(headerParsed['Content-Length'])
                if(contentLength == 0):
                    self.handleSipMessage(header.strip(), '')
                    recvdata = splitter[1]
                elif(len(splitter[1]) >= contentLength):
                    self.handleSipMessage(header.strip(), splitter[1][:contentLength])
                    recvdata = splitter[1][contentLength:]
                else:
                    # message transmission is not completed yet, wait for next run
                    if(self.debug): print(':: SIP message info: found '+str(len(splitter[1])) + ' bytes but expecting ' + str(contentLength)+', waiting for more...')
                    break

    def handleSipMessage(self, head, body):
        if(self.debug): print('=== INCOMING SIP MESSAGE ===')
        if(self.debug): print(head+"\r\n\r\n"+body)

        headers = self.parseSipHead(head)

        ### handle registration
        #if('REFER' in headers): # what the hell does this REFER message from the SIP server mean? It does not seem necessary to answer it...
        #    senddata = self.compileReferAckHead(headers['Via'], headers['From'], headers['To'], headers['Call-ID'], headers['Contact'])
        #    self.sock.sendall(senddata.encode('utf-8'))
        #    senddata = self.compileRegisterHead(self.sock.getsockname()[0], str(self.sock.getsockname()[1]), '102 REGISTER', '')
        #    self.sock.sendall(senddata.encode('utf-8'))
        if('SIP/2.0' in headers and 'CSeq' in headers and 'REGISTER' in headers['CSeq']):
            if(headers['SIP/2.0'].startswith('100')):
                pass
            elif(headers['SIP/2.0'].startswith('200')):
                self.evtRegistrationStatusChanged.emit(self.REGISTRATION_REGISTERED, '')
            else:
                self.evtRegistrationStatusChanged.emit(self.REGISTRATION_FAILED, headers['Warning'] if 'Warning' in headers else '')

        ### handle incoming calls
        if('INVITE' in headers and 'From_parsed' in headers):
            self.currentCall = {
                'remoteSessionId': headers['Session-ID'].split(';')[0],
                'mySessionId': self.generateSessionId(),
                'headers': headers,
            }
            self.currentCall['headers']['To'] = self.currentCall['headers']['To'] + ';tag='+self.generateTag()
            self.currentCall['number'] = headers['From_parsed']

            # trying
            senddata = self.compileTryingHead(
                headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                self.currentCall['mySessionId'], self.currentCall['remoteSessionId'],
                headers['INVITE'].split(' ')[0]
            )
            self.sock.sendall(senddata.encode('utf-8'))
            self.evtIncomingCall.emit(self.INCOMING_CALL_RINGING)

            # ringing
            senddata = self.compileRingingHead(
                headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                self.currentCall['mySessionId'], self.currentCall['remoteSessionId'],
                headers['INVITE'].split(' ')[0]
            )
            self.sock.sendall(senddata.encode('utf-8'))
            # wait for user to accept call via acceptCall()

        if(self.currentCall != None and 'CANCEL' in headers and 'Session-ID' in headers and headers['Session-ID'].split(';')[0] == self.currentCall['headers']['Session-ID'].split(';')[0]):
            self.evtIncomingCall.emit(self.INCOMING_CALL_CANCELED)

        if(self.currentCall != None and 'ACK' in headers and 'Session-ID' in headers and headers['Session-ID'].split(';')[0] == self.currentCall['headers']['Session-ID'].split(';')[0]):
            # start outgoing audio stream
            dstAddress = None
            dstPort = None
            sdpParsed = self.parseSdpBody(body)
            if('c' in sdpParsed):
                connectionParams = sdpParsed['c'].split(' ')
                dstAddress = connectionParams[2]
            for key, value in sdpParsed['m'].items():
                if(key.startswith('audio ')):
                    audioParams = key.split(' ')
                    dstPort = int(audioParams[1])
            if(dstAddress != None and dstPort != None):
                self.audioOut = OutputAudioSocket(self.audioIn.sock, dstAddress, dstPort, self.audio)
                self.audioOut.start()

        ### handle outgoing calls
        if('SIP/2.0' in headers and 'CSeq' in headers and 'INVITE' in headers['CSeq']):
            if(headers['SIP/2.0'].startswith('100')):
                pass
            # 180=ringing (internal calls), 183=session progress (external landline calls)
            elif((headers['SIP/2.0'].startswith('180') or headers['SIP/2.0'].startswith('183')) and 'Session-ID' in headers):
                self.currentCall['headers'] = headers
                self.currentCall['remoteSessionId'] = headers['Session-ID'].split(';')[0]
                self.evtOutgoingCall.emit(self.OUTGOING_CALL_RINGING, '')
            elif(headers['SIP/2.0'].startswith('200') and 'Session-ID' in headers and headers['Session-ID'].split(';')[1].lstrip('remote=') == self.currentCall['mySessionId']):
                self.evtOutgoingCall.emit(self.OUTGOING_CALL_ACCEPTED, '')
                # start outgoing audio stream
                dstAddress = None
                dstPort = None
                sdpParsed = self.parseSdpBody(body)
                if('c' in sdpParsed):
                    connectionParams = sdpParsed['c'].split(' ')
                    dstAddress = connectionParams[2]
                for key, value in sdpParsed['m'].items():
                    if(key.startswith('audio ')):
                        audioParams = key.split(' ')
                        dstPort = int(audioParams[1])
                if(dstAddress != None and dstPort != None):
                    self.audioOut = OutputAudioSocket(self.audioIn.sock, dstAddress, dstPort, self.audio)
                    self.audioOut.start()
                # send SIP ACK
                senddata = self.compileInviteOkAckHead(
                    headers['To_parsed'],
                    headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                    self.currentCall['mySessionId'], self.currentCall['remoteSessionId']
                )
                self.sock.sendall(senddata.encode('utf-8'))
            else:
                self.evtOutgoingCall.emit(self.OUTGOING_CALL_FAILED, headers['Warning'] if 'Warning' in headers else headers['SIP/2.0'])

        ### handle BYE of incoming and outgoing calls
        if(self.currentCall != None and 'BYE' in headers and 'Session-ID' in headers and headers['Session-ID'].split(';')[0] == self.currentCall['headers']['Session-ID'].split(';')[0]):
            # stop audio streams
            self.audioOut.stop()
            self.audioIn.stop()
            del self.audioOut
            del self.audioIn
            # ack BYE
            senddata = self.compileByeOkHead(
                headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                self.currentCall['mySessionId'], self.currentCall['remoteSessionId']
            )
            self.sock.sendall(senddata.encode('utf-8'))
            self.evtCallClosed.emit()

        ### special: handle phone events ("kpml") in order to establish outgoing external (landline) calls
        if(self.currentCall != None and 'SUBSCRIBE' in headers and headers['CSeq'] == '101 SUBSCRIBE'):
            senddata = self.compileSubscripeAckHead(
                headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
                '101 SUBSCRIBE'
            )
            self.sock.sendall(senddata.encode('utf-8'))
            senddata = self.compileSubscripeNotifyHead(
                headers['Via'], headers['To'], headers['From'], headers['Call-ID'],
                self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
                '1000 NOTIFY', ''
            )
            self.sock.sendall(senddata.encode('utf-8'))
        if(self.currentCall != None and 'SIP/2.0' in headers and headers['SIP/2.0'] == '200 OK' and headers['CSeq'] == '1000 NOTIFY'):
            senddata = self.compileSubscripeNotifyHead(
                headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
                '1001 NOTIFY', '<?xml version="1.0" encoding="UTF-8"?><kpml-response xmlns="urn:ietf:params:xml:ns:kpml-response" version="1.0" code="423" text="Timer Expired" suppressed="false" forced_flush="false" digits="" tag="Backspace OK"/>'
            )
            self.sock.sendall(senddata.encode('utf-8'))
        if(self.currentCall != None and 'SUBSCRIBE' in headers and headers['CSeq'] == '102 SUBSCRIBE'):
            senddata = self.compileSubscripeAckHead(
                headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
                '102 SUBSCRIBE'
            )
            self.sock.sendall(senddata.encode('utf-8'))
            senddata = self.compileSubscripeNotifyHead(
                headers['Via'], headers['To'], headers['From'], headers['Call-ID'],
                self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
                '1002 NOTIFY', '<?xml version="1.0" encoding="UTF-8"?><kpml-response xmlns="urn:ietf:params:xml:ns:kpml-response" version="1.0" code="487" text="Subscription Exp" suppressed="false" forced_flush="false" digits="" tag="Backspace OK"/>'
            )
            self.sock.sendall(senddata.encode('utf-8'))

    def acceptCall(self):
        if(self.currentCall == None): return
        headers = self.currentCall['headers']

        # prepare for incoming audio stream
        self.audioIn = InputAudioSocket(self.sock.getsockname()[0], self.audio)
        self.audioIn.start()

        # ack SIP INVITE message
        senddata = self.compileInviteOkHead(
            headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
            self.currentCall['mySessionId'], self.currentCall['remoteSessionId'], headers['INVITE'].split(' ')[0],
            self.compileInviteBody(self.audioIn.sock.getsockname()[0], str(self.audioIn.sock.getsockname()[1]))
        )
        self.sock.sendall(senddata.encode('utf-8'))
        self.evtIncomingCall.emit(self.INCOMING_CALL_ACCEPTED)

    def rejectCall(self):
        if(self.currentCall == None): return
        headers = self.currentCall['headers']

        # send SIP "Busy here" message
        senddata = self.compileBusyHereHead(
            headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
            self.currentCall['mySessionId'], self.currentCall['remoteSessionId'], headers['INVITE'].split(' ')[0]
        )
        self.sock.sendall(senddata.encode('utf-8'))

    def call(self, number):
        self.currentCall = {
            'number': number,
            'remoteSessionId': self.EMPTY_SESSION_ID,
            'mySessionId': self.generateSessionId(),
            'headers': [],
        }

        # prepare for incoming audio stream
        self.audioIn = InputAudioSocket(self.sock.getsockname()[0], self.audio)
        self.audioIn.start()

        # send SIP INVITE
        senddata = self.compileInviteHead(
            self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
            self.currentCall['mySessionId'], self.currentCall['remoteSessionId'], number,
            self.compileInviteBody(self.audioIn.sock.getsockname()[0], str(self.audioIn.sock.getsockname()[1]))
        )
        self.sock.sendall(senddata.encode('utf-8'))

    def cancelCall(self):
        if(self.currentCall == None): return
        headers = self.currentCall['headers']

        # send SIP CANCEL message
        senddata = self.compileCancelHead(
            headers['From'], headers['To'], headers['Call-ID'],
            self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
            self.currentCall['mySessionId'], self.currentCall['remoteSessionId'],
            self.currentCall['number']
        )
        self.sock.sendall(senddata.encode('utf-8'))

    def closeCall(self, isOutgoingCall):
        if(self.currentCall == None): return
        headers = self.currentCall['headers']

        # stop audio streams
        self.audioOut.stop()
        self.audioIn.stop()
        del self.audioOut
        del self.audioIn

        # send SIP BYE message
        if(isOutgoingCall):
            senddata = self.compileByeHeadOutgoing(
                headers['From'], headers['To'], headers['Call-ID'],
                self.sock.getsockname()[0], str(self.sock.getsockname()[1]),
                self.currentCall['mySessionId'], self.currentCall['remoteSessionId']
            )
        else:
            senddata = self.compileByeHeadIncoming(
                headers['Via'], headers['From'], headers['To'], headers['Call-ID'],
                self.currentCall['mySessionId'], self.currentCall['remoteSessionId']
            )
        self.sock.sendall(senddata.encode('utf-8'))

    def parseSipHead(self, head):
        headers = {}
        counter = 0
        for line in head.split("\r\n"):
            if(counter == 0 and ' ' in line):
                splitter = line.split(' ', 1)
                headers[splitter[0]] = splitter[1]
            else:
                splitter = line.split(': ', 1)
                if(len(splitter) > 1): headers[splitter[0]] = splitter[1]
            counter += 1
        if 'From' in headers and 'sip:' in headers['From'] and '@' in headers['From']:
            headers['From_parsed'] = headers['From'].split('sip:')[1].split('@')[0]
        if 'To' in headers and 'sip:' in headers['To'] and '@' in headers['To']:
            headers['To_parsed'] = headers['To'].split('sip:')[1].split('@')[0]
        return headers

    def parseSdpBody(self, body):
        attrs = {}
        inMediaDescription = None
        for line in body.splitlines():
            splitter = line.split('=', 1)
            if(len(splitter) != 2): continue
            if(splitter[0] in ['m']):
                inMediaDescription = splitter[1]
                if('m' not in attrs): attrs['m'] = {}
                attrs['m'][splitter[1]] = {}
            else:
                if(inMediaDescription != None):
                    if(splitter[0] in attrs['m'][inMediaDescription]):
                        attrs['m'][inMediaDescription][splitter[0]].append(splitter[1])
                    else:
                        attrs['m'][inMediaDescription][splitter[0]] = [splitter[1]]
                else:
                    attrs[splitter[0]] = splitter[1]
        return attrs

    EMPTY_SESSION_ID = '00000000000000000000000000000000'
    def generateSessionId(self):
        return ''.join(random.choice('0123456789abcdef') for _ in range(32))
    def generateTag(self):
        return ''.join(random.choice('0123456789abcdef') for _ in range(24)) + '-' + ''.join(random.choice('0123456789abcdef') for _ in range(8))

    def getTimestamp(self):
        return datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S %Z') # date format: Fri, 17 Mar 2023 14:48:35 GMT"

    def compileRegisterHead(self, clientIp, clientPort, cSeq, body):
        return (f"REGISTER sip:{self.serverFqdn} SIP/2.0\r\n" +
            f"Via: SIP/2.0/TCP {clientIp}:{clientPort};branch=z9hG4bK000050d9\r\n" +
            f"From: <sip:{self.sipNumber}@{self.serverFqdn}>;tag={self.generateTag()}\r\n" +
            f"To: <sip:{self.sipNumber}@{self.serverFqdn}>\r\n" +
            f"Call-ID: 00000000-00000003-0000598b-000053fa@{clientIp}\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: {cSeq}\r\n" +
            f"User-Agent: Cisco-CSF\r\n" +
            f"Contact: <sip:{self.contactId}@{clientIp}:{clientPort};transport=tcp>;+sip.instance=\"<urn:uuid:00000000-0000-0000-0000-000000000000>\";+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\";+u.sip!model.ccm.cisco.com=\"503\";video\r\n" +
            f"Supported: replaces,join,sdp-anat,norefersub,resource-priority,extended-refer,X-cisco-callinfo,X-cisco-serviceuri,X-cisco-escapecodes,X-cisco-service-control,X-cisco-srtp-fallback,X-cisco-monrec,X-cisco-config,X-cisco-sis-7.0.0,X-cisco-sessionpersist,X-cisco-xsi-8.5.1,X-cisco-graceful-reg,X-cisco-duplicate-reg\r\n" +
            f"Reason: SIP;cause=200;text=\"cisco-alarm:25 Name=\"{self.deviceName}\" ActiveLoad=Jabber_for_Windows-14.1.3.57304 InactiveLoad=Jabber_for_Windows-14.1.3.57304 Last=initialized\r\n" +
            f"Expires: 3600\r\n" +
            f"Content-Type: multipart/mixed; boundary=uniqueBoundary\r\n" +
            f"Mime-Version: 1.0\r\n" +
            f"Content-Length: {str(len(body))}\r\n" +
            f"\r\n" + body)
    def compileRegisterBody(self):
        return ("--uniqueBoundary\r\n" +
            "Content-Type: application/x-cisco-remotecc-request+xml\r\n" +
            "Content-Disposition: session;handling=optional\r\n" +
            "\r\n" +
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n" +
            "<x-cisco-remotecc-request>\r\n" +
            "<bulkregisterreq>\r\n" +
            "<contact all=\"true\">\r\n" +
            "<register></register>\r\n" +
            "</contact>\r\n" +
            "</bulkregisterreq>\r\n" +
            "</x-cisco-remotecc-request>\r\n" +
            "\r\n" +
            "--uniqueBoundary\r\n" +
            "Content-Type: application/x-cisco-remotecc-request+xml\r\n" +
            "Content-Disposition: session;handling=optional\r\n" +
            "\r\n" +
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n" +
            "<x-cisco-remotecc-request>\r\n" +
            "  <optionsind>\r\n" +
            "    <combine max=\"6\">\r\n" +
            "      <remotecc>\r\n" +
            "        <status></status>\r\n" +
            "      </remotecc>\r\n" +
            "      <service-control></service-control>\r\n" +
            "    </combine>\r\n" +
            "    <dialog usage=\"hook status\">\r\n" +
            "      <unot></unot>\r\n" +
            "      <sub></sub>\r\n" +
            "    </dialog>\r\n" +
            "    <dialog usage=\"shared line\">\r\n" +
            "      <unot></unot>\r\n" +
            "      <sub></sub>\r\n" +
            "    </dialog>\r\n" +
            "    <presence usage=\"blf speed dial\">\r\n" +
            "      <unot></unot>\r\n" +
            "      <sub></sub>\r\n" +
            "    </presence>\r\n" +
            "    <joinreq></joinreq>\r\n" +
            "    <cfwdall-anyline></cfwdall-anyline>\r\n" +
            "    <coaching></coaching>\r\n" +
            "    <oosalarm></oosalarm>\r\n" +
            "    <x-cisco-number></x-cisco-number>\r\n" +
            "    <bfcp></bfcp>\r\n" +
            "    <ix></ix>\r\n" +
            "    <gatewayrecording></gatewayrecording>\r\n" +
            "    <conferenceDisplayInstance></conferenceDisplayInstance>\r\n" +
            "  </optionsind>\r\n" +
            "</x-cisco-remotecc-request>\r\n" +
            "--uniqueBoundary--\r\n")
    def compileReferAckHead(self, via, fro, to, callId, contact):
        return (f"SIP/2.0 200 OK\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 REFER\r\n" +
            f"Server: Cisco-CSF\r\n" +
            f"Contact: {contact}\r\n" +
            f"Content-Length: 0\r\n" +
            f"\r\n")
    def compileInviteBody(self, clientIp, clientPort):
        return (f"v=0\r\n" +
            f"o=Cisco-SIPUA 22437 0 IN IP4 {clientIp}\r\n" +
            f"s=SIP Call\r\n" +
            f"b=AS:4000\r\n" +
            f"t=0 0\r\n" +
            f"a=cisco-mari:v1\r\n" +
            f"a=cisco-mari-rate\r\n" +
            f"m=audio {clientPort} RTP/AVP 0 8 111 101\r\n" + # original: RTP/AVP 114 9 104 105 0 8 18 111 101
            f"c=IN IP4 {clientIp}\r\n" +
            #f"a=rtpmap:114 opus/48000/2\r\n" +
            #f"a=rtpmap:9 G722/8000\r\n" +
            #f"a=rtpmap:104 G7221/16000\r\n" +
            #f"a=fmtp:104 bitrate=32000\r\n" +
            #f"a=rtpmap:105 G7221/16000\r\n" +
            #f"a=fmtp:105 bitrate=24000\r\n" +
            f"a=rtpmap:0 PCMU/8000\r\n" +
            f"a=rtpmap:8 PCMA/8000\r\n" +
            #f"a=rtpmap:18 G729/8000\r\n" +
            #f"a=fmtp:18 annexb=no\r\n" +
            f"a=rtpmap:111 x-ulpfecuc/8000\r\n" +
            f"a=extmap:14/sendrecv http://protocols.cisco.com/timestamp#100us\r\n" +
            f"a=fmtp:111 max_esel=1420;m=8;max_n=32;FEC_ORDER=FEC_SRTP\r\n" +
            f"a=rtpmap:101 telephone-event/8000\r\n" +
            f"a=fmtp:101 0-16\r\n" +
            f"a=sendrecv\r\n")
    def compileTryingHead(self, via, fro, to, callId, sessionId, remoteSessionId, contact):
        return (f"SIP/2.0 100 Trying\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 INVITE\r\n" +
            f"Server: Cisco-CSF\r\n" +
            f"Contact: <{contact}>;+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\"\r\n" +
            f"Allow: ACK,BYE,CANCEL,INVITE,NOTIFY,OPTIONS,REFER,REGISTER,UPDATE,SUBSCRIBE,INFO\r\n" +
            f"Supported: replaces,join,sdp-anat,norefersub,resource-priority,extended-refer,X-cisco-callinfo,X-cisco-serviceuri,X-cisco-escapecodes,X-cisco-service-control,X-cisco-srtp-fallback,X-cisco-monrec,X-cisco-config,X-cisco-sis-7.0.0,X-cisco-xsi-8.5.1\r\n" +
            f"Allow-Events: kpml,dialog\r\n" +
            f"Recv-Info: conference\r\n" +
            f"Recv-Info: x-cisco-conference\r\n" +
            f"Content-Length: 0\r\n\r\n")
    def compileRingingHead(self, via, fro, to, callId, sessionId, remoteSessionId, contact):
        return (f"SIP/2.0 180 Ringing\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 INVITE\r\n" +
            f"Server: Cisco-CSF\r\n" +
            f"Contact: <{contact}>;+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\"\r\n" +
            f"Remote-Party-ID: \"{self.sipSender}\" <sip:{self.sipNumber}@{self.serverFqdn}>;party=called;id-type=subscriber;privacy=off;screen=yes\r\n" +
            f"Allow: ACK,BYE,CANCEL,INVITE,NOTIFY,OPTIONS,REFER,REGISTER,UPDATE,SUBSCRIBE,INFO\r\n" +
            f"Supported: replaces,join,sdp-anat,norefersub,resource-priority,extended-refer,X-cisco-callinfo,X-cisco-serviceuri,X-cisco-escapecodes,X-cisco-service-control,X-cisco-srtp-fallback,X-cisco-monrec,X-cisco-config,X-cisco-sis-7.0.0,X-cisco-xsi-8.5.1\r\n" +
            f"Allow-Events: kpml,dialog\r\n" +
            f"Content-Length: 0\r\n\r\n")
    def compileBusyHereHead(self, via, fro, to, callId, sessionId, remoteSessionId, contact):
        return (f"SIP/2.0 486 Busy here\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 INVITE\r\n" +
            f"Server: Cisco-CSF\r\n" +
            f"Contact: <{contact}>;+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\"\r\n" +
            f"Remote-Party-ID: \"{self.sipSender}\" <sip:{self.sipNumber}@{self.serverFqdn}>;party=called;id-type=subscriber;privacy=off;screen=yes\r\n" +
            f"Allow: ACK,BYE,CANCEL,INVITE,NOTIFY,OPTIONS,REFER,REGISTER,UPDATE,SUBSCRIBE,INFO\r\n" +
            f"Allow-Events: kpml,dialog\r\n" +
            f"Content-Length: 0\r\n\r\n")
    def compileInviteOkHead(self, via, fro, to, callId, sessionId, remoteSessionId, contact, body):
        return (f"SIP/2.0 200 OK\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 INVITE\r\n" +
            f"Server: Cisco-CSF\r\n" +
            f"Contact: <{contact}>;+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\"\r\n" +
            f"Remote-Party-ID: \"{self.sipSender}\" <sip:{self.sipNumber}@{self.serverFqdn}>;party=called;id-type=subscriber;privacy=off;screen=yes\r\n" +
            f"Allow: ACK,BYE,CANCEL,INVITE,NOTIFY,OPTIONS,REFER,REGISTER,UPDATE,SUBSCRIBE,INFO\r\n" +
            f"Supported: replaces,join,sdp-anat,norefersub,resource-priority,extended-refer,X-cisco-callinfo,X-cisco-serviceuri,X-cisco-escapecodes,X-cisco-service-control,X-cisco-srtp-fallback,X-cisco-monrec,X-cisco-config,X-cisco-sis-7.0.0,X-cisco-xsi-8.5.1\r\n" +
            f"Allow-Events: kpml,dialog\r\n" +
            f"Recv-Info: conference\r\n" +
            f"Recv-Info: x-cisco-conference\r\n" +
            f"Content-Type: application/sdp\r\n" +
            f"Content-Disposition: session;handling=optional\r\n" +
            f"Content-Length: {str(len(body))}\r\n" +
            f"\r\n" + body)
    def compileInviteOkAckHead(self, targetSipNumber, via, fro, to, callId, sessionId, remoteSessionId):
        return (f"ACK sip:{targetSipNumber}@{self.serverFqdn};transport=tcp SIP/2.0\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 ACK\r\n" +
            f"User-Agent: Cisco-CSF\r\n" +
            f"Remote-Party-ID: \"{self.sipSender}\" <sip:{self.sipNumber}@{self.serverFqdn}>;party=called;id-type=subscriber;privacy=off;screen=yes\r\n" +
            f"Recv-Info: conference\r\n" +
            f"Recv-Info: x-cisco-conference\r\n" +
            f"Content-Length: 0\r\n" +
            f"\r\n")
    def compileInviteHead(self, clientIp, clientPort, sessionId, remoteSessionId, targetSipNumber, body):
        return (f"INVITE sip:{targetSipNumber}@{self.serverFqdn};user=phone SIP/2.0\r\n" +
            f"Via: SIP/2.0/TCP {clientIp}:{clientPort};branch=z9hG4bK00005d4d\r\n" +
            f"From: \"{self.sipSender}\" <sip:{self.sipNumber}@{self.serverFqdn}>;tag={self.generateTag()}\r\n" +
            f"To: <sip:{targetSipNumber}@{self.serverFqdn}>\r\n" +
            f"Call-ID: 00505687-43cd0004-00007da9-00002794@{clientIp}\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 INVITE\r\n" +
            f"User-Agent: Cisco-CSF\r\n" +
            f"Contact: <sip:{self.contactId}@{clientIp}:{clientPort};transport=tcp>;+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\"\r\n" +
            f"Expires: 180\r\n" +
            f"Accept: application/sdp\r\n" +
            f"Allow: ACK,BYE,CANCEL,INVITE,NOTIFY,OPTIONS,REFER,REGISTER,UPDATE,SUBSCRIBE,INFO\r\n" +
            f"Remote-Party-ID: \"{self.sipSender}\" <sip:{self.sipNumber}@{self.serverFqdn}>;party=calling;id-type=subscriber;privacy=off;screen=yes\r\n" +
            f"Supported: replaces,join,sdp-anat,norefersub,resource-priority,extended-refer,X-cisco-callinfo,X-cisco-serviceuri,X-cisco-escapecodes,X-cisco-service-control,X-cisco-srtp-fallback,X-cisco-monrec,X-cisco-config,X-cisco-sis-7.0.0,X-cisco-xsi-8.5.1\r\n" +
            f"Allow-Events: kpml,dialog\r\n" +
            f"Recv-Info: conference\r\n" +
            f"Recv-Info: x-cisco-conference\r\n" +
            f"Content-Length: {str(len(body))}\r\n" +
            f"Content-Type: application/sdp\r\n" +
            f"Content-Disposition: session;handling=optional\r\n" +
            f"\r\n" + body)
    def compileCancelHead(self, fro, to, callId, clientIp, clientPort, sessionId, remoteSessionId, targetSipNumber):
        return (f"CANCEL sip:{targetSipNumber}@{self.serverFqdn};user=phone SIP/2.0\r\n" +
            f"Via: SIP/2.0/TCP {clientIp}:{clientPort};branch=z9hG4bK00005d4d\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 CANCEL\r\n" +
            f"User-Agent: Cisco-CSF\r\n" +
            f"Content-Length: 0\r\n" +
            f"\r\n")
    def compileByeHeadOutgoing(self, fro, to, callId, clientIp, clientPort, sessionId, remoteSessionId):
        byeTo = fro.split('<')[1].split('>')[0]
        return (f"BYE {byeTo};transport=tcp SIP/2.0\r\n" +
            f"Via: SIP/2.0/TCP {clientIp}:{clientPort};branch=z9hG4bK00005d4d\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 BYE\r\n" +
            f"User-Agent: Cisco-CSF\r\n" +
            f"Content-Length: 0\r\n" +
            f"\r\n")
    def compileByeHeadIncoming(self, via, fro, to, callId, sessionId, remoteSessionId):
        byeTo = fro.split('<')[1].split('>')[0]
        return (f"BYE {byeTo};transport=tcp SIP/2.0\r\n" +
            f"Via: {via}\r\n" +
            f"From: {to}\r\n" +
            f"To: {fro}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 101 BYE\r\n" +
            f"User-Agent: Cisco-CSF\r\n" +
            f"Content-Length: 0\r\n" +
            f"\r\n")
    def compileByeOkHead(self, via, fro, to, callId, sessionId, remoteSessionId):
        return (f"SIP/2.0 200 OK\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Session-ID: {sessionId};remote={remoteSessionId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: 102 BYE\r\n" +
            f"Server: Cisco-CSF\r\n" +
            #f"RTP-RxStat: Dur=10,Pkt=454,Oct=72640,LostPkt=0,AvgJit=0.185022,VqMetrics=\"CS=0;SCS=0\"\r\n" +
            #f"RTP-TxStat: Dur=10,Pkt=443,Oct=70880\r\n" +
            f"Content-Length: 0\r\n" +
            f"\r\n")
    def compileSubscripeAckHead(self, via, fro, to, callId, clientIp, clientPort, cseq):
        return (f"SIP/2.0 200 OK\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: {cseq}\r\n" +
            f"Server: Cisco-CSF\r\n" +
            f"Contact: <sip:{self.contactId}@{clientIp}:{clientPort};transport=tcp>;+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\"\r\n" +
            f"Expires: 7200\r\n" +
            f"Content-Length: 0\r\n" +
            f"\r\n")
    def compileSubscripeNotifyHead(self, via, fro, to, callId, clientIp, clientPort, cseq, body):
        notifyTo = to.split('<')[1].split('>')[0]
        return (f"NOTIFY {notifyTo};transport=tcp SIP/2.0\r\n" +
            f"Via: {via}\r\n" +
            f"From: {fro}\r\n" +
            f"To: {to}\r\n" +
            f"Call-ID: {callId}\r\n" +
            f"Date: {self.getTimestamp()}\r\n" +
            f"CSeq: {cseq}\r\n" +
            f"Event: kpml\r\n" +
            f"Subscription-State: active; expires=7200\r\n" +
            f"Max-Forwards: 70\r\n" +
            f"Contact: <sip:{self.contactId}@{clientIp}:{clientPort};transport=tcp>;+u.sip!devicename.ccm.cisco.com=\"{self.deviceName}\"\r\n" +
            f"Allow: ACK,BYE,CANCEL,INVITE,NOTIFY,OPTIONS,REFER,REGISTER,UPDATE,SUBSCRIBE\r\n" +
            f"Content-Type: application/kpml-response+xml\r\n" +
            f"Content-Disposition: session;handling=required\r\n" +
            f"Content-Length: {str(len(body))}\r\n" +
            f"\r\n" + body)