#!/usr/bin/env python3

from PyQt5 import QtWidgets
from PyQt5 import QtGui
from PyQt5 import QtCore

from UdsWrapper import UdsWrapper
from SipHandler import SipHandler
from AudioSocket import AudioPlayer
from Tools import ignoreStderr, niceTime

from functools import partial
from pathlib import Path
from threading import Thread, Timer
from locale import getdefaultlocale
import datetime
import pyaudio
import time
import argparse
import json
import re
import socket
import sys, os
import traceback


PRODUCT_NAME = 'Jabber4Linux'
PRODUCT_VERSION = '0.1'

CFG_DIR  = str(Path.home())+'/.config/jabber4linux'
CFG_PATH = CFG_DIR+'/settings.json'
HISTORY_PATH = CFG_DIR+'/history.json'
PHONEBOOK_PATH = CFG_DIR+'/phonebook.json'


def translate(text):
    return QtWidgets.QApplication.translate(PRODUCT_NAME, text)

def showErrorDialog(title, text, additionalText=''):
    print('Error: '+text)
    msg = QtWidgets.QMessageBox()
    msg.setIcon(QtWidgets.QMessageBox.Critical)
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
        labelAppName.setText(PRODUCT_NAME + ' v' + PRODUCT_VERSION)
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
            '<a href="https://github.com/schorschii/Jabber4Linux">https://github.com/schorschii/Jabber4Linux</a>'
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
    def __init__(self, debug=False, *args, **kwargs):
        self.debug = debug
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

    def closeEvent(self, event):
        QtCore.QCoreApplication.exit()

    def login(self):
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

            window = MainWindow({'user':userDetails, 'devices':devices}, debug=self.debug)
            window.show()

            self.accept()
        except Exception as e:
            print(traceback.format_exc())
            showErrorDialog(translate('Login Error'), str(e))

class IncomingCallWindow(QtWidgets.QDialog):
    def __init__(self, callerText, diversionText, *args, **kwargs):
        super(IncomingCallWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Yes|QtWidgets.QDialogButtonBox.No)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Yes).setText(translate('Yes'))
        self.buttonBox.button(QtWidgets.QDialogButtonBox.No).setText(translate('No'))
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QtWidgets.QGridLayout(self)

        self.lblFrom1 = QtWidgets.QLabel(callerText)
        self.layout.addWidget(self.lblFrom1, 0, 0)
        self.lblFrom2 = QtWidgets.QLabel(diversionText)
        self.layout.addWidget(self.lblFrom2, 1, 0)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
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
        self.buttonBox.rejected.connect(self.accept) # accept means: cancel call!

        self.layout = QtWidgets.QGridLayout(self)

        self.lblTo = QtWidgets.QLabel(callerText)
        self.layout.addWidget(self.lblTo, 0, 0)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
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
        self.buttonBox.rejected.connect(self.cancelCall)

        self.layout = QtWidgets.QGridLayout(self)

        self.lblRemotePartyName = QtWidgets.QLabel(remotePartyName)
        self.layout.addWidget(self.lblRemotePartyName, 0, 0)

        self.lblCallTimer = QtWidgets.QLabel(niceTime(0))
        self.layout.addWidget(self.lblCallTimer, 1, 0)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
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
    def __init__(self, mainWindow, *args, **kwargs):
        super(PhoneBookEntryWindow, self).__init__(*args, **kwargs)
        self.mainWindow = mainWindow

        # window layout
        layout = QtWidgets.QGridLayout()

        self.lblCall = QtWidgets.QLabel(translate('Name'))
        layout.addWidget(self.lblCall, 0, 0)
        self.txtName = QtWidgets.QLineEdit()
        layout.addWidget(self.txtName, 0, 1)

        self.lblCall = QtWidgets.QLabel(translate('Number'))
        layout.addWidget(self.lblCall, 1, 0)
        self.txtNumber = QtWidgets.QLineEdit()
        layout.addWidget(self.txtNumber, 1, 1)

        self.lblCall = QtWidgets.QLabel(translate('Ringtone'))
        layout.addWidget(self.lblCall, 2, 0)
        self.txtCustomRingtone = QtWidgets.QLineEdit()
        self.txtCustomRingtone.setPlaceholderText(translate('(optional)'))
        self.txtCustomRingtone.setEnabled(False)
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
        self.setWindowTitle(translate('Add Phone Book Entry'))

    def clickChooseRingtone(self, e):
        fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, translate('Ringtone File'), self.txtCustomRingtone.text(), 'WAV Audio Files (*.wav);;')
        if fileName: self.txtCustomRingtone.setText(fileName)

    def accept(self):
        self.mainWindow.phoneBook.append({
            'displayName': self.txtName.text(),
            'number': self.txtNumber.text(),
            'ringtone': self.txtCustomRingtone.text()
        })
        self.mainWindow.tblPhoneBook.setData(self.mainWindow.phoneBook)
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
        self.setToolTip(PRODUCT_NAME)

    def showMenuOnTrigger(self, reason):
        if(reason == QtWidgets.QSystemTrayIcon.Trigger):
            self.contextMenu().popup(QtGui.QCursor.pos())

    def open(self):
        self.parentWidget.show()
        if(self.parentWidget.status == MainWindow.STATUS_NOTIFY):
            self.parentWidget.setTrayIcon(MainWindow.STATUS_OK)

    def exit(self):
        self.parentWidget.close()
        QtCore.QCoreApplication.exit()

class PhoneBookTable(QtWidgets.QTableWidget):
    keyPressed = QtCore.pyqtSignal(int)

    def __init__(self, *args):
        self.entries = {}
        QtWidgets.QTableWidget.__init__(self, *args)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        #self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QTableWidget.EditTrigger.NoEditTriggers)

    def keyPressEvent(self, event):
        super(PhoneBookTable, self).keyPressEvent(event)
        if(not event.isAutoRepeat()): self.keyPressed.emit(event.key())

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

class CallHistoryTable(QtWidgets.QTableWidget):
    keyPressed = QtCore.pyqtSignal(int)

    def __init__(self, *args):
        self.calls = {}
        QtWidgets.QTableWidget.__init__(self, *args)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        #self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QTableWidget.EditTrigger.NoEditTriggers)

    def keyPressEvent(self, event):
        super(CallHistoryTable, self).keyPressEvent(event)
        if(not event.isAutoRepeat()): self.keyPressed.emit(event.key())

    def setData(self, calls):
        if(isDarkMode(self.palette())):
            self.iconIncoming = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/incoming.light.svg')
            self.iconOutgoing = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/outgoing.light.svg')
        else:
            self.iconIncoming = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/incoming.svg')
            self.iconOutgoing = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/outgoing.svg')
        self.iconIncomingMissed = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/incoming.missed.svg')

        self.calls = calls
        self.setRowCount(len(self.calls))
        self.setColumnCount(3)

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

            newItem = QtWidgets.QTableWidgetItem(call['displayName'])
            if(color != None): newItem.setForeground(QtGui.QBrush(color))
            self.setItem(counter, 1, newItem)

            newItem = QtWidgets.QTableWidgetItem(call['date'])
            if(color != None): newItem.setForeground(QtGui.QBrush(color))
            self.setItem(counter, 2, newItem)

            counter += 1

        self.setHorizontalHeaderLabels([
            '', # direction column (shows icon of incoming or outgoing call)
            translate('Remote Party'),
            translate('Date')
        ])
        self.resizeColumnsToContents()
        self.resizeRowsToContents()

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

class IpcObserver(Thread):
    IPC_PORT = 6666

    evtIpcMessageReceived = None

    def __init__(self, *args, **kwargs):
        super(IpcObserver, self).__init__(*args, **kwargs)
        self.daemon = True
        try:
            self.ipcSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ipcSock.bind(('localhost', self.IPC_PORT))
            self.ipcSock.listen()
        except Exception as e:
            print('Unable to setup IPC socket:', e)
            self.ipcSock = None

    def run(self, *args, **kwargs):
        if(not self.ipcSock): return
        while True:
            conn, address = self.ipcSock.accept()
            with conn:
                data = conn.recv(512)
                if(data): self.evtIpcMessageReceived.emit(data.decode('utf-8').strip())

class MainWindow(QtWidgets.QMainWindow):
    user = None
    devices = None
    config = {} # misc settings
    debug = False

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
        else:
            self.iconCall = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/outgoing.svg')

        self.iconApplication = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/tux-phone.svg')
        self.iconTrayNormal = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/phone.svg')
        self.iconTrayNotification = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/phone-notification.svg')
        self.iconTrayFail = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/assets/phone-fail.svg')

        # window layout
        grid = QtWidgets.QGridLayout()

        self.lblPhone = QtWidgets.QLabel(translate('Line'))
        grid.addWidget(self.lblPhone, 0, 0)
        self.sltPhone = QtWidgets.QComboBox()
        for device in self.devices:
            self.sltPhone.addItem(str(device['number']))
        self.sltPhone.currentIndexChanged.connect(self.sltPhoneChanged)
        grid.addWidget(self.sltPhone, 0, 1)
        self.lblRegistrationStatus = QtWidgets.QLabel('...')
        grid.addWidget(self.lblRegistrationStatus, 0, 2)

        self.lblCall = QtWidgets.QLabel(translate('Call'))
        grid.addWidget(self.lblCall, 1, 0)
        self.txtCall = QtWidgets.QLineEdit()
        if(presetNumber): self.txtCall.setText(presetNumber)
        self.txtCall.setPlaceholderText(translate('Phone Number (type to search global address book)'))
        grid.addWidget(self.txtCall, 1, 1)
        self.btnCall = QtWidgets.QPushButton()
        self.btnCall.setIcon(self.iconCall)
        self.btnCall.setToolTip(translate('Start Call'))
        self.btnCall.clicked.connect(self.clickCall)
        self.txtCall.returnPressed.connect(self.btnCall.click)
        grid.addWidget(self.btnCall, 1, 2)

        self.tblCalls = CallHistoryTable()
        self.tblCalls.setData(self.callHistory)
        self.tblCalls.keyPressed.connect(self.tblCallsKeyPressed)
        self.tblCalls.doubleClicked.connect(self.recallHistory)

        gridPhoneBook = QtWidgets.QGridLayout()
        self.tblPhoneBook = PhoneBookTable()
        self.tblPhoneBook.setData(self.phoneBook)
        self.tblPhoneBook.keyPressed.connect(self.tblPhoneBookKeyPressed)
        self.tblPhoneBook.doubleClicked.connect(self.callPhoneBook)
        gridPhoneBook.addWidget(self.tblPhoneBook, 0, 0)
        buttonBox = QtWidgets.QVBoxLayout()
        btnAddPhoneBookEntry = QtWidgets.QPushButton(translate('Add'))
        btnAddPhoneBookEntry.clicked.connect(self.addPhoneBookEntry)
        buttonBox.addWidget(btnAddPhoneBookEntry)
        btnDelPhoneBookEntry = QtWidgets.QPushButton(translate('Remove'))
        btnDelPhoneBookEntry.clicked.connect(self.delPhoneBookEntry)
        buttonBox.addWidget(btnDelPhoneBookEntry)
        buttonBox.addStretch(1)
        gridPhoneBook.addLayout(buttonBox, 0, 1)
        gridPhoneBook.setContentsMargins(0, 0, 0, 0)
        widgetPhoneBook = QtWidgets.QWidget()
        widgetPhoneBook.setLayout(gridPhoneBook)

        tabHistoryPhoneBook = QtWidgets.QTabWidget()
        tabHistoryPhoneBook.addTab(self.tblCalls, translate('Call History'))
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
        registerAction.triggered.connect(self.clickRegister)
        fileMenu.addAction(registerAction)

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
        self.setWindowTitle(PRODUCT_NAME)
        self.resize(440, 280)
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

        # init IPC server socket
        self.ipcObserver = IpcObserver()
        self.ipcObserver.evtIpcMessageReceived = self.evtIpcMessageReceived
        self.ipcObserver.start()

        # start SIP registration
        self.initSipSession(self.sltPhone.currentIndex())

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
            sys.exit()
        else:
            event.ignore()
            self.hide()

    def clickQuit(self, e):
        self.close()
        sys.exit()

    def clickAboutDialog(self, e):
        dlg = AboutWindow(self)
        dlg.exec_()

    def evtIpcMessageReceivedHandler(self, message):
        if(message.strip() != ''):
            self.show()
            self.txtCall.setText(message)
            self.txtCall.selectAll()
            self.txtCall.setFocus()

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

    def recallHistory(self, e):
        for row in sorted(self.tblCalls.selectionModel().selectedRows()):
            historyItem = self.callHistory[row.row()]
            if('number' in historyItem and historyItem['number'].strip() != ''):
                self.sipHandler.call(historyItem['number'])
                break
    def callPhoneBook(self, e):
        for row in sorted(self.tblPhoneBook.selectionModel().selectedRows()):
            addressBookEntry = self.phoneBook[row.row()]
            if('number' in addressBookEntry and addressBookEntry['number'].strip() != ''):
                self.sipHandler.call(addressBookEntry['number'])
                break
    def tblCallsKeyPressed(self, keyCode):
        if(keyCode == QtCore.Qt.Key_Delete):
            indices = self.tblCalls.selectionModel().selectedRows() 
            for index in sorted(indices, reverse=True):
                del self.callHistory[index.row()]
            self.tblCalls.setData(self.callHistory)
            saveCallHistory(self.callHistory)
        if(keyCode == QtCore.Qt.Key_Return):
            self.recallHistory(None)
    def tblPhoneBookKeyPressed(self, keyCode):
        if(keyCode == QtCore.Qt.Key_Delete):
            self.delPhoneBookEntry(None)
        if(keyCode == QtCore.Qt.Key_Return):
            self.callPhoneBook(None)

    def addPhoneBookEntry(self, e):
        dialog = PhoneBookEntryWindow(self)
        dialog.exec_()
    def delPhoneBookEntry(self, e):
        indices = self.tblPhoneBook.selectionModel().selectedRows() 
        for index in sorted(indices, reverse=True):
            del self.phoneBook[index.row()]
        self.tblPhoneBook.setData(self.phoneBook)
        savePhoneBook(self.phoneBook)

    CALL_HISTORY_OUTGOING = 1
    CALL_HISTORY_INCOMING = 2
    CALL_HISTORY_INCOMING_MISSED = 3
    def addCallToHistory(self, displayName, number, type):
        self.callHistory.insert(0, {'date':datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'displayName':displayName, 'number':number, 'type':type})
        self.tblCalls.setData(self.callHistory)
        saveCallHistory(self.callHistory)

    STATUS_OK = 0
    STATUS_NOTIFY = 1
    STATUS_FAIL = 2
    def setTrayIcon(self, status):
        self.status = status
        newIcon = None
        if(status == self.STATUS_OK): newIcon = self.iconTrayNormal
        elif(status == self.STATUS_NOTIFY): newIcon = self.iconTrayNotification
        else: newIcon = self.iconTrayFail
        self.trayIcon.setIcon(newIcon)

    def clickRegister(self, e):
        self.initSipSession(self.sltPhone.currentIndex())

    def sltPhoneChanged(self, sender):
        self.initSipSession(self.sltPhone.currentIndex())

    def initSipSession(self, deviceIndex, force=False):
        try:
            device = self.devices[deviceIndex]

            port = device['callManagers'][0]['sipPort']
            useTls = False
            if(device['deviceSecurityMode'] == '2' or device['deviceSecurityMode'] == '3'):
                port = device['callManagers'][0]['sipsPort']
                useTls = True

            self.sipHandler = SipHandler(
                device['callManagers'][0]['address'], port, useTls,
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
        else:
            self.lblRegistrationStatus.setText(translate('FAILED!'))
            self.setTrayIcon(self.STATUS_FAIL)

            # option to take over other sessions
            if(status == SipHandler.REGISTRATION_ALREADY_ACTIVE):
                msg = QtWidgets.QMessageBox()
                msg.setIcon(QtWidgets.QMessageBox.Warning)
                msg.setWindowTitle(translate('Force Registration?'))
                msg.setText(translate('Your phone is already connected with another softphone instance. Do you want to disconnect the other softphone?'))
                msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                if(msg.exec_() == QtWidgets.QMessageBox.Ok):
                    self.initSipSession(self.sltPhone.currentIndex(), True)
            else:
                showErrorDialog(translate('Registration Error'), text)

    def evtIncomingCallHandler(self, status):
        if(status == SipHandler.INCOMING_CALL_RINGING):
            callerText = self.sipHandler.currentCall['headers']['From_parsed_text']
            diversionText = (translate('Forwarded for: ')+self.sipHandler.currentCall['headers']['Diversion'].split(';')[0]) if 'Diversion' in self.sipHandler.currentCall['headers'] else ''
            self.incomingCallWindow = IncomingCallWindow(callerText, diversionText)
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
            self.addCallToHistory(self.sipHandler.currentCall['headers']['From_parsed_text'], self.sipHandler.currentCall['headers']['From_parsed_number'], MainWindow.CALL_HISTORY_INCOMING)
            self.closeIncomingCallWindow()
            self.callWindow = CallWindow(self.sipHandler.currentCall['headers']['From_parsed_text'] if 'From_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'], False)
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
            self.addCallToHistory(self.sipHandler.currentCall['headers']['From_parsed_text'], self.sipHandler.currentCall['headers']['From_parsed_number'], MainWindow.CALL_HISTORY_INCOMING_MISSED)

    def closeIncomingCallWindow(self):
        if(self.ringtonePlayer != None):
            self.ringtonePlayer.stop()
            self.ringtonePlayer = None
        if(self.incomingCallWindow != None):
            self.incomingCallWindow.close()

    def clickCall(self, sender):
        numberStripped = self.txtCall.text().strip()
        if(numberStripped != ''): self.sipHandler.call(numberStripped)

    def evtOutgoingCallHandler(self, status, text):
        if(status == SipHandler.OUTGOING_CALL_TRYING):
            self.outgoingCallWindow = OutgoingCallWindow(self.sipHandler.currentCall['headers']['To_parsed_text'] if 'To_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'])
            self.outgoingCallWindow.finished.connect(self.outgoingCallWindowFinished)
            self.outgoingCallWindow.show()
        elif(status == SipHandler.OUTGOING_CALL_RINGING):
            self.outgoingCallWindow.lblTo.setText(self.sipHandler.currentCall['headers']['To_parsed_text'] if 'To_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'])
            self.addCallToHistory(self.sipHandler.currentCall['headers']['To_parsed_text'], self.sipHandler.currentCall['headers']['To_parsed_number'], MainWindow.CALL_HISTORY_OUTGOING)
            self.startRingtone(self.sipHandler.currentCall['number'])
        elif(status == SipHandler.OUTGOING_CALL_ACCEPTED):
            self.closeOutgoingCallWindow()
            self.callWindow = CallWindow(self.sipHandler.currentCall['headers']['To_parsed_text'] if 'To_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'], True)
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

    def getRingtoneFile(self, number):
        if(number):
            for entry in self.phoneBook:
                if('number' in entry and entry['number'].strip().replace('+', '00') == number.strip().replace('+', '00')):
                    if('ringtone' in entry and os.path.isfile(entry['ringtone'])):
                        return entry['ringtone']
        if(os.path.isfile(self.ringtoneFile)):
            return self.ringtoneFile
        return self.defaultRingtoneFile
    def startRingtone(self, number):
        self.ringtonePlayer = AudioPlayer(
            self.getRingtoneFile(number),
            self.sipHandler.audio,
            self.ringtoneOutputDeviceNames
        )
        self.ringtonePlayer.start()

def loadSettings(suppressError=False):
    try:
        with open(CFG_PATH) as f:
            return json.load(f)
    except Exception as e:
        if(not suppressError): showErrorDialog(translate('Error loading settings file'), str(e))
def saveSettings(settings):
    try:
        if(not os.path.isdir(CFG_DIR)): os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
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
        if(not os.path.isdir(CFG_DIR)): os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
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
        if(not os.path.isdir(CFG_DIR)): os.makedirs(CFG_DIR, mode=0o700, exist_ok=True)
        with open(PHONEBOOK_PATH, 'w') as json_file:
            json.dump(settings, json_file, indent=4)
    except Exception as e:
        showErrorDialog(translate('Error saving phone book file'), str(e))

# main entry point
if __name__ == '__main__':
    # parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--hidden', action='store_true', help='Start with tray icon only (for autostart)')
    parser.add_argument('-v', '--debug', action='store_true', help='Print debug output (SIP packet contents etc.)')
    args, unknownargs = parser.parse_known_args()
    presetNumber = None
    if(len(unknownargs) > 0 and unknownargs[0].startswith('tel:')):
        presetNumber = unknownargs[0].strip().split(':')[1].replace('+', '00')

    # if a number was given, we check if an instance is already running and forward the number to its MainWindow
    if(presetNumber):
        try:
            ipcConn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ipcConn.connect(('localhost', IpcObserver.IPC_PORT))
            ipcConn.sendall(str.encode(presetNumber))
            ipcConn.close()
            print('An instance is already running. Since a phone number was given as parameter, the number will be forwarded to the other instance and this instance will be closed immediately.')
            sys.exit(0)
        except Exception as e:
            # exception is thrown when connection to other instance could not be established - this will start a new instance regularly
            pass

    # init QT app
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # load QT translations
    translator = QtCore.QTranslator(app)
    if getattr(sys, 'frozen', False):
        translator.load(os.path.join(sys._MEIPASS, 'lang/%s.qm' % getdefaultlocale()[0]))
    elif os.path.isdir('lang'):
        translator.load('lang/%s.qm' % getdefaultlocale()[0])
    else:
        translator.load('/usr/share/jabber4linux/lang/%s.qm' % getdefaultlocale()[0])
    app.installTranslator(translator)

    # load settings, show main window or login window
    settings = loadSettings(True)
    if settings != None and 'user' in settings and 'devices' in settings and len(settings['devices']) > 0:
        # directly start main window if login already done
        window = MainWindow(settings, presetNumber=presetNumber, debug=args.debug)
        if not args.hidden: window.show()
        sys.exit(app.exec_())
    else:
        # show login window on first startup
        window = LoginWindow(debug=args.debug)
        if window.exec_() == QtWidgets.QDialog.Accepted:
            sys.exit(app.exec_())
