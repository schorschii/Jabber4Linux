#!/usr/bin/env python3

import traceback
import requests
import urllib.parse
import threading
import ssl
from xml.dom import minidom, expatbuilder
from base64 import b64encode
from dns import resolver, rdatatype


class CustomHTTPAdapter(requests.adapters.HTTPAdapter):

    def __init__(self, trustedCerts, debug=False, *args, **kwargs):
        self.debug = debug
        self.trustedCerts = trustedCerts
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        # this creates a default context with secure default settings,
        # which enables server certficiate verification using the
        # system's default CA certificates
        #context = ssl.create_default_context()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # load trusted server certs
        for fileName in self.trustedCerts:
            if(self.debug): print(f':: trusting UDS server cert {fileName}')
            context.load_verify_locations(fileName)

        # alternatively, you could create your own context manually
        # but this does NOT enable server certificate verification
        super().init_poolmanager(*args, **kwargs, ssl_context=context)


# Cisco User Data Services REST API Wrapper
# todo: threading would be nice
class UdsWrapper():

    username = None
    password = None

    serverName = None
    serverPort = None

    debug = False

    def __init__(self, username=None, password=None, serverName=None, serverPort=None, trustedCerts=None, debug=False):
        self.username = username
        self.password = password
        self.debug = debug

        if serverName != None and serverName != '' and serverPort != None and int(serverPort) != 0:
            self.serverName = serverName
            self.serverPort = serverPort
        else:
            discoveredServer = self.discoverUdsServer()
            if discoveredServer != None:
                self.serverName = discoveredServer['address']
                self.serverPort = discoveredServer['port']
        if self.serverName == None:
            raise Exception('UDS server not found')

        self.http_session = requests.Session()
        if(trustedCerts):
            # trust custom certs if at least one is given
            # otherwise, system default CAs are used
            self.http_session.mount('https://', CustomHTTPAdapter(trustedCerts=trustedCerts, debug=debug))

    def discoverUdsServer(self):
        try:
            res = resolver.resolve(qname='_cisco-uds._tcp', rdtype=rdatatype.SRV, lifetime=10, search=True)
            for srv in res.rrset:
                return {
                    # strip the trailing . from the dns resolver for certificate verification reasons
                    'address': str(srv.target).rstrip('.'),
                    'port': srv.port
                }
        except Exception as e:
            print('DNS auto discovery failed: '+str(e))
        return None

    def basic_auth(self, username, password):
        token = b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
        return f'Basic {token}'

    def getUserDetails(self):
        url = f'https://{self.serverName}:{self.serverPort}/cucm-uds/user/{urllib.parse.quote(self.username)}'
        with self.http_session.get(url, headers={'Authorization':self.basic_auth(self.username,self.password)}) as result:
            result.raise_for_status()
            if(self.debug): print(url, '::', result.text, "\n")
            document = minidom.parseString(result.text).documentElement
            values = {
                'id': document.getElementsByTagName('id')[0].firstChild.data,
                'userName': None,
                'firstName': None,
                'lastName': None,
                'displayName': None,
                'phoneNumber': None,
                'homeNumber': None,
                'mobileNumber': None,
                'remoteDestinationLimit': 0,
                'email': None,
                'imAndPresenceServers': [],
                'serviceProfileUris': [],
                'devicesUri': [],
                'credentialsUri': [],
                'extensionsUri': [],
                'speedDialsUri': [],
            }
            if document.getElementsByTagName('userName')[0].firstChild:
                values['userName'] = document.getElementsByTagName('userName')[0].firstChild.data
            if document.getElementsByTagName('firstName')[0].firstChild:
                values['firstName'] = document.getElementsByTagName('firstName')[0].firstChild.data
            if document.getElementsByTagName('lastName')[0].firstChild:
                values['lastName'] = document.getElementsByTagName('lastName')[0].firstChild.data
            if document.getElementsByTagName('displayName')[0].firstChild:
                values['displayName'] = document.getElementsByTagName('displayName')[0].firstChild.data
            if document.getElementsByTagName('phoneNumber')[0].firstChild:
                values['phoneNumber'] = document.getElementsByTagName('phoneNumber')[0].firstChild.data
            if document.getElementsByTagName('homeNumber')[0].firstChild:
                values['homeNumber'] = document.getElementsByTagName('homeNumber')[0].firstChild.data
            if document.getElementsByTagName('mobileNumber')[0].firstChild:
                values['mobileNumber'] = document.getElementsByTagName('mobileNumber')[0].firstChild.data
            if document.getElementsByTagName('remoteDestinationLimit')[0].firstChild:
                values['remoteDestinationLimit'] = int(document.getElementsByTagName('remoteDestinationLimit')[0].firstChild.data)
            if document.getElementsByTagName('email')[0].firstChild:
                values['email'] = document.getElementsByTagName('email')[0].firstChild.data
            if document.getElementsByTagName('imAndPresence') and document.getElementsByTagName('imAndPresence')[0].getElementsByTagName('server'):
                for item in document.getElementsByTagName('imAndPresence')[0].getElementsByTagName('server'):
                    values['imAndPresenceServers'].append(item.firstChild.data)
            if document.getElementsByTagName('serviceProfile') and document.getElementsByTagName('serviceProfile')[0].getElementsByTagName('uri'):
                for item in document.getElementsByTagName('serviceProfile')[0].getElementsByTagName('uri'):
                    values['serviceProfileUris'].append(item.firstChild.data)
            if document.getElementsByTagName('devices'):
                values['devicesUri'] = document.getElementsByTagName('devices')[0].getAttribute('uri')
            if document.getElementsByTagName('credential'):
                values['credentialsUri'] = document.getElementsByTagName('credential')[0].getAttribute('uri')
            if document.getElementsByTagName('extensions'):
                values['extensionsUri'] = document.getElementsByTagName('extensions')[0].getAttribute('uri')
            if document.getElementsByTagName('speedDials'):
                values['speedDialsUri'] = document.getElementsByTagName('speedDials')[0].getAttribute('uri')
            return values

    def getFirstElementByTagName(self, item, tag):
        try:
            return item.getElementsByTagName(tag)[0].firstChild.data
        except AttributeError:
            return ''

    def getDevices(self):
        url = f'https://{self.serverName}:{self.serverPort}/cucm-uds/user/{urllib.parse.quote(self.username)}/devices'
        with self.http_session.get(url, headers={'Authorization':self.basic_auth(self.username,self.password)}) as result:
            result.raise_for_status()
            if(self.debug): print(url, '::', result.text, "\n")
            document = minidom.parseString(result.text).documentElement
            values = []
            for item in document.getElementsByTagName('device'):
                values.append({
                    'id': item.getElementsByTagName('id')[0].firstChild.data,
                    'name': item.getElementsByTagName('name')[0].firstChild.data,
                    'type': item.getElementsByTagName('type')[0].firstChild.data,
                    'model': item.getElementsByTagName('model')[0].firstChild.data,
                    'description': self.getFirstElementByTagName(item, 'description'),
                })
            return values

    def getDevice(self, id):
        url = f'https://{self.serverName}:{self.serverPort}/cucm-uds/user/{urllib.parse.quote(self.username)}/device/{urllib.parse.quote(id)}'
        with self.http_session.get(url, headers={'Authorization':self.basic_auth(self.username,self.password)}) as result:
            result.raise_for_status()
            if(self.debug): print(url, '::', result.text, "\n")
            document = minidom.parseString(result.text).documentElement
            values = {
                'id': document.getElementsByTagName('id')[0].firstChild.data,
                'name': document.getElementsByTagName('name')[0].firstChild.data,
                'type': document.getElementsByTagName('type')[0].firstChild.data,
                'model': document.getElementsByTagName('model')[0].firstChild.data,
                'description': self.getFirstElementByTagName(document, 'description'),
                'deviceName': document.getElementsByTagName('name')[0].firstChild.data,
                'number': None,
                'contact': None,
                'callManagers': [],
                'deviceSecurityMode': '0',
                'certHash': None,
                'capfServers': [],
            }

            for item in document.getElementsByTagName('provision')[0].getElementsByTagName('uri'):
                provisionResult = self.http_session.get(item.firstChild.data, headers={'Authorization':self.basic_auth(self.username,self.password)})
                try:
                    if(self.debug): print(item.firstChild.data, '::', provisionResult.text, "\n")
                    document2 = expatbuilder.parseString(provisionResult.text, False).documentElement
                    values['deviceSecurityMode'] = document2.getElementsByTagName('deviceSecurityMode')[0].firstChild.data
                    values['transportLayerProtocol'] = document2.getElementsByTagName('transportLayerProtocol')[0].firstChild.data
                    values['certHash'] = document2.getElementsByTagName('certHash')[0].firstChild.data if document2.getElementsByTagName('certHash')[0].firstChild else None
                    for capfList in document2.getElementsByTagName('capfList'):
                        for capfEntry in capfList.getElementsByTagName('capf'):
                            values['capfServers'].append({
                                'address': capfEntry.getElementsByTagName('processNodeName')[0].firstChild.data if capfEntry.getElementsByTagName('processNodeName')[0].firstChild else None,
                                'port': capfEntry.getElementsByTagName('phonePort')[0].firstChild.data if capfEntry.getElementsByTagName('phonePort')[0].firstChild else None,
                            })
                except Exception:
                    if(self.debug): traceback.print_exc()
                    return None

                for sl in document2.getElementsByTagName('sipLines'):
                    for l in sl.getElementsByTagName('line'):
                        values['number'] = l.getElementsByTagName('name')[0].firstChild.data
                        values['contact'] = l.getElementsByTagName('contact')[0].firstChild.data
                        break

                for dp in document2.getElementsByTagName('devicePool'):
                    for cmg in dp.getElementsByTagName('callManagerGroup'):
                        for ms in cmg.getElementsByTagName('members'):
                            for m in ms.getElementsByTagName('member'):
                                for cm in m.getElementsByTagName('callManager'):
                                    values['callManagers'].append({
                                        'address': cm.getElementsByTagName('name')[0].firstChild.data,
                                        'sipPort': int(cm.getElementsByTagName('ports')[0].getElementsByTagName('sipPort')[0].firstChild.data),
                                        'sipsPort': int(cm.getElementsByTagName('ports')[0].getElementsByTagName('securedSipPort')[0].firstChild.data),
                                    })
                break
            return values

    def queryPhoneBook(self, name, signal):
        searchUrl = f'https://{self.serverName}:{self.serverPort}/cucm-uds/users?max=10&start=0&name={urllib.parse.quote(name)}'
        t = threading.Thread(target=self.parsePhoneBook, args=(searchUrl,signal,))
        t.start()
    def parsePhoneBook(self, url, signal):
        users = []
        with self.http_session.get(url) as response:
            response.raise_for_status()
            response.encoding = 'UTF-8'
            document = minidom.parseString(response.text).documentElement
            for user in document.getElementsByTagName('user'):
                users.append({
                    'id': user.getElementsByTagName('id')[0].firstChild.data if user.getElementsByTagName('id')[0].firstChild else '',
                    'userName': user.getElementsByTagName('userName')[0].firstChild.data if user.getElementsByTagName('userName')[0].firstChild else '',
                    'firstName': user.getElementsByTagName('firstName')[0].firstChild.data if user.getElementsByTagName('firstName')[0].firstChild else '',
                    'lastName': user.getElementsByTagName('lastName')[0].firstChild.data if user.getElementsByTagName('lastName')[0].firstChild else '',
                    'middleName': user.getElementsByTagName('middleName')[0].firstChild.data if user.getElementsByTagName('middleName')[0].firstChild else '',
                    'displayName': user.getElementsByTagName('displayName')[0].firstChild.data if user.getElementsByTagName('displayName')[0].firstChild else '',
                    'phoneNumber': user.getElementsByTagName('phoneNumber')[0].firstChild.data if user.getElementsByTagName('phoneNumber')[0].firstChild else '',
                    'homeNumber': user.getElementsByTagName('homeNumber')[0].firstChild.data if user.getElementsByTagName('homeNumber')[0].firstChild else '',
                    'mobileNumber': user.getElementsByTagName('mobileNumber')[0].firstChild.data if user.getElementsByTagName('mobileNumber')[0].firstChild else '',
                    'email': user.getElementsByTagName('email')[0].firstChild.data if user.getElementsByTagName('email')[0].firstChild else '',
                    'directoryUri': user.getElementsByTagName('directoryUri')[0].firstChild.data if user.getElementsByTagName('directoryUri')[0].firstChild else '',
                    'msUri': user.getElementsByTagName('msUri')[0].firstChild.data if user.getElementsByTagName('msUri')[0].firstChild else '',
                    'department': user.getElementsByTagName('department')[0].firstChild.data if user.getElementsByTagName('department')[0].firstChild else '',
                    'manager': user.getElementsByTagName('manager')[0].firstChild.data if user.getElementsByTagName('manager')[0].firstChild else '',
                    'title': user.getElementsByTagName('title')[0].firstChild.data if user.getElementsByTagName('title')[0].firstChild else '',
                    'pager': user.getElementsByTagName('pager')[0].firstChild.data if user.getElementsByTagName('pager')[0].firstChild else '',
                })
            signal.emit(users)
