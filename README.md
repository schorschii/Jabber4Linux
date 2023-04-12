# Jabber4Linux

It is annoying that companies always forget to implement their software for the most important operating system. Cisco even offers a native Linux AnyConnect client - but no Cisco Jabber Linux client. Unfortunately, the Windows binary doesn't perform well via Wine and I couldn't get any other Linux-native 3rd party softphone working with our Cisco telephone system, that's why we need another solution.

Jabber4Linux is an unoffical Linux port of the [Cisco Jabber](https://www.cisco.com/c/en/us/products/unified-communications/jabber/index.html) application for macOS and Windows. It is written in pure python. Warning: extremely experimental and unstable.

What it can:
- server auto discovery via DNS SRV record `_cisco-uds._tcp`
- getting user's device information via Cisco UDS REST API
- mimic Cisco Jabber SIP(S) registration
  - optional: force registration (disconnect an other client which is already active and holds the line)
- initiate and accept calls
- realtime de-/encoding of RTP packets with codecs: PCMA, PCMU

What (currently) doesn't:
- intelligent input/output audio device (headset) selection
- company phone book search
- presence / instant messaging
- voice mail access
- conference features
- call transfer
- other commonly used audio codes (Opus, G722, G729)
  - Opus seems to be problematic: libopus on Linux does not decode VoIP opus packets; Opus decoding in Wireshark also only works on Windows >:(
- video telephony
- SRTP/ZRTP encrypted calls

You can put Jabber4Linux in your autostart with parameter `--hidden` to start it only with the tray icon.

For debugging / reporting bugs, please start Jabber4Linux from Terminal with parameter `--debug` and have a look and report the debug output.

Stars & contributions welcome!

## Installation
For Ubuntu 22.04:
```
apt install python3-requests python3-dnspython python3-pyqt5 portaudio19-dev
sudo -H pip3 install -r requirements.txt

./Jabber4Linux.py
```

## Development Resources
- Wireshark ftw
- [SIP](https://de.wikipedia.org/wiki/Session_Initiation_Protocol)
- [SIP Requests](https://de.wikipedia.org/wiki/SIP-Anfragen)
- [RTP](https://de.wikipedia.org/wiki/Real-Time_Transport_Protocol)
- [RTCP](https://de.wikipedia.org/wiki/RealTime_Control_Protocol)
- [SDP](https://de.wikipedia.org/wiki/Session_Description_Protocol)
- [Cisco UDS](https://developer.cisco.com/docs/user-data-services-api-reference/#!overview/overview)
- [CUCM Security Features](https://www.ciscolive.com/c/dam/r/ciscolive/emea/docs/2019/pdf/BRKCOL-3501.pdf)
