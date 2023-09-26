# Jabber4Linux

It is annoying that companies always forget to implement their software for the most important operating system. Cisco even offers a native Linux AnyConnect client - but no Cisco Jabber Linux client. Unfortunately, the Windows binary doesn't perform well via Wine and I couldn't get any other Linux-native 3rd party softphone working with our Cisco telephone system, that's why we need another solution.

Jabber4Linux is an unoffical Linux port of the [Cisco Jabber](https://www.cisco.com/c/en/us/products/unified-communications/jabber/index.html) application for macOS and Windows, written in pure Python. Warning: extremely experimental. Please note that the scope of this project is to emulate the softphone functionality compatible with Cisco CUCM. For chat/XMPP you can use other clients like Pidgin.

What it can:
- server auto discovery via DNS SRV record `_cisco-uds._tcp`
- getting user's device information via Cisco UDS REST API
- mimic Cisco Jabber SIP(S) registration
  - optional: force registration (disconnect an other client which is already active and holds the line)
- initiate and accept calls
- realtime de-/encoding of RTP packets with codecs: PCMA, PCMU, Opus (HD telephony)
- company phone book search
- local address book with option to set custom ringtones per contact
- handle "tel:" parameter/links (from websites)
- SIPS (encrypted registration)
- call subjects

What (currently) doesn't:
- input/output audio device (headset) and ringtone devices selection
- presence / instant messaging
- voice mail access
- conference features
- call transfer
- video telephony
- SRTP/ZRTP encrypted calls

You can put Jabber4Linux in your autostart with parameter `--hidden` to start it only with the tray icon.

For debugging / reporting bugs, please start Jabber4Linux from Terminal with parameter `--debug` and have a look and report the debug output.

Stars & contributions welcome!

## Installation
For Ubuntu 22.04:
```
apt install python3-requests python3-dnspython python3-pyqt5 portaudio19-dev python3-watchdog python3-cryptography python3-pip
sudo -H pip3 install -r requirements.txt

./Jabber4Linux.py
```

## SIP Transport Encryption (SIPS)
Your CUCM administrator can choose whether your softphone should operate encrypted using SIPS (this option is called "Secure" in the management interface) or unencrypted using plaintext SIP ("Non-Secure").

Besides SIP, SIPS is also supported by Jabber4Linux. For the TLS connection, a client certificate (called "LSC" - Locally Significant Certificate) is necessary, which is signed using the Cisco [CAPF protocol](docs/Reverse%20Engineering.md#capf-protocol) on port 3804 from the CUCM server. The pitfall is that such a certificate is only issued once; every further signing request will be denied by the CUCM server. If you already used Cisco Jabber on Windows before, you need to export the softphone certificate from the Windows cert store. Alternatively, you can contact your CUCM admin who can reset your softphone instance. This will allow your client to get a new certificate once again.

<details>
<summary>Export Certificate from Windows Cert Store</summary>

1. Log in into Cisco Jabber on a Windows machine.
2. Open the user cert store (`certmgr.msc`) and navigate to "Own Certificates" -> "Certificates".
3. Export your Cisco Jabber certificate by right-clicking it -> "All Tasks" -> "Export".
   - Choose "Yes, export private key".
   - Choose format "PKCS #12 (.PFX)".
   - Choose a password to protect the file.
4. On your Linux machine, convert the file into PEM format: `openssl pkcs12 -in jabbercert.pfx -out jabbercert.pem -nodes`.
4. Move the PEM file into `~/.config/jabber4linux/client-certs`. Create the directory if it does not exist.
5. Start Jabber4Linux and login.
</details>

<details>
<summary>Server Certificate Pinning</summary>

In addition to that, server certificates of Cisco CUCM used for SIPS are often self-signed (unlike those used for the UDS API and web interface). You can put all server certificates which should be trusted inside `~/.config/jabber4linux/server-certs` and they will automatically be loaded.
</details>

## Development
### I18n
```
# 1. Create translation files from code
pylupdate5 certuploader.py -ts lang/de.ts

# 2. Use Qt Linguist to translate the file

# 3. Compile translation files for usage
lrelease lang/de.ts
```

### Resources
Reverse engineering findings were documented in the [docs](docs/) folder. Wireshark was the biggest help for this project.

Helpful links:
- [SIP](https://de.wikipedia.org/wiki/Session_Initiation_Protocol)
- [SIP Requests](https://de.wikipedia.org/wiki/SIP-Anfragen)
- [RTP](https://de.wikipedia.org/wiki/Real-Time_Transport_Protocol)
- [RTCP](https://de.wikipedia.org/wiki/RealTime_Control_Protocol)
- [SDP](https://de.wikipedia.org/wiki/Session_Description_Protocol)
- [Cisco UDS](https://developer.cisco.com/docs/user-data-services-api-reference/#!overview/overview)
- [CUCM Security Features](https://www.ciscolive.com/c/dam/r/ciscolive/emea/docs/2019/pdf/BRKCOL-3501.pdf)

## Support
You can hire me for commercial support or adjustments for this project. Please [contact me](https://georg-sieber.de/?page=impressum) if you are interested.
