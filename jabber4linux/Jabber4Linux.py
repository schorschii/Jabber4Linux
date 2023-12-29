#!/usr/bin/env python3

from PyQt5 import QtWidgets
from PyQt5 import QtGui
from PyQt5 import QtCore

from .__init__ import __title__, __version__, __website__
from .CapfWrapper import CapfWrapper
from .UdsWrapper import UdsWrapper
from .SipHandler import SipHandler
from .AudioSocket import AudioPlayer
from .Tools import ignoreStderr, niceTime

from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives import hashes
from functools import partial
from pathlib import Path
from threading import Thread, Timer
from locale import getdefaultlocale
import urllib.parse
import watchdog.events
import watchdog.observers
import filelock
import datetime
import pyaudio
import time
import argparse
import json
import re
import sys, os
import traceback


CFG_DIR  = str(Path.home())+'/.config/jabber4linux'
CFG_PATH = CFG_DIR+'/settings.json'
HISTORY_PATH = CFG_DIR+'/history.json'
PHONEBOOK_PATH = CFG_DIR+'/phonebook.json'
CLIENT_CERTS_DIR = CFG_DIR+'/client-certs'
SERVER_CERTS_DIR = CFG_DIR+'/server-certs'

QT_STYLESHEET = """
    QPushButton#destructive, QPushButton#constructive {
        min-width: 60px;
        border: none;
        border-radius: 2px;
        padding: 8px;
        outline: none;
    }
    QPushButton#destructive:focus, QPushButton#constructive:focus {
        font-weight: bold;
    }
    QPushButton#destructive {
        color: white;
        background-color: #FF5C48;
    }
    QPushButton#destructive:hover {
        background-color: #97362B;
    }
    QPushButton#destructive:pressed {
        background-color: #6C271E;
    }
    QPushButton#constructive {
        color: white;
        background-color: #239B2A;
    }
    QPushButton#constructive:hover {
        background-color: #1C7E22;
    }
    QPushButton#constructive:pressed {
        background-color: #155F1A;
    }
"""


def translate(text):
    return QtWidgets.QApplication.translate(__title__, text)

def showErrorDialog(title, text, additionalText='', icon=QtWidgets.QMessageBox.Critical):
    print('(GUI ERROR DIALOG)', text)
    msg = QtWidgets.QMessageBox()
    msg.setIcon(icon)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setDetailedText(additionalText)
    msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
    msg.exec()

def isDarkMode(palette):
    return (palette.color(QtGui.QPalette.Background).red() < 100
        and palette.color(QtGui.QPalette.Background).green() < 100
        and palette.color(QtGui.QPalette.Background).blue() < 100)

class AboutWindow(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
        super(AboutWindow, self).__init__(*args, **kwargs)

        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.accepted.connect(self.accept)

        self.layout = QtWidgets.QVBoxLayout(self)

        labelAppName = QtWidgets.QLabel(self)
        labelAppName.setText(__title__ + ' v' + __version__)
        labelAppName.setStyleSheet('font-weight:bold')
        labelAppName.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(labelAppName)

        labelCopyright = QtWidgets.QLabel(self)
        labelCopyright.setText(
            '<br>'
            '© 2023 <a href="https://georg-sieber.de">Georg Sieber</a>'
            '<br>'
            '<br>'
            'GNU General Public License v3.0'
            '<br>'
            '<a href="'+__website__+'">'+__website__+'</a>'
            '<br>'
            '<br>'
            'If you like Jabber4Linux please consider<br>making a donation to support further development.'
            '<br>'
        )
        labelCopyright.setOpenExternalLinks(True)
        labelCopyright.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(labelCopyright)

        labelDescription = QtWidgets.QLabel(self)
        labelDescription.setText(
            translate('Jabber4Linux is a unofficial Cisco Jabber port for Linux.')
        )
        labelDescription.setStyleSheet('opacity:0.8')
        labelDescription.setFixedWidth(450)
        labelDescription.setWordWrap(True)
        labelDescription.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(labelDescription)

        self.layout.addWidget(self.buttonBox)

        self.setLayout(self.layout)
        self.setWindowTitle('About')

class LoginWindow(QtWidgets.QDialog):
    def __init__(self, mainWindow=None, debug=False, *args, **kwargs):
        self.debug = debug
        self.mainWindow = mainWindow
        super(LoginWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok|QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setText(translate('Login'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setText(translate('Exit'))
        self.buttonBox.accepted.connect(self.login)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QtWidgets.QGridLayout(self)

        discoveredServer = UdsWrapper.discoverUdsServer(None)
        self.lblServerName = QtWidgets.QLabel(translate('Server'))
        self.layout.addWidget(self.lblServerName, 0, 0)

        self.txtServerName = QtWidgets.QLineEdit()
        self.txtServerName.setPlaceholderText(translate('Address'))
        if discoveredServer != None: self.txtServerName.setText(discoveredServer['address'])
        self.layout.addWidget(self.txtServerName, 0, 1)

        self.txtServerPort = QtWidgets.QLineEdit()
        self.txtServerPort.setPlaceholderText(translate('Port'))
        if discoveredServer != None: self.txtServerPort.setText(str(discoveredServer['port']))
        self.layout.addWidget(self.txtServerPort, 0, 2)

        self.lblUsername = QtWidgets.QLabel(translate('Username'))
        self.layout.addWidget(self.lblUsername, 1, 0)
        self.txtUsername = QtWidgets.QLineEdit()
        self.layout.addWidget(self.txtUsername, 1, 1, 1, 2)

        self.lblPassword = QtWidgets.QLabel(translate('Password'))
        self.layout.addWidget(self.lblPassword, 2, 0)
        self.txtPassword = QtWidgets.QLineEdit()
        self.txtPassword.setEchoMode(QtWidgets.QLineEdit.Password)
        self.layout.addWidget(self.txtPassword, 2, 1, 1, 2)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle(translate('Jabber4Linux Login'))
        self.resize(350, 150)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        # directly focus the username field if the server was auto-discovered
        if discoveredServer != None:
            self.txtUsername.setFocus()

    def closeEvent(self, event):
        QtCore.QCoreApplication.exit()

    def login(self):
        self.txtUsername.setEnabled(False)
        self.txtPassword.setEnabled(False)
        self.txtServerName.setEnabled(False)
        self.txtServerPort.setEnabled(False)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setEnabled(False)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setText(translate('Please wait...'))

        try:
            # query necessary details from API
            # throws auth & connection errors, preventing to go to the main window on error
            uds = UdsWrapper(self.txtUsername.text(), self.txtPassword.text(), self.txtServerName.text(), self.txtServerPort.text(), debug=self.debug)
            userDetails = uds.getUserDetails()
            devices = []
            for device in uds.getDevices():
                deviceDetails = uds.getDevice(device['id'])
                if deviceDetails != None and deviceDetails['model'] == 'Cisco Unified Client Services Framework':
                    devices.append(deviceDetails)
            if len(devices) == 0: raise Exception('Unable to find a Jabber softphone device')

            if(self.mainWindow == None):
                self.mainWindow = MainWindow({'user':userDetails, 'devices':devices}, debug=self.debug)
            else:
                self.mainWindow.user = userDetails
                self.mainWindow.devices = devices
            self.mainWindow.show()
            self.accept()

        except Exception as e:
            print(traceback.format_exc())
            showErrorDialog(translate('Login Error'), str(e))

            self.txtUsername.setEnabled(True)
            self.txtPassword.setEnabled(True)
            self.txtServerName.setEnabled(True)
            self.txtServerPort.setEnabled(True)
            self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)
            self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setEnabled(True)
            self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setText(translate('Login'))

class IncomingCallWindow(QtWidgets.QDialog):
    def __init__(self, callerText, diversionText, *args, **kwargs):
        super(IncomingCallWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Yes|QtWidgets.QDialogButtonBox.No)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Yes).setText(translate('Yes'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.No).setText(translate('No'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Yes).setObjectName('constructive')
        self.buttonBox.button(QtWidgets.QDialogButtonBox.No).setObjectName('destructive')
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QtWidgets.QGridLayout(self)

        self.lblFrom1 = QtWidgets.QLabel(callerText)
        self.lblFrom1.setStyleSheet('font-weight:bold')
        self.layout.addWidget(self.lblFrom1, 0, 0)
        self.lblFrom2 = QtWidgets.QLabel(diversionText)
        self.layout.addWidget(self.lblFrom2, 1, 0)

        self.layout.addWidget(self.buttonBox, 2, 0)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle(translate('Incoming Call'))
        self.resize(250, 100)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

class OutgoingCallWindow(QtWidgets.QDialog):
    def __init__(self, callerText, *args, **kwargs):
        super(OutgoingCallWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setText(translate('Cancel'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setObjectName('destructive')
        self.buttonBox.rejected.connect(self.accept) # accept means: cancel call!

        self.layout = QtWidgets.QGridLayout(self)

        self.lblTo = QtWidgets.QLabel(callerText)
        self.lblTo.setStyleSheet('font-weight:bold')
        self.layout.addWidget(self.lblTo, 0, 0)

        self.layout.addWidget(self.buttonBox, 1, 0)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle(translate('Outgoing Call'))
        self.resize(250, 100)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

class CallWindow(QtWidgets.QDialog):
    def __init__(self, remotePartyName, isOutgoingCall, *args, **kwargs):
        self.isOutgoingCall = isOutgoingCall
        self.startTime = time.time()
        super(CallWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setText(translate('Hang Up'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setObjectName('destructive')
        self.buttonBox.rejected.connect(self.cancelCall)

        self.layout = QtWidgets.QGridLayout(self)

        self.lblRemotePartyName = QtWidgets.QLabel(remotePartyName)
        self.lblRemotePartyName.setStyleSheet('font-weight:bold')
        self.layout.addWidget(self.lblRemotePartyName, 0, 0)

        self.lblCallTimer = QtWidgets.QLabel(niceTime(0))
        self.layout.addWidget(self.lblCallTimer, 1, 0)

        self.layout.addWidget(self.buttonBox, 2, 1)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle(translate('Current Call'))
        self.resize(250, 100)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        # schedule call timer update
        self.refreshCallTimer()

    def closeEvent(self, event):
        self.callTimeInterval.cancel()
        self.reject()

    def cancelCall(self):
        self.callTimeInterval.cancel()
        self.reject() # reject dialog result code means: close call (BYE)!

    def refreshCallTimer(self):
        self.lblCallTimer.setText(niceTime(time.time() - self.startTime))
        self.callTimeInterval = Timer(1, self.refreshCallTimer)
        self.callTimeInterval.daemon = True
        self.callTimeInterval.start()

class PhoneBookEntryWindow(QtWidgets.QDialog):
    def __init__(self, mainWindow, number=None, entry=None, *args, **kwargs):
        super(PhoneBookEntryWindow, self).__init__(*args, **kwargs)
        self.mainWindow = mainWindow
        self.entry = entry

        # window layout
        layout = QtWidgets.QGridLayout()

        self.lblCall = QtWidgets.QLabel(translate('Name'))
        layout.addWidget(self.lblCall, 0, 0)
        self.txtName = QtWidgets.QLineEdit()
        if(entry != None): self.txtName.setText( self.mainWindow.phoneBook[entry]['displayName'] )
        layout.addWidget(self.txtName, 0, 1)

        self.lblCall = QtWidgets.QLabel(translate('Number'))
        layout.addWidget(self.lblCall, 1, 0)
        self.txtNumber = QtWidgets.QLineEdit()
        if(entry != None): self.txtNumber.setText( self.mainWindow.phoneBook[entry]['number'] )
        elif(number): self.txtNumber.setText(number)
        layout.addWidget(self.txtNumber, 1, 1)

        self.lblCall = QtWidgets.QLabel(translate('Ringtone'))
        layout.addWidget(self.lblCall, 2, 0)
        self.txtCustomRingtone = QtWidgets.QLineEdit()
        if(entry != None): self.txtCustomRingtone.setText( self.mainWindow.phoneBook[entry]['ringtone'] )
        self.txtCustomRingtone.setPlaceholderText(translate('(optional)'))
        layout.addWidget(self.txtCustomRingtone, 2, 1)
        self.btnChooseRingtone = QtWidgets.QPushButton('...')
        self.btnChooseRingtone.clicked.connect(self.clickChooseRingtone)
        layout.addWidget(self.btnChooseRingtone, 2, 2)

        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save|QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Save).setText(translate('Save'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setText(translate('Cancel'))
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox, 3, 0, 1, 3)
        self.setLayout(layout)

        # window properties
        self.setWindowTitle(translate('Phone Book Entry'))

    def clickChooseRingtone(self, e):
        fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, translate('Ringtone File'), self.txtCustomRingtone.text(), 'WAV Audio Files (*.wav);;')
        if fileName: self.txtCustomRingtone.setText(fileName)

    def accept(self):
        if(self.entry != None):
            self.mainWindow.phoneBook[self.entry]['displayName'] = self.txtName.text()
            self.mainWindow.phoneBook[self.entry]['number'] = self.txtNumber.text()
            self.mainWindow.phoneBook[self.entry]['ringtone'] = self.txtCustomRingtone.text()
        else:
            self.mainWindow.phoneBook.append({
                'displayName': self.txtName.text(),
                'number': self.txtNumber.text(),
                'ringtone': self.txtCustomRingtone.text()
            })
        self.mainWindow.phoneBook = sorted(self.mainWindow.phoneBook, key=lambda d: d['displayName'])
        self.mainWindow.tblPhoneBook.setData(self.mainWindow.phoneBook)
        self.mainWindow.tblCalls.setData(self.mainWindow.callHistory, self.mainWindow.phoneBook)
        savePhoneBook(self.mainWindow.phoneBook)
        self.close()

class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self, icon, parent):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.parentWidget = parent
        menu = QtWidgets.QMenu(parent)
        openAction = menu.addAction(translate('Open Jabber4Linux'))
        openAction.triggered.connect(self.open)
        exitAction = menu.addAction(translate('Exit'))
        exitAction.triggered.connect(self.exit)
        self.setContextMenu(menu)
        self.activated.connect(self.showMenuOnTrigger)
        self.setToolTip(__title__)

    def showMenuOnTrigger(self, reason):
        if(reason == QtWidgets.QSystemTrayIcon.Trigger):
            self.contextMenu().popup(QtGui.QCursor.pos())

    def open(self):
        self.parentWidget.show()
        if(self.parentWidget.status == MainWindow.STATUS_NOTIFY):
            self.parentWidget.setTrayIcon(MainWindow.STATUS_OK, True) # remove notification icon when clicked on tray icon

    def exit(self):
        self.parentWidget.close()
        QtCore.QCoreApplication.exit()

class PhoneBookTable(QtWidgets.QTableWidget):
    keyPressed = QtCore.pyqtSignal(QtGui.QKeyEvent)

    def __init__(self, *args):
        self.entries = {}
        QtWidgets.QTableWidget.__init__(self, *args)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        #self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QTableWidget.EditTrigger.NoEditTriggers)

    def keyPressEvent(self, event):
        super(PhoneBookTable, self).keyPressEvent(event)
        if(not event.isAutoRepeat()): self.keyPressed.emit(event)

    def setData(self, entries):
        self.entries = entries
        self.setRowCount(len(self.entries))
        self.setColumnCount(2)

        counter = 0
        for entry in self.entries:
            newItem = QtWidgets.QTableWidgetItem(entry['displayName'])
            self.setItem(counter, 0, newItem)

            newItem = QtWidgets.QTableWidgetItem(entry['number'])
            self.setItem(counter, 1, newItem)

            counter += 1

        self.setHorizontalHeaderLabels([
            translate('Name'),
            translate('Number'),
        ])
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        self.clearSelection()

class CallHistoryTable(QtWidgets.QTableWidget):
    keyPressed = QtCore.pyqtSignal(QtGui.QKeyEvent)

    def __init__(self, *args):
        self.calls = {}
        self.localPhoneBookEntries = {}
        QtWidgets.QTableWidget.__init__(self, *args)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        #self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QTableWidget.EditTrigger.NoEditTriggers)

    def keyPressEvent(self, event):
        super(CallHistoryTable, self).keyPressEvent(event)
        if(not event.isAutoRepeat()): self.keyPressed.emit(event)

    def getDisplayNameFromLocalPhoneBook(self, number):
        for item in self.localPhoneBookEntries:
            if(item['number'].strip() == number.strip()):
                return item['displayName']

    def setData(self, calls, localPhoneBookEntries):
        if(isDarkMode(self.palette())):
            self.iconIncoming = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/incoming.light.svg')
            self.iconOutgoing = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/outgoing.light.svg')
        else:
            self.iconIncoming = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/incoming.svg')
            self.iconOutgoing = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/outgoing.svg')
        self.iconIncomingMissed = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/incoming.missed.svg')

        self.calls = calls
        self.localPhoneBookEntries = localPhoneBookEntries
        self.setRowCount(len(self.calls))
        self.setColumnCount(4)

        counter = 0
        for call in self.calls:
            color = None

            if(('type' in call and call['type'] == MainWindow.CALL_HISTORY_OUTGOING) or ('incoming' in call and not call['incoming'])):
                newItem = QtWidgets.QTableWidgetItem()
                newItem.setIcon(self.iconOutgoing)
            elif(('type' in call and call['type'] == MainWindow.CALL_HISTORY_INCOMING) or ('incoming' in call and call['incoming'])):
                newItem = QtWidgets.QTableWidgetItem()
                newItem.setIcon(self.iconIncoming)
            elif('type' in call and call['type'] == MainWindow.CALL_HISTORY_INCOMING_MISSED):
                color = QtGui.QColor(250, 20, 20)
                newItem = QtWidgets.QTableWidgetItem()
                newItem.setIcon(self.iconIncomingMissed)
                if(color != None): newItem.setForeground(QtGui.QBrush(color))
            self.setItem(counter, 0, newItem)

            displayName = call['displayName'] if call.get('displayName','')!=call.get('number','') else ''
            if(not displayName): displayName = self.getDisplayNameFromLocalPhoneBook(call.get('number',''))
            if(not displayName): displayName = call.get('number', '?')
            newItem = QtWidgets.QTableWidgetItem(displayName)
            if(color != None): newItem.setForeground(QtGui.QBrush(color))
            self.setItem(counter, 1, newItem)

            newItem = QtWidgets.QTableWidgetItem(call.get('date', '?'))
            if(color != None): newItem.setForeground(QtGui.QBrush(color))
            self.setItem(counter, 2, newItem)

            newItem = QtWidgets.QTableWidgetItem(call.get('subject', ''))
            if(color != None): newItem.setForeground(QtGui.QBrush(color))
            self.setItem(counter, 3, newItem)

            counter += 1

        self.setHorizontalHeaderLabels([
            '', # direction column (shows icon of incoming or outgoing call)
            translate('Remote Party'),
            translate('Date'),
            translate('Subject')
        ])
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        self.clearSelection()

class PhoneBookSearchModel(QtGui.QStandardItemModel):
    finished = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super(PhoneBookSearchModel, self).__init__(parent)
        self.uds = UdsWrapper()
        self.finished.connect(self.processPhoneBookResult)

    @QtCore.pyqtSlot(str)
    def search(self, text):
        if(not text): return
        self.uds.queryPhoneBook(text, self.finished)
        self.loop = QtCore.QEventLoop()
        self.loop.exec_()

    def processPhoneBookResult(self, entries):
        self.clear()
        for entry in entries:
            if(entry['phoneNumber'] != ''):
                item = QtGui.QStandardItem(entry['displayName']+' ('+entry['phoneNumber']+')')
                item.number = entry['phoneNumber']
                self.appendRow(item)
            if(entry['homeNumber'] != ''):
                item = QtGui.QStandardItem(entry['displayName']+' ('+entry['homeNumber']+')')
                item.number = entry['homeNumber']
                self.appendRow(item)
            if(entry['mobileNumber'] != ''):
                item = QtGui.QStandardItem(entry['displayName']+' ('+entry['mobileNumber']+')')
                item.number = entry['mobileNumber']
                self.appendRow(item)
        self.loop.quit()

class PhoneBookSearchCompleter(QtWidgets.QCompleter):
    def __init__(self, mainWindow, *args, **kwargs):
        self.mainWindow = mainWindow
        super(PhoneBookSearchCompleter, self).__init__(*args, **kwargs)
        self.setCompletionMode(QtWidgets.QCompleter.UnfilteredPopupCompletion)
        #self.activated[QtCore.QModelIndex].connect(self.applySuggestion)

    def splitPath(self, path):
        self.model().search(path)
        return super(PhoneBookSearchCompleter, self).splitPath(path)

    def pathFromIndex(self, index):
        return self.model().item(index.row(), 0).number

    #def applySuggestion(self, index):
    #    self.mainWindow.txtCall.setText(self.model().item(index.row(), 0).number)

class IpcHandler(watchdog.events.FileSystemEventHandler):
    IPC_FILE = CFG_DIR + '/ipc.lock'

    evtIpcMessageReceived = None

    def on_modified(self, event):
        if(event.src_path != IpcHandler.IPC_FILE): return
        with open(IpcHandler.IPC_FILE, 'r') as f:
            number = f.read().strip()
            if(number != ''): self.evtIpcMessageReceived.emit(number)

class MainWindow(QtWidgets.QMainWindow):
    user = None
    devices = None
    config = {} # misc settings
    debug = False
    failFlag = False
    registrationFeedbackFlag = False

    sipHandler = None
    registerRenevalInterval = None

    trayIcon = None
    incomingCallWindow = None
    outgoingCallWindow = None
    callWindow = None

    evtRegistrationStatusChanged = QtCore.pyqtSignal(int, str)
    evtIncomingCall = QtCore.pyqtSignal(int)
    evtOutgoingCall = QtCore.pyqtSignal(int, str)
    evtCallClosed = QtCore.pyqtSignal()
    evtIpcMessageReceived = QtCore.pyqtSignal(str)

    def __init__(self, settings, presetNumber=None, debug=False, *args, **kwargs):
        self.debug = debug
        self.user = settings['user']
        self.devices = settings['devices']
        self.ringtonePlayer = None
        self.ringtoneOutputDeviceNames = settings.get('ringtone-devices', [])
        self.inputDeviceName = settings.get('input-device', None)
        self.outputDeviceName = settings.get('output-device', None)
        self.defaultRingtoneFile = os.path.dirname(os.path.realpath(__file__))+'/assets/ringelingeling.wav'
        self.ringtoneFile = settings.get('ringtone', self.defaultRingtoneFile)
        super(MainWindow, self).__init__(*args, **kwargs)
        self.callHistory = loadCallHistory(True)
        self.phoneBook = loadPhoneBook(True)
        self.status = self.STATUS_FAIL

        # icons
        if(isDarkMode(self.palette())):
            self.iconCall = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/outgoing.light.svg')
            self.iconAdd = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/add.light.svg')
            self.iconEdit = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/edit.light.svg')
            self.iconAddBook = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/add-book.light.svg')
            self.iconDelete = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/delete.light.svg')
        else:
            self.iconCall = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/outgoing.svg')
            self.iconAdd = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/add.svg')
            self.iconEdit = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/edit.svg')
            self.iconAddBook = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/add-book.svg')
            self.iconDelete = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/delete.svg')

        self.iconApplication = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/tux-phone.svg')
        self.iconTrayNormal = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/phone.svg')
        self.iconTrayNotification = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/phone-notification.svg')
        self.iconTrayFail = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/phone-fail.svg')

        # window layout
        grid = QtWidgets.QGridLayout()

        self.lblPhone = QtWidgets.QLabel(translate('Line'))
        grid.addWidget(self.lblPhone, 0, 0)
        self.sltPhone = QtWidgets.QComboBox()
        self.buildPhoneSelector()
        grid.addWidget(self.sltPhone, 0, 1)
        self.lblRegistrationStatus = QtWidgets.QLabel('...')
        grid.addWidget(self.lblRegistrationStatus, 0, 2)

        self.lblCall = QtWidgets.QLabel(translate('Call'))
        grid.addWidget(self.lblCall, 1, 0)
        self.txtCall = QtWidgets.QLineEdit()
        if(presetNumber): self.txtCall.setText(presetNumber)
        self.txtCall.setPlaceholderText(translate('Phone Number (type to search global address book)'))
        self.txtCall.installEventFilter(self)
        grid.addWidget(self.txtCall, 1, 1)
        self.btnCall = QtWidgets.QPushButton()
        self.btnCall.setIcon(self.iconCall)
        self.btnCall.setToolTip(translate('Start Call'))
        self.btnCall.installEventFilter(self)
        self.btnCall.clicked.connect(self.clickCall)
        grid.addWidget(self.btnCall, 1, 2)

        gridCalls = QtWidgets.QGridLayout()
        self.tblCalls = CallHistoryTable()
        self.tblCalls.setData(self.callHistory, self.phoneBook)
        self.tblCalls.keyPressed.connect(self.tblCallsKeyPressed)
        self.tblCalls.doubleClicked.connect(self.recallHistory)
        gridCalls.addWidget(self.tblCalls, 0, 0)
        buttonBox = QtWidgets.QVBoxLayout()
        btnAddCallsEntryToPhoneBook = QtWidgets.QPushButton()
        btnAddCallsEntryToPhoneBook.setIcon(self.iconAddBook)
        btnAddCallsEntryToPhoneBook.setToolTip(translate('Add To Phone Book'))
        btnAddCallsEntryToPhoneBook.clicked.connect(self.addCallsEntryToPhoneBook)
        buttonBox.addWidget(btnAddCallsEntryToPhoneBook)
        btnDelCallsEntry = QtWidgets.QPushButton()
        btnDelCallsEntry.setIcon(self.iconDelete)
        btnDelCallsEntry.setToolTip(translate('Remove'))
        btnDelCallsEntry.clicked.connect(self.delCallsEntry)
        buttonBox.addWidget(btnDelCallsEntry)
        buttonBox.addStretch(1)
        gridCalls.addLayout(buttonBox, 0, 1)
        gridCalls.setContentsMargins(0, 0, 0, 0)
        widgetCalls = QtWidgets.QWidget()
        widgetCalls.setLayout(gridCalls)

        gridPhoneBook = QtWidgets.QGridLayout()
        self.tblPhoneBook = PhoneBookTable()
        self.tblPhoneBook.setData(self.phoneBook)
        self.tblPhoneBook.keyPressed.connect(self.tblPhoneBookKeyPressed)
        self.tblPhoneBook.doubleClicked.connect(self.callPhoneBook)
        gridPhoneBook.addWidget(self.tblPhoneBook, 0, 0)
        buttonBox = QtWidgets.QVBoxLayout()
        btnAddPhoneBookEntry = QtWidgets.QPushButton()
        btnAddPhoneBookEntry.setIcon(self.iconAdd)
        btnAddPhoneBookEntry.setToolTip(translate('Add'))
        btnAddPhoneBookEntry.clicked.connect(self.addPhoneBookEntry)
        buttonBox.addWidget(btnAddPhoneBookEntry)
        btnEditPhoneBookEntry = QtWidgets.QPushButton()
        btnEditPhoneBookEntry.setIcon(self.iconEdit)
        btnEditPhoneBookEntry.setToolTip(translate('Edit'))
        btnEditPhoneBookEntry.clicked.connect(self.editPhoneBookEntry)
        buttonBox.addWidget(btnEditPhoneBookEntry)
        btnDelPhoneBookEntry = QtWidgets.QPushButton()
        btnDelPhoneBookEntry.setIcon(self.iconDelete)
        btnDelPhoneBookEntry.setToolTip(translate('Remove'))
        btnDelPhoneBookEntry.clicked.connect(self.delPhoneBookEntry)
        buttonBox.addWidget(btnDelPhoneBookEntry)
        buttonBox.addStretch(1)
        gridPhoneBook.addLayout(buttonBox, 0, 1)
        gridPhoneBook.setContentsMargins(0, 0, 0, 0)
        widgetPhoneBook = QtWidgets.QWidget()
        widgetPhoneBook.setLayout(gridPhoneBook)

        tabHistoryPhoneBook = QtWidgets.QTabWidget()
        tabHistoryPhoneBook.addTab(widgetCalls, translate('Call History'))
        tabHistoryPhoneBook.addTab(widgetPhoneBook, translate('Local Address Book'))
        grid.addWidget(tabHistoryPhoneBook, 2, 0, 1, 3)

        widget = QtWidgets.QWidget(self)
        widget.setLayout(grid)
        self.setCentralWidget(widget)

        # register event handler
        self.evtRegistrationStatusChanged.connect(self.evtRegistrationStatusChangedHandler)
        self.evtIncomingCall.connect(self.evtIncomingCallHandler)
        self.evtOutgoingCall.connect(self.evtOutgoingCallHandler)
        self.evtCallClosed.connect(self.evtCallClosedHandler)
        self.evtIpcMessageReceived.connect(self.evtIpcMessageReceivedHandler)

        # init QCompleter for phone book search
        try:
            self.phoneBookSearchCompleterModel = PhoneBookSearchModel(self)
            phoneBookSearchCompleter = PhoneBookSearchCompleter(self, caseSensitivity=QtCore.Qt.CaseInsensitive)
            phoneBookSearchCompleter.setModel(self.phoneBookSearchCompleterModel)
            self.txtCall.setCompleter(phoneBookSearchCompleter)
        except Exception:
            traceback.format_exc()

        # Menubar
        mainMenu = self.menuBar()

        # File Menu
        fileMenu = mainMenu.addMenu(translate('&File'))

        registerAction = QtWidgets.QAction(translate('&Register'), self)
        registerAction.setShortcut('F5')
        registerAction.triggered.connect(self.clickRegister)
        fileMenu.addAction(registerAction)
        refreshConfigAction = QtWidgets.QAction(translate('Refresh &Config'), self)
        refreshConfigAction.triggered.connect(self.clickRefreshConfig)
        fileMenu.addAction(refreshConfigAction)

        fileMenu.addSeparator()
        callAction = QtWidgets.QAction(translate('Start &Call'), self)
        callAction.setShortcut('F2')
        callAction.triggered.connect(self.clickCall)
        fileMenu.addAction(callAction)
        callWithSubjectAction = QtWidgets.QAction(translate('Start Call With &Subject'), self)
        callWithSubjectAction.setShortcut('F3')
        callWithSubjectAction.triggered.connect(self.clickCallWithSubject)
        fileMenu.addAction(callWithSubjectAction)

        fileMenu.addSeparator()
        quitAction = QtWidgets.QAction(translate('&Quit'), self)
        quitAction.setShortcut('Ctrl+Q')
        quitAction.triggered.connect(self.clickQuit)
        fileMenu.addAction(quitAction)

        # Audio Menu
        audioMenu = mainMenu.addMenu(translate('&Audio'))
        inputDevicesMenu = audioMenu.addMenu(translate('&Input Device'))
        inputDevicesMenu.setEnabled(False)
        outputDevicesMenu = audioMenu.addMenu(translate('&Output Device'))
        outputDevicesMenu.setEnabled(False)
        audioMenu.addSeparator()
        ringtoneDevicesMenu = audioMenu.addMenu(translate('&Ringtone Devices'))
        ringtoneDevicesMenu.setEnabled(False)
        chooseRingtoneAction = QtWidgets.QAction(translate('&Choose Default Ringtone'), self)
        chooseRingtoneAction.triggered.connect(self.clickChooseRingtone)
        audioMenu.addAction(chooseRingtoneAction)

        with ignoreStderr(): audio = pyaudio.PyAudio()
        info = audio.get_host_api_info_by_index(0)
        inputDevicesGroup = QtWidgets.QActionGroup(self)
        inputDevicesGroup.setExclusive(True)
        outputDevicesGroup = QtWidgets.QActionGroup(self)
        outputDevicesGroup.setExclusive(True)
        for i in range(0, info.get('deviceCount')):
            if(audio.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                deviceName = re.sub('[\(\[].*?[\)\]]', '', audio.get_device_info_by_host_api_device_index(0, i).get('name')).strip()
                inputDeviceAction = inputDevicesGroup.addAction(QtWidgets.QAction(deviceName, self, checkable=True))
                if(deviceName == self.inputDeviceName): inputDeviceAction.setChecked(True)
                inputDeviceAction.triggered.connect(partial(self.clickSetInput, deviceName, inputDeviceAction))
                inputDevicesMenu.addAction(inputDeviceAction)
            if(audio.get_device_info_by_host_api_device_index(0, i).get('maxOutputChannels')) > 0:
                deviceName = re.sub('[\(\[].*?[\)\]]', '', audio.get_device_info_by_host_api_device_index(0, i).get('name')).strip()
                outputDeviceAction = outputDevicesGroup.addAction(QtWidgets.QAction(deviceName, outputDevicesGroup, checkable=True))
                if(deviceName == self.outputDeviceName): outputDeviceAction.setChecked(True)
                outputDeviceAction.triggered.connect(partial(self.clickSetOutput, deviceName, outputDeviceAction))
                outputDevicesMenu.addAction(outputDeviceAction)
                ringtoneDeviceAction = QtWidgets.QAction(deviceName, self, checkable=True)
                if(deviceName in self.ringtoneOutputDeviceNames): ringtoneDeviceAction.setChecked(True)
                ringtoneDeviceAction.triggered.connect(partial(self.clickSetRingtoneOutput, deviceName, ringtoneDeviceAction))
                ringtoneDevicesMenu.addAction(ringtoneDeviceAction)

        # Help Menu
        helpMenu = mainMenu.addMenu(translate('&Help'))

        aboutAction = QtWidgets.QAction(translate('&About'), self)
        aboutAction.setShortcut('F1')
        aboutAction.triggered.connect(self.clickAboutDialog)
        helpMenu.addAction(aboutAction)

        # window properties
        self.setWindowTitle(__title__)
        self.resize(440, 290)
        self.txtCall.setFocus()
        self.setWindowIcon(self.iconApplication)

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        # tray icon
        self.trayIcon = SystemTrayIcon(QtGui.QIcon(), self)
        self.setTrayIcon(self.STATUS_FAIL)
        self.trayIcon.show()

        # init IPC
        try:
            self.ipcLock = filelock.FileLock(IpcHandler.IPC_FILE, timeout=0)
            self.ipcLock.acquire()
            self.ipcHandler = IpcHandler()
            self.ipcHandler.evtIpcMessageReceived = self.evtIpcMessageReceived
            self.ipcObserver = watchdog.observers.Observer()
            self.ipcObserver.schedule(self.ipcHandler, path=IpcHandler.IPC_FILE, recursive=False)
            self.ipcObserver.start()
            if(self.debug): print(':: IPC Lock acquired')
        except Exception as e: print(e)

        # start SIP registration
        self.initSipSession(self.sltPhone.currentIndex())

    def buildPhoneSelector(self):
        # do not fire index changed events when building the list
        try:
            self.sltPhone.currentIndexChanged.disconnect(self.sltPhoneChanged)
        except Exception: pass

        phoneIndex = 0
        self.sltPhone.clear()
        for device in self.devices:
            self.sltPhone.addItem(str(device['number']))
            if('default' in device and device['default']):
                self.sltPhone.setCurrentIndex(phoneIndex)
            phoneIndex += 1
        self.sltPhone.currentIndexChanged.connect(self.sltPhoneChanged)

    def closeEvent(self, event):
        saveSettings({
            'user': self.user,
            'devices': self.devices,
            'ringtone': self.ringtoneFile,
            'ringtone-devices': self.ringtoneOutputDeviceNames,
            'output-device': self.outputDeviceName,
            'input-device': self.inputDeviceName,
        })
        if(self.debug):
            QtCore.QCoreApplication.exit()
        else:
            event.ignore()
            self.hide()

    def clickQuit(self, e):
        self.close()
        QtCore.QCoreApplication.exit()

    def clickAboutDialog(self, e):
        dlg = AboutWindow(self)
        dlg.exec_()

    def evtIpcMessageReceivedHandler(self, message):
        if(message.strip() != ''):
            self.show()
            if(not message.strip().startswith('.')):
                self.txtCall.setText(message)
                self.txtCall.selectAll()
                self.txtCall.setFocus()

    def eventFilter(self, source, event):
        if(event.type() == QtCore.QEvent.KeyPress
        and (source is self.txtCall or source is self.btnCall)
        and event.key() == QtCore.Qt.Key_Return):
            if(event.modifiers() & QtCore.Qt.CTRL):
                self.clickCallWithSubject(None)
            else:
                self.clickCall(None)
        return super(MainWindow, self).eventFilter(source, event)

    def clickChooseRingtone(self, e):
        fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, translate('Ringtone File'), self.ringtoneFile, 'WAV Audio Files (*.wav);;')
        if fileName: self.ringtoneFile = fileName

    def clickSetInput(self, deviceName, menuItem, e):
        self.inputDeviceName = deviceName
        self.sipHandler.inputDeviceName = deviceName
    def clickSetOutput(self, deviceName, menuItem, e):
        self.outputDeviceName = deviceName
        self.sipHandler.outputDeviceName = deviceName
    def clickSetRingtoneOutput(self, deviceName, menuItem, e):
        if(menuItem.isChecked()):
            if(deviceName not in self.ringtoneOutputDeviceNames):
                self.ringtoneOutputDeviceNames.append(deviceName)
        else:
            self.ringtoneOutputDeviceNames.remove(deviceName)

    def recallHistory(self, e, withSubject=False):
        for row in sorted(self.tblCalls.selectionModel().selectedRows()):
            historyItem = self.callHistory[row.row()]
            if('number' in historyItem and historyItem['number'].strip() != ''):
                self.call(historyItem['number'], withSubject)
                break
    def callPhoneBook(self, e, withSubject=False):
        for row in sorted(self.tblPhoneBook.selectionModel().selectedRows()):
            addressBookEntry = self.phoneBook[row.row()]
            if('number' in addressBookEntry and addressBookEntry['number'].strip() != ''):
                self.call(addressBookEntry['number'], withSubject)
                break
    def tblCallsKeyPressed(self, keyEvent):
        if(keyEvent.key() == QtCore.Qt.Key_Delete):
            self.delCallsEntry(None)
        if(keyEvent.key() == QtCore.Qt.Key_Return):
            self.recallHistory(None, (keyEvent.modifiers() & QtCore.Qt.CTRL))
    def tblPhoneBookKeyPressed(self, keyEvent):
        if(keyEvent.key() == QtCore.Qt.Key_Delete):
            self.delPhoneBookEntry(None)
        if(keyEvent.key() == QtCore.Qt.Key_Return):
            self.callPhoneBook(None, (keyEvent.modifiers() & QtCore.Qt.CTRL))

    def addPhoneBookEntry(self, e):
        dialog = PhoneBookEntryWindow(self)
        dialog.exec_()
    def editPhoneBookEntry(self, e):
        indices = self.tblPhoneBook.selectionModel().selectedRows()
        for index in sorted(indices):
            dialog = PhoneBookEntryWindow(self, entry=index.row())
            dialog.exec_()
            break
    def addCallsEntryToPhoneBook(self, e):
        indices = self.tblCalls.selectionModel().selectedRows()
        for index in sorted(indices):
            dialog = PhoneBookEntryWindow(self, number=self.callHistory[index.row()]['number'])
            dialog.exec_()
            break
    def delPhoneBookEntry(self, e):
        indices = self.tblPhoneBook.selectionModel().selectedRows()
        if(len(indices) == 0): return

        # confirm
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowTitle(translate('Remove'))
        msg.setText(translate('Are you sure you want to delete %s item(s) from the list?') % str(len(indices)))
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        msg.button(QtWidgets.QMessageBox.Cancel).setText(translate('Cancel'))
        if(msg.exec_() == QtWidgets.QMessageBox.Cancel): return

        for index in sorted(indices, reverse=True):
            del self.phoneBook[index.row()]
        self.tblPhoneBook.setData(self.phoneBook)
        self.tblCalls.setData(self.callHistory, self.phoneBook)
        savePhoneBook(self.phoneBook)
    def delCallsEntry(self, e):
        indices = self.tblCalls.selectionModel().selectedRows()
        if(len(indices) == 0): return

        # confirm
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowTitle(translate('Remove'))
        msg.setText(translate('Are you sure you want to delete %s item(s) from the list?') % str(len(indices)))
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        msg.button(QtWidgets.QMessageBox.Cancel).setText(translate('Cancel'))
        if(msg.exec_() == QtWidgets.QMessageBox.Cancel): return

        for index in sorted(indices, reverse=True):
            del self.callHistory[index.row()]
        self.tblCalls.setData(self.callHistory, self.phoneBook)
        saveCallHistory(self.callHistory)

    CALL_HISTORY_OUTGOING = 1
    CALL_HISTORY_INCOMING = 2
    CALL_HISTORY_INCOMING_MISSED = 3
    CALL_HISTORY_MAX_ITEMS = 99
    def addCallToHistory(self, displayName, number, type, subject=''):
        self.callHistory.insert(0, {'date':datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'displayName':displayName, 'number':number, 'type':type, 'subject':subject})
        self.callHistory = self.callHistory[:MainWindow.CALL_HISTORY_MAX_ITEMS]
        self.tblCalls.setData(self.callHistory, self.phoneBook)
        saveCallHistory(self.callHistory)

    STATUS_OK = 0
    STATUS_NOTIFY = 1
    STATUS_FAIL = 2
    def setTrayIcon(self, newStatus, force=False):
        newIcon = None
        if(newStatus == self.STATUS_OK):
            if(force or self.status != self.STATUS_NOTIFY): # overwrite STATUS_NOTIFY only if forced
                newIcon = self.iconTrayNormal
            else:
                return # 's bleibt so wie's is!!
        elif(newStatus == self.STATUS_NOTIFY):
            newIcon = self.iconTrayNotification
        else:
            newIcon = self.iconTrayFail
        self.trayIcon.setIcon(newIcon)
        self.status = newStatus

    def clickRegister(self, e):
        self.registrationFeedbackFlag = True
        self.initSipSession(self.sltPhone.currentIndex())

    def clickRefreshConfig(self, e):
        window = LoginWindow(mainWindow=self, debug=self.debug)
        if window.exec_() == QtWidgets.QDialog.Accepted:
            self.buildPhoneSelector()
            self.registrationFeedbackFlag = True
            self.initSipSession(self.sltPhone.currentIndex())

    def sltPhoneChanged(self, sender):
        self.initSipSession(self.sltPhone.currentIndex())

    def initSipSession(self, deviceIndex, force=False):
        try:
            # stop previous SIP(S) session
            if(self.sipHandler):
                self.sipHandler.stop()

            # set current selection as default device for next startup
            counter = 0
            for dev in self.devices:
                dev['default'] = (counter == deviceIndex)
                counter += 1

            # get selected device details
            device = self.devices[deviceIndex]
            port = device['callManagers'][0]['sipPort']
            certHash = device['certHash'].lower() if device['certHash'] else None

            # try to get a client certificate via CAPF on startup
            if('capfServers' in device):
                for capfServer in device['capfServers']:
                    try:
                        targetCertFile = CLIENT_CERTS_DIR+'/'+device['name']+'_'+str(time.time())+'.pem'
                        capf = CapfWrapper(capfServer['address'], port=int(capfServer['port']), debug=self.debug)
                        capf.requestCertificate(device['name'], targetCertFile)

                        # get new cert hash
                        with open(targetCertFile, 'rb') as f:
                            cert = load_pem_x509_certificate(f.read())
                            certHash = cert.fingerprint(hashes.MD5()).hex().lower()
                            self.devices[deviceIndex]['certHash'] = certHash
                            if(self.debug): print(':: CAPF succeeded', certHash, targetCertFile)

                        break # break the loop and exit if cert was issued successfully
                    except Exception as e:
                        print(':: CAPF error:', capfServer, e) # ignore timeout and try next server

            # set up SIPS encryption if configured
            tlsOptions = None
            if(device['deviceSecurityMode'] == '2' or device['deviceSecurityMode'] == '3'):
                port = device['callManagers'][0]['sipsPort']

                # check client cert hash
                if(not certHash):
                    raise Exception('deviceSecurityMode is enabled but no certHash given?!')

                # find/load existing corresponding client cert
                for fileName in os.listdir(CLIENT_CERTS_DIR):
                    filePath = CLIENT_CERTS_DIR+'/'+fileName
                    if(not os.path.isfile(filePath)): continue
                    with open(filePath, 'rb') as f:
                        try:
                            cert = load_pem_x509_certificate(f.read())
                            if(cert.fingerprint(hashes.MD5()).hex().lower() == certHash):
                                tlsOptions = {'client-cert':filePath, 'client-key':None} # key should be included inside cert file
                            elif(self.debug):
                                print(f':: fingerprint of {filePath} does not match')
                        except Exception as e:
                            print(f':: unable to read certificate {filePath} ({e})')
                    if(tlsOptions): break # break if correct certificate was found
                if(not tlsOptions):
                    raise Exception(f'Unable to find a certificate with MD5 hash {certHash} in {CLIENT_CERTS_DIR}')

                # load trusted server certs
                tlsOptions['server-cert'] = []
                if(os.path.isdir(SERVER_CERTS_DIR)):
                    for fileName in os.listdir(SERVER_CERTS_DIR):
                        if(self.debug): print(f':: trusting server cert {fileName}')
                        tlsOptions['server-cert'].append(SERVER_CERTS_DIR+'/'+fileName)

            # start SIP(S) session
            self.sipHandler = SipHandler(
                device['callManagers'][0]['address'], port, tlsOptions,
                self.user['displayName'], device['number'], device['deviceName'], device['contact'],
                debug=self.debug
            )
            self.sipHandler.inputDeviceName = self.inputDeviceName
            self.sipHandler.outputDeviceName = self.outputDeviceName
            self.sipHandler.evtRegistrationStatusChanged = self.evtRegistrationStatusChanged
            self.sipHandler.evtIncomingCall = self.evtIncomingCall
            self.sipHandler.evtOutgoingCall = self.evtOutgoingCall
            self.sipHandler.evtCallClosed = self.evtCallClosed
            self.sipHandler.start()
            self.registerSipSession(force)
        except Exception as e:
            traceback.print_exc()
            self.evtRegistrationStatusChanged.emit(SipHandler.REGISTRATION_FAILED, str(e))

    def registerSipSession(self, force=False):
        self.sipHandler.register(force)

    def evtRegistrationStatusChangedHandler(self, status, text):
        self.lblRegistrationStatus.setToolTip(text)
        if(status == SipHandler.REGISTRATION_REGISTERED):
            self.lblRegistrationStatus.setText(translate('OK!'))
            self.setTrayIcon(self.STATUS_OK)
            self.failFlag = False
            if(self.registrationFeedbackFlag):
                showErrorDialog(translate('Success'), translate('SIP registration successful'), icon=QtWidgets.QMessageBox.Information)
                self.registrationFeedbackFlag = False

        elif(status == SipHandler.REGISTRATION_INACTIVE):
            self.lblRegistrationStatus.setText('...')
            self.setTrayIcon(self.STATUS_FAIL)

        else:
            self.lblRegistrationStatus.setText(translate('FAILED!'))
            self.setTrayIcon(self.STATUS_FAIL)

            # show option to take over other sessions
            if(status == SipHandler.REGISTRATION_ALREADY_ACTIVE):
                msg = QtWidgets.QMessageBox()
                msg.setIcon(QtWidgets.QMessageBox.Warning)
                msg.setWindowTitle(translate('Force Registration?'))
                msg.setText(translate('Your phone is already connected with another softphone instance. Do you want to disconnect the other softphone?'))
                msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                if(msg.exec_() == QtWidgets.QMessageBox.Ok):
                    self.initSipSession(self.sltPhone.currentIndex(), True)
                return

            # it seems to be normal that the server closes the connection from time to time
            # we retry to connect one time - if it fails again, we show a regular error
            if(status == SipHandler.REGISTRATION_CONNECTION_RESET):
                if(not self.failFlag):
                    self.failFlag = True
                    self.initSipSession(self.sltPhone.currentIndex())
                    return

            if('Device security mismatch: expected TLS' in text):
                # CUCM administrator switched the phone to "secure" mode, we need to switch too
                # todo: re-read the configuration from the server instead of switching to fixed number '3'
                print(':: SIP registration failed:', text, ' :: automatically switching to TLS')
                self.devices[self.sltPhone.currentIndex()]['deviceSecurityMode'] = '3'
                self.initSipSession(self.sltPhone.currentIndex())
            else:
                showErrorDialog(translate('Registration Error'), text)

    def evtIncomingCallHandler(self, status):
        if(status == SipHandler.INCOMING_CALL_RINGING):
            callerText = self.getRemotePartyText('From_parsed_text')
            subjectText = (translate('Subject')+': '+self.getSubjectText()+"\n") if self.getSubjectText() else ''
            diversionText = (translate('Forwarded for')+': '+self.getDiversionText()+"\n") if self.getDiversionText() else ''
            self.incomingCallWindow = IncomingCallWindow(callerText, (subjectText+diversionText).strip())
            try:
                self.startRingtone(self.sipHandler.currentCall['number'])
            except Exception as e:
                print('!!! ringtone error: '+str(e))
            self.incomingCallWindow.finished.connect(self.incomingCallWindowFinished)
            self.incomingCallWindow.show()

        elif(status == SipHandler.INCOMING_CALL_CANCELED):
            self.closeIncomingCallWindow()
            self.setTrayIcon(self.STATUS_NOTIFY)

        elif(status == SipHandler.INCOMING_CALL_ACCEPTED):
            self.addCallToHistory(self.sipHandler.currentCall['headers']['From_parsed_text'], self.sipHandler.currentCall['headers']['From_parsed_number'], MainWindow.CALL_HISTORY_INCOMING, self.getSubjectText())
            self.closeIncomingCallWindow()
            self.callWindow = CallWindow(self.getRemotePartyText('From_parsed_text'), False)
            self.callWindow.finished.connect(self.callWindowFinished)
            self.callWindow.show()

        else:
            showErrorDialog(translate('Incoming Call Failed'), str(status))

    def incomingCallWindowFinished(self, status):
        self.closeIncomingCallWindow()
        if(status == QtWidgets.QDialog.Accepted):
            self.sipHandler.acceptCall()
        else:
            self.sipHandler.rejectCall()
            self.addCallToHistory(self.sipHandler.currentCall['headers']['From_parsed_text'], self.sipHandler.currentCall['headers']['From_parsed_number'], MainWindow.CALL_HISTORY_INCOMING_MISSED, self.getSubjectText())

    def closeIncomingCallWindow(self):
        if(self.ringtonePlayer != None):
            self.ringtonePlayer.stop()
            self.ringtonePlayer = None
        if(self.incomingCallWindow != None):
            self.incomingCallWindow.close()

    def call(self, number, askForCallSubject=False):
        self.currentOutgoingCallSubject = ''
        subject = None
        if(askForCallSubject):
            dialog = QtWidgets.QInputDialog(self)
            dialog.setWindowTitle(translate('Subject'))
            dialog.setLabelText(translate('Please enter a call subject.')+"\n"+translate('Please note that only compatible clients will display it to the remote party.'))
            dialog.setCancelButtonText(translate('Cancel'))
            if(dialog.exec_() == QtWidgets.QDialog.Accepted):
                subject = dialog.textValue()
                self.currentOutgoingCallSubject = subject
            else:
                return
        self.sipHandler.call(number, subject)

    def clickCall(self, sender):
        number = self.txtCall.text().strip()
        if(number == ''): return
        self.call(number)
    def clickCallWithSubject(self, sender):
        number = self.txtCall.text().strip()
        if(number == ''): return
        self.call(number, True)

    def evtOutgoingCallHandler(self, status, text):
        if(status == SipHandler.OUTGOING_CALL_TRYING):
            self.outgoingCallWindow = OutgoingCallWindow(self.getRemotePartyText('To_parsed_text'))
            self.outgoingCallWindow.finished.connect(self.outgoingCallWindowFinished)
            self.outgoingCallWindow.show()

        elif(status == SipHandler.OUTGOING_CALL_BUSY):
            self.closeOutgoingCallWindow()
            self.sipHandler.cancelCall()
            showErrorDialog(translate('Call Failed'), translate('This line is currently busy'), '', icon=QtWidgets.QMessageBox.Warning)

        elif(status == SipHandler.OUTGOING_CALL_RINGING):
            self.outgoingCallWindow.lblTo.setText(self.getRemotePartyText('To_parsed_text'))
            self.addCallToHistory(self.sipHandler.currentCall['headers']['To_parsed_text'], self.sipHandler.currentCall['headers']['To_parsed_number'], MainWindow.CALL_HISTORY_OUTGOING, self.currentOutgoingCallSubject)
            self.startRingtone(self.sipHandler.currentCall['number'])

        elif(status == SipHandler.OUTGOING_CALL_ACCEPTED):
            self.closeOutgoingCallWindow()
            self.callWindow = CallWindow(self.getRemotePartyText('To_parsed_text'), True)
            self.callWindow.finished.connect(self.callWindowFinished)
            self.callWindow.show()

        else:
            self.closeOutgoingCallWindow()
            showErrorDialog(translate('Outgoing Call Failed'), str(text))

    def outgoingCallWindowFinished(self, status):
        self.closeOutgoingCallWindow()
        if status == QtWidgets.QDialog.Accepted:
            self.sipHandler.cancelCall()

    def closeOutgoingCallWindow(self):
        if(self.outgoingCallWindow != None):
            self.outgoingCallWindow.close()
        if(self.ringtonePlayer != None):
            self.ringtonePlayer.stop()
            self.ringtonePlayer = None

    def callWindowFinished(self, status):
        if status == QtWidgets.QDialog.Rejected:
            self.sipHandler.closeCall(self.callWindow.isOutgoingCall)

    def evtCallClosedHandler(self):
        self.callWindow.close()

    def getRemotePartyText(self, headerField):
        remotePartyText = self.sipHandler.currentCall.get('headers',{}).get(headerField,'')
        if(remotePartyText and remotePartyText != self.sipHandler.currentCall['number']):
            return remotePartyText

        phoneBookEntry = self.getLocalPhoneBookEntry(self.sipHandler.currentCall['number'])
        if(phoneBookEntry and phoneBookEntry.get('displayName','')):
            return phoneBookEntry['displayName']
        else:
            return self.sipHandler.currentCall['number']

    def getSubjectText(self):
        subjectText = ''
        if('Subject' in self.sipHandler.currentCall['headers']):
            subjectText = self.sipHandler.currentCall['headers']['Subject']
        if('Contact' in self.sipHandler.currentCall['headers']):
            for item in self.sipHandler.currentCall['headers']['Contact'].split(';'):
                keyValue = item.split('=')
                if(len(keyValue) > 1 and keyValue[0] == 'subject'):
                    subjectText = urllib.parse.unquote_plus(keyValue[1])
        return subjectText
    def getDiversionText(self):
        if('Diversion' in self.sipHandler.currentCall['headers']):
            return self.sipHandler.currentCall['headers']['Diversion'].split(';')[0]
        return ''

    def getLocalPhoneBookEntry(self, number):
        if(not number): return None
        for entry in self.phoneBook:
            if(entry.get('number','').strip().replace('+', '00') == number.strip().replace('+', '00')):
                return entry

    def startRingtone(self, number):
        soundFilePath = self.defaultRingtoneFile
        if(os.path.isfile(self.ringtoneFile)):
            soundFilePath = self.ringtoneFile
        phoneBookEntry = self.getLocalPhoneBookEntry(number)
        if(phoneBookEntry and os.path.isfile(phoneBookEntry.get('ringtone',''))):
            soundFilePath = phoneBookEntry['ringtone']

        self.ringtonePlayer = AudioPlayer(
            soundFilePath,
            self.sipHandler.audio,
            self.ringtoneOutputDeviceNames
        )
        self.ringtonePlayer.start()

def loadSettings(suppressError=False):
    try:
        os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
        os.makedirs(CFG_DIR+'/client-certs', mode=0o700, exist_ok=True)
        os.makedirs(CFG_DIR+'/server-certs', mode=0o700, exist_ok=True)
        with open(CFG_PATH) as f:
            return json.load(f)
    except Exception as e:
        if(not suppressError): showErrorDialog(translate('Error loading settings file'), str(e))
def saveSettings(settings):
    try:
        os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
        with open(CFG_PATH, 'w') as json_file:
            json.dump(settings, json_file, indent=4)
    except Exception as e:
        showErrorDialog(translate('Error saving settings file'), str(e))

def loadCallHistory(suppressError=False):
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except Exception as e:
        if(not suppressError): showErrorDialog(translate('Error loading history file'), str(e))
        return []
def saveCallHistory(settings):
    try:
        os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
        with open(HISTORY_PATH, 'w') as json_file:
            json.dump(settings, json_file, indent=4)
    except Exception as e:
        showErrorDialog(translate('Error saving history file'), str(e))

def loadPhoneBook(suppressError=False):
    try:
        with open(PHONEBOOK_PATH) as f:
            return json.load(f)
    except Exception as e:
        if(not suppressError): showErrorDialog(translate('Error loading phone book file'), str(e))
        return []
def savePhoneBook(settings):
    try:
        os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
        with open(PHONEBOOK_PATH, 'w') as json_file:
            json.dump(settings, json_file, indent=4)
    except Exception as e:
        showErrorDialog(translate('Error saving phone book file'), str(e))

# main entry point
def main():
    # parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--hidden', action='store_true', help='Start with tray icon only (for autostart)')
    parser.add_argument('-v', '--debug', action='store_true', help='Print debug output (SIP packet contents etc.)')
    parser.add_argument('-n', '--new-instance', action='store_true', help='Allow starting a new instance for using multiple softphones at once')
    args, unknownargs = parser.parse_known_args()
    presetNumber = None
    if(len(unknownargs) > 0 and unknownargs[0].startswith('tel:')):
        presetNumber = unknownargs[0].strip().split(':')[1].replace('+', '00')

    # load settings, create settings dir if not exists
    settings = loadSettings(True)

    # check if an instance is already running
    otherInstance = False
    try:
        filelock.FileLock(IpcHandler.IPC_FILE, timeout=0).acquire()
        # file could be locked - start a new instance regularly since there is no other instance running
    except filelock._error.Timeout as e:
        # exception is thrown when file is already locked (= an instance is already running)
        if(not args.new_instance):
            if(presetNumber):
                # if a number was given, we forward the number to the other instances MainWindow
                print('An instance is already running. Since a phone number was given as parameter, the number will be forwarded to the other instance and this instance will be closed immediately.')
                with open(IpcHandler.IPC_FILE, 'w') as f: f.write(presetNumber)
            else:
                print('An instance is already running. Opening the main windows of the other instance and closing this instance.')
                with open(IpcHandler.IPC_FILE, 'w') as f: f.write('.')
            sys.exit(0)

    # init QT app
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QT_STYLESHEET)

    # load QT translations
    translator = QtCore.QTranslator(app)
    if getattr(sys, 'frozen', False):
        translator.load(os.path.join(sys._MEIPASS, 'lang/%s.qm' % getdefaultlocale()[0]))
    elif os.path.isdir('lang'):
        translator.load('lang/%s.qm' % getdefaultlocale()[0])
    else:
        translator.load('/usr/share/jabber4linux/lang/%s.qm' % getdefaultlocale()[0])
    app.installTranslator(translator)

    # show main window or login window if no config was found
    if settings != None and 'user' in settings and 'devices' in settings and len(settings['devices']) > 0:
        # directly start main window if login already done
        window = MainWindow(settings, presetNumber=presetNumber, debug=args.debug)
        if not args.hidden: window.show()
        exitCode = app.exec_()

        # cleanup lock file
        if(window.ipcLock.is_locked):
            window.ipcLock.release()
            window.ipcObserver.stop()
            os.remove(IpcHandler.IPC_FILE)

        sys.exit(exitCode)

    else:
        # do not do anything if hidden startup was requested and J4L was not set up yet
        if args.hidden:
            print('Hidden startup requested but no configuration found. Exiting.')
            sys.exit(0)

        # show login window on first normal startup
        window = LoginWindow(debug=args.debug)
        if window.exec_() == QtWidgets.QDialog.Accepted:
            sys.exit(app.exec_())
