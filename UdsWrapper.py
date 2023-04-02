#!/usr/bin/python3

import requests
import urllib.parse
from xml.dom import minidom, expatbuilder
from base64 import b64encode
from dns import resolver, rdatatype


# Cisco User Data Services REST API Wrapper
# todo: threading would be nice
class UdsWrapper():

    username = None
    password = None

    serverName = None
    serverPort = None

    debug = False

    def __init__(self, username, password, serverName=None, serverPort=None, debug=False):
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
        token = b64encode(f'{username}:{password}'.encode('utf-8')).decode("ascii")
        return f'Basic {token}'

    def getUserDetails(self):
        with requests.get(f'https://{self.serverName}:{self.serverPort}/cucm-uds/user/{urllib.parse.quote(self.username)}', headers={'Authorization':self.basic_auth(self.username,self.password)}) as result:
            result.raise_for_status()
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

    def getDevices(self):
        with requests.get(f'https://{self.serverName}:{self.serverPort}/cucm-uds/user/{urllib.parse.quote(self.username)}/devices', headers={'Authorization':self.basic_auth(self.username,self.password)}) as result:
            result.raise_for_status()
            document = minidom.parseString(result.text).documentElement
            values = []
            for item in document.getElementsByTagName('device'):
                values.append({
                    'id': item.getElementsByTagName('id')[0].firstChild.data,
                    'name': item.getElementsByTagName('name')[0].firstChild.data,
                    'type': item.getElementsByTagName('type')[0].firstChild.data,
                    'model': item.getElementsByTagName('model')[0].firstChild.data,
                    'description': item.getElementsByTagName('description')[0].firstChild.data,
                })
            return values

    def getDevice(self, id):
        with requests.get(f'https://{self.serverName}:{self.serverPort}/cucm-uds/user/{urllib.parse.quote(self.username)}/device/{urllib.parse.quote(id)}', headers={'Authorization':self.basic_auth(self.username,self.password)}) as result:
            result.raise_for_status()
            document = minidom.parseString(result.text).documentElement
            values = {
                'id': document.getElementsByTagName('id')[0].firstChild.data,
                'name': document.getElementsByTagName('name')[0].firstChild.data,
                'type': document.getElementsByTagName('type')[0].firstChild.data,
                'model': document.getElementsByTagName('model')[0].firstChild.data,
                'description': document.getElementsByTagName('description')[0].firstChild.data,
                'deviceName': document.getElementsByTagName('name')[0].firstChild.data,
                'number': None,
                'contact': None,
                'callManagers': [],
            }

            for item in document.getElementsByTagName('provision')[0].getElementsByTagName('uri'):
                provisionResult = requests.get(item.firstChild.data, headers={'Authorization':self.basic_auth(self.username,self.password)})
                try:
                    if(self.debug): print(id, item.firstChild.data, provisionResult.text)
                    document2 = expatbuilder.parseString(provisionResult.text, False).documentElement
                except Exception:
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
