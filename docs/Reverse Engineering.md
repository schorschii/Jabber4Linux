# Reverse Engineering Cisco Jabber

## DNS SRV record
Since DNS queries are plaintext, it was an easy one to obtain how Cisco Jabber does the autodiscovery to find the CUCM server using Wireshark.

## SIP and RTP
Basic reverse engineering was done by disabling encryption for a test softphone on the CUCM server. This made it possible to view the SIP and RTP communication in Wireshark and to write a Python program which mimics and generates the same messages. SIPS support was then simply added via Pythons SSLContext socket wrapper.

## UDS REST API
For investigating the CUCM API calls, which are necessary to query metadata of the own softphone and the global address book, the environment variable `SSLKEYLOGFILE` was set. This writes the SSL session keys of the UDS API HTTPS calls into the given file path, which could then be used for decryption with wireshark. This worked because HTTP API calls are done by Jabber using the `libcurl.dll`, which has support `SSLKEYLOGFILE` implemented.

## CAPF protocol
To establish a SIPS session, a client certificate is necessary, which is negotiated on the first login via the proprietary [Cisco CAPF](https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/admin/12_5_1SU1/systemConfig/cucm_b_system-configuration-guide-1251su1/cucm_b_system-configuration-guide-1251su1_restructured_chapter_0101100.html#reference_AA61A26C5ABC7EE8693F280F7FDA9617) [protocol](https://www.cisco.com/c/en/us/support/docs/unified-communications/unified-communications-manager-callmanager/212214-Tech-Note-on-CAPF-Certificate-Signed-by.html) on [port 3804](https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/admin/11_5_1/sysConfig/CUCM_BK_SE5DAF88_00_cucm-system-configuration-guide-1151/CUCM_BK_SE5DAF88_00_cucm-system-configuration-guide-1151_chapter_01010100.html#:~:text=Communications%20Manager%20(CAPF)-,3804,-/%20TCP). (Until now, Jabber4Linux' SIPS connection was established using a certificate exported from a Windows keystore, where Cisco Jabber was started once.) It would be nice to implement this too so we can completely avoid a Windows machine.

The protocol details are not publicly available and `SSLKEYLOGFILE` does not log the required session keys for this connection. In addition to that, the certificate can only be created once, which made it additionally hard to reverse engineer. After one certificate, the softphone account has to be reset by the CUCM admin.

The port 3804 communication first was not interpretable at all, it did not even show up as TLS traffic. Turns out, Wireshark recognizes TLS traffic only [on specific ports or heuristics](https://stackoverflow.com/questions/70955337/how-to-decrypt-https-traffic-on-custom-tcp-port-in-wireshark). After adding the port into "SSL/TLS ports" field in the Wireshark HTTP protocol settings, the encrypted TLS packets were shown. But how to decrypt them?

First try was using [Frida](https://github.com/frida/frida) to intercept Windows' `lsass.exe` for TLS session key generation using [this Frida script](https://github.com/sldlb/win-frida-scripts/tree/master/lsasslkeylog-easy). It worked perfectly for getting keys of the Internet Explorer HTTPS connections, but not for Cisco Jabber. This means that Cisco Jabber is not using the standard Windows syscalls for TLS session key generation.

Next, I noticed the OpenSSL libraries `libssl-1_1.dll` and `libcrypto-1_1.dll` in the program directory. It must be these libraries doing the SSL key exchange. But how to convince libssl to give us the keys? There are [several posts](https://security.stackexchange.com/questions/80158/extract-pre-master-keys-from-an-openssl-application) showing how to use `gdb` or `LD_PRELOAD` to achive this. But unfortunately, they are written for Linux systems. Porting those ideas to Windows seems too complicated.

The final solution was using [FriTap](https://github.com/fkie-cad/friTap). Based on frida, friTap can be attached to the Jabber processes and automatically hook loaded common SSL/TLS libraries like OpenSSL for key and plaintext packet logging. Since Cisco Jabber spawns multiple processes but frida/friTap can only be attached to a single process, I wrote a small script which automatically starts friTab for all Jabber PIDs (`fritap_all.py`) and log the plaintext communication into pcap files.

Now, I had the dumped plaintext CAPF communication in pcap files. Further investigation was necessary, since the content was binary and not easy to understand plaintext like HTTP. The perceptions regarding this protocol are documented in [CAPF Protocol Specification.md](CAPF%20Protocol%20Specification.md) and implemented in [CapfWrapper.py](../jabber4linux/CapfWrapper.py).
