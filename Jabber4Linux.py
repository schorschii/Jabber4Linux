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
from threading import Timer
import datetime
import pyaudio
import time
import argparse
import json
import re
import sys, os
import traceback


PRODUCT_VERSION = '0.1'

CFG_DIR  = str(Path.home())+'/.config/jabber4linux'
CFG_PATH = CFG_DIR+'/settings.json'
HISTORY_PATH = CFG_DIR+'/history.json'


def showErrorDialog(title, text, additionalText=''):
    print('Error: '+text)
    msg = QtWidgets.QMessageBox()
    msg.setIcon(QtWidgets.QMessageBox.Critical)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setDetailedText(additionalText)
    msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
    msg.exec()

class AboutWindow(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
        super(AboutWindow, self).__init__(*args, **kwargs)

        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.accepted.connect(self.accept)

        self.layout = QtWidgets.QVBoxLayout(self)

        labelAppName = QtWidgets.QLabel(self)
        labelAppName.setText('Jabber4Linux' + ' v' + PRODUCT_VERSION)
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
            'Jabber4Linux is a unofficial Cisco Jabber port for Linux.'
        )
        labelDescription.setStyleSheet('opacity:0.8')
        labelDescription.setFixedWidth(450)
        labelDescription.setWordWrap(True)
        labelDescription.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(labelDescription)

        self.layout.addWidget(self.buttonBox)

        self.setLayout(self.layout)
        self.setWindowTitle('About')
        self.setWindowIcon(QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/tux-phone.svg'))

class LoginWindow(QtWidgets.QDialog):
    debug = False

    def __init__(self, debug=False, *args, **kwargs):
        self.debug = debug
        super(LoginWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok|QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.login)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QtWidgets.QGridLayout(self)

        discoveredServer = UdsWrapper.discoverUdsServer(None)
        self.lblServerName = QtWidgets.QLabel('Server')
        self.layout.addWidget(self.lblServerName, 0, 0)

        self.txtServerName = QtWidgets.QLineEdit()
        self.txtServerName.setPlaceholderText('Address')
        if discoveredServer != None: self.txtServerName.setText(discoveredServer['address'])
        self.layout.addWidget(self.txtServerName, 0, 1)

        self.txtServerPort = QtWidgets.QLineEdit()
        self.txtServerPort.setPlaceholderText('Port')
        if discoveredServer != None: self.txtServerPort.setText(str(discoveredServer['port']))
        self.layout.addWidget(self.txtServerPort, 0, 2)

        self.lblUsername = QtWidgets.QLabel('Username')
        self.layout.addWidget(self.lblUsername, 1, 0)
        self.txtUsername = QtWidgets.QLineEdit()
        self.layout.addWidget(self.txtUsername, 1, 1, 1, 2)

        self.lblPassword = QtWidgets.QLabel('Password')
        self.layout.addWidget(self.lblPassword, 2, 0)
        self.txtPassword = QtWidgets.QLineEdit()
        self.txtPassword.setEchoMode(QtWidgets.QLineEdit.Password)
        self.layout.addWidget(self.txtPassword, 2, 1, 1, 2)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle('Jabber4Linux Login')
        self.resize(350, 150)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.setWindowIcon(QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/tux-phone.svg'))

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
            showErrorDialog('Login Error', str(e))

class IncomingCallWindow(QtWidgets.QDialog):
    def __init__(self, callerText, diversionText, *args, **kwargs):
        super(IncomingCallWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Yes|QtWidgets.QDialogButtonBox.No)
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
        self.setWindowTitle('Incoming Call')
        self.resize(250, 100)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowIcon(QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/tux-phone.svg'))

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
        self.buttonBox.rejected.connect(self.accept) # accept means: cancel call!

        self.layout = QtWidgets.QGridLayout(self)

        self.lblTo = QtWidgets.QLabel(callerText)
        self.layout.addWidget(self.lblTo, 0, 0)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle('Outgoing Call')
        self.resize(250, 100)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowIcon(QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/tux-phone.svg'))

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

class CallWindow(QtWidgets.QDialog):
    isOutgoingCall = None

    callTimeInterval = None
    startTime = 0

    def __init__(self, remotePartyName, isOutgoingCall, *args, **kwargs):
        self.isOutgoingCall = isOutgoingCall
        self.startTime = time.time()
        super(CallWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.rejected.connect(self.cancelCall)

        self.layout = QtWidgets.QGridLayout(self)

        self.lblRemotePartyName = QtWidgets.QLabel(remotePartyName)
        self.layout.addWidget(self.lblRemotePartyName, 0, 0)

        self.lblCallTimer = QtWidgets.QLabel(niceTime(0))
        self.layout.addWidget(self.lblCallTimer, 1, 0)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle('Call')
        self.resize(250, 100)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowIcon(QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/tux-phone.svg'))

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        # schedule call timer update
        self.refreshCallTimer()

    def cancelCall(self):
        self.callTimeInterval.cancel()
        self.reject() # reject dialog result code means: close call (BYE)!

    def refreshCallTimer(self):
        self.lblCallTimer.setText(niceTime(time.time() - self.startTime))
        self.callTimeInterval = Timer(1, self.refreshCallTimer)
        self.callTimeInterval.daemon = True
        self.callTimeInterval.start()

class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    parentWidget = None

    def __init__(self, icon, parent):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.parentWidget = parent
        menu = QtWidgets.QMenu(parent)
        openAction = menu.addAction('Open Jabber4Linux')
        openAction.triggered.connect(self.open)
        exitAction = menu.addAction('Exit')
        exitAction.triggered.connect(self.exit)
        self.setContextMenu(menu)
        self.activated.connect(self.showMenuOnTrigger)
        self.setToolTip('Jabber4Linux')

    def showMenuOnTrigger(self, reason):
        if(reason == QtWidgets.QSystemTrayIcon.Trigger):
            self.contextMenu().popup(QtGui.QCursor.pos())

    def open(self):
        self.parentWidget.show()

    def exit(self):
        self.parentWidget.close()
        QtCore.QCoreApplication.exit()

class CallHistoryTable(QtWidgets.QTableWidget):
    def __init__(self, *args):
        QtWidgets.QTableWidget.__init__(self, *args)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QTableWidget.EditTrigger.NoEditTriggers)

    def setData(self, calls):
        self.setRowCount(len(calls))
        self.setColumnCount(3)

        counter = 0
        for call in calls:
            newItem = QtWidgets.QTableWidgetItem('>' if call['incoming'] else '<')
            self.setItem(counter, 0, newItem)
            newItem = QtWidgets.QTableWidgetItem(call['displayName'])
            self.setItem(counter, 1, newItem)
            newItem = QtWidgets.QTableWidgetItem(call['date'])
            self.setItem(counter, 2, newItem)
            counter += 1

        self.setHorizontalHeaderLabels([
            '', # direction column (< or >)
            QtWidgets.QApplication.translate('Jabber4Linux', 'Remote Party'),
            QtWidgets.QApplication.translate('Jabber4Linux', 'Date')
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
        #self.activated[QtCore.QModelIndex].connect(self.applySuggestion)

    def splitPath(self, path):
        self.model().search(path)
        return super(PhoneBookSearchCompleter, self).splitPath(path)

    def pathFromIndex(self, index):
        return self.model().item(index.row(), 0).number

    #def applySuggestion(self, index):
    #    self.mainWindow.txtCall.setText(self.model().item(index.row(), 0).number)

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

    def __init__(self, settings, debug=False, *args, **kwargs):
        self.debug = debug
        self.user = settings['user']
        self.devices = settings['devices']
        self.ringtonePlayer = None
        self.ringtoneOutputDeviceNames = settings.get('ringtone-devices', [])
        self.inputDeviceName = settings.get('input-device', None)
        self.outputDeviceName = settings.get('output-device', None)
        self.ringtoneFile = settings.get('ringtone', os.path.dirname(os.path.realpath(__file__))+'/ringelingeling.wav')
        super(MainWindow, self).__init__(*args, **kwargs)
        self.callHistory = loadCallHistory(True)

        # window layout
        grid = QtWidgets.QGridLayout()

        self.lblPhone = QtWidgets.QLabel('Line')
        grid.addWidget(self.lblPhone, 0, 0)
        self.sltPhone = QtWidgets.QComboBox()
        for device in self.devices:
            self.sltPhone.addItem(str(device['number']))
        self.sltPhone.currentIndexChanged.connect(self.sltPhoneChanged)
        grid.addWidget(self.sltPhone, 0, 1)
        self.lblRegistrationStatus = QtWidgets.QLabel('...')
        grid.addWidget(self.lblRegistrationStatus, 0, 2)

        self.lblCall = QtWidgets.QLabel('Call')
        grid.addWidget(self.lblCall, 1, 0)
        self.txtCall = QtWidgets.QLineEdit()
        grid.addWidget(self.txtCall, 1, 1)
        self.btnCall = QtWidgets.QPushButton('Call')
        self.btnCall.clicked.connect(self.clickCall)
        self.txtCall.returnPressed.connect(self.btnCall.click)
        grid.addWidget(self.btnCall, 1, 2)

        self.lblHistory = QtWidgets.QLabel('History')
        grid.addWidget(self.lblHistory, 2, 0)
        self.tblCalls = CallHistoryTable()
        self.tblCalls.setData(self.callHistory)
        self.tblCalls.doubleClicked.connect(self.recallHistory)
        grid.addWidget(self.tblCalls, 2, 1)

        widget = QtWidgets.QWidget(self)
        widget.setLayout(grid)
        self.setCentralWidget(widget)

        # register event handler
        self.evtRegistrationStatusChanged.connect(self.evtRegistrationStatusChangedHandler)
        self.evtIncomingCall.connect(self.evtIncomingCallHandler)
        self.evtOutgoingCall.connect(self.evtOutgoingCallHandler)
        self.evtCallClosed.connect(self.evtCallClosedHandler)

        # init QCompleter for phone book search
        self.phoneBookSearchCompleterModel = PhoneBookSearchModel(self)
        phoneBookSearchCompleter = PhoneBookSearchCompleter(self, caseSensitivity=QtCore.Qt.CaseInsensitive)
        phoneBookSearchCompleter.setModel(self.phoneBookSearchCompleterModel)
        self.txtCall.setCompleter(phoneBookSearchCompleter)

        # Menubar
        mainMenu = self.menuBar()

        # File Menu
        fileMenu = mainMenu.addMenu('&File')

        registerAction = QtWidgets.QAction('&Register', self)
        registerAction.triggered.connect(self.clickRegister)
        fileMenu.addAction(registerAction)

        fileMenu.addSeparator()
        quitAction = QtWidgets.QAction('&Quit', self)
        quitAction.setShortcut('Ctrl+Q')
        quitAction.triggered.connect(self.clickQuit)
        fileMenu.addAction(quitAction)

        # Audio Menu
        audioMenu = mainMenu.addMenu('&Audio')
        inputDevicesMenu = audioMenu.addMenu('&Input Device')
        outputDevicesMenu = audioMenu.addMenu('&Output Device')
        ringtoneDevicesMenu = audioMenu.addMenu('&Ringtone Devices')
        inputDevicesGroup = QtWidgets.QActionGroup(self)
        inputDevicesGroup.setExclusive(True)
        outputDevicesGroup = QtWidgets.QActionGroup(self)
        outputDevicesGroup.setExclusive(True)

        with ignoreStderr(): audio = pyaudio.PyAudio()
        info = audio.get_host_api_info_by_index(0)
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
        helpMenu = mainMenu.addMenu('&Help')

        aboutAction = QtWidgets.QAction('&About', self)
        aboutAction.setShortcut('F1')
        aboutAction.triggered.connect(self.clickAboutDialog)
        helpMenu.addAction(aboutAction)

        # window properties
        self.setWindowTitle('Jabber4Linux')
        self.resize(460, 260)
        self.txtCall.setFocus()
        self.setWindowIcon(QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/tux-phone.svg'))

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        # tray icon
        self.trayIcon = SystemTrayIcon(QtGui.QIcon(), self)
        self.setTrayIcon(self.STATUS_FAIL)
        self.trayIcon.show()

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
        saveCallHistory(self.callHistory)
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

    def addCallToHistory(self, displayName, number, incoming):
        self.callHistory.insert(0, {'date':datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'displayName':displayName, 'number':number, 'incoming':incoming})
        self.tblCalls.setData(self.callHistory)

    STATUS_OK = 0
    STATUS_FAIL = 1
    def setTrayIcon(self, status):
        newIcon = None
        if(status == 0):
            newIcon = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/phone.svg')
        else:
            newIcon = QtGui.QIcon(os.path.dirname(os.path.realpath(__file__))+'/phone-fail.svg')
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
            self.lblRegistrationStatus.setText('OK!')
            self.setTrayIcon(self.STATUS_OK)
        else:
            self.lblRegistrationStatus.setText('FAILED!')
            self.setTrayIcon(self.STATUS_FAIL)

            # option to take over other sessions
            if(status == SipHandler.REGISTRATION_ALREADY_ACTIVE):
                msg = QtWidgets.QMessageBox()
                msg.setIcon(QtWidgets.QMessageBox.Warning)
                msg.setWindowTitle(QtWidgets.QApplication.translate('Jabber4Linux', 'Force Registration?'))
                msg.setText(QtWidgets.QApplication.translate('Jabber4Linux', 'Your phone is already connected with another softphone instance. Do you want to disconnect the other softphone?'))
                msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                if(msg.exec_() == QtWidgets.QMessageBox.Ok):
                    self.initSipSession(self.sltPhone.currentIndex(), True)
            else:
                showErrorDialog('Registration Error', text)

    def evtIncomingCallHandler(self, status):
        self.addCallToHistory(self.sipHandler.currentCall['headers']['From_parsed_text'], self.sipHandler.currentCall['headers']['From_parsed_number'], True)
        if(status == SipHandler.INCOMING_CALL_RINGING):
            callerText = self.sipHandler.currentCall['headers']['From_parsed_text']
            diversionText = ('Forwarded for: '+self.sipHandler.currentCall['headers']['Diversion'].split(';')[0]) if 'Diversion' in self.sipHandler.currentCall['headers'] else ''
            self.incomingCallWindow = IncomingCallWindow(callerText, diversionText)
            try:
                self.ringtonePlayer = AudioPlayer(
                    self.ringtoneFile,
                    self.sipHandler.audio,
                    self.ringtoneOutputDeviceNames
                )
                self.ringtonePlayer.start()
            except Exception as e:
                print('!!! ringtone error: '+str(e))
            self.incomingCallWindow.finished.connect(self.incomingCallWindowFinished)
            self.incomingCallWindow.show()
        elif(status == SipHandler.INCOMING_CALL_CANCELED):
            self.closeIncomingCallWindow()
        elif(status == SipHandler.INCOMING_CALL_ACCEPTED):
            self.closeIncomingCallWindow()
            self.callWindow = CallWindow(self.sipHandler.currentCall['headers']['From_parsed_text'] if 'From_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'], False)
            self.callWindow.finished.connect(self.callWindowFinished)
            self.callWindow.show()
        else:
            showErrorDialog('Incoming Call Failed', str(status))

    def incomingCallWindowFinished(self, status):
        self.closeIncomingCallWindow()
        if status == QtWidgets.QDialog.Accepted:
            self.sipHandler.acceptCall()
        else:
            self.sipHandler.rejectCall()

    def closeIncomingCallWindow(self):
        if(self.ringtonePlayer != None):
            self.ringtonePlayer.stop()
            self.ringtonePlayer = None
        if(self.incomingCallWindow != None):
            self.incomingCallWindow.close()

    def clickCall(self, sender):
        numberStripped = self.txtCall.text().strip()
        self.sipHandler.call(numberStripped)

    def evtOutgoingCallHandler(self, status, text):
        if(status == SipHandler.OUTGOING_CALL_TRYING):
            self.outgoingCallWindow = OutgoingCallWindow(self.sipHandler.currentCall['headers']['To_parsed_text'] if 'To_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'])
            self.outgoingCallWindow.finished.connect(self.outgoingCallWindowFinished)
            self.outgoingCallWindow.show()
        elif(status == SipHandler.OUTGOING_CALL_RINGING):
            self.outgoingCallWindow.lblTo.setText(self.sipHandler.currentCall['headers']['To_parsed_text'] if 'To_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'])
            self.ringtonePlayer = AudioPlayer(
                self.ringtoneFile,
                self.sipHandler.audio,
                self.ringtoneOutputDeviceNames
            )
            self.ringtonePlayer.start()
            self.addCallToHistory(self.sipHandler.currentCall['headers']['To_parsed_text'], self.sipHandler.currentCall['headers']['To_parsed_number'], False)
        elif(status == SipHandler.OUTGOING_CALL_ACCEPTED):
            self.closeOutgoingCallWindow()
            self.callWindow = CallWindow(self.sipHandler.currentCall['headers']['To_parsed_text'] if 'To_parsed_text' in self.sipHandler.currentCall['headers'] else self.sipHandler.currentCall['number'], True)
            self.callWindow.finished.connect(self.callWindowFinished)
            self.callWindow.show()
        else:
            self.closeOutgoingCallWindow()
            showErrorDialog('Outgoing Call Failed', str(text))

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

def loadSettings(suppressError=False):
    try:
        if(not os.path.isdir(CFG_DIR)): os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_PATH) as f:
            return json.load(f)
    except Exception as e:
        if(not suppressError): showErrorDialog('Error loading settings file', str(e))
def saveSettings(settings):
    try:
        if(not os.path.isdir(CFG_DIR)): os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_PATH, 'w') as json_file:
            json.dump(settings, json_file, indent=4)
    except Exception as e:
        showErrorDialog('Error saving settings file', str(e))

def loadCallHistory(suppressError=False):
    try:
        if(not os.path.isdir(CFG_DIR)): os.makedirs(CFG_DIR, exist_ok=True)
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except Exception as e:
        if(not suppressError): showErrorDialog('Error loading history file', str(e))
        return []
def saveCallHistory(settings):
    try:
        if(not os.path.isdir(CFG_DIR)): os.makedirs(CFG_DIR, exist_ok=True)
        with open(HISTORY_PATH, 'w') as json_file:
            json.dump(settings, json_file, indent=4)
    except Exception as e:
        showErrorDialog('Error saving history file', str(e))

# main entry point
if __name__ == '__main__':
    # parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--hidden', action='store_true', help='Start with tray icon only (for autostart)')
    parser.add_argument('-v', '--debug', action='store_true', help='Print debug output (SIP packet contents etc.)')
    args = parser.parse_args()

    # init QT app
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    settings = loadSettings(True)
    if settings != None and 'user' in settings and 'devices' in settings and len(settings['devices']) > 0:
        # directly start main window if login already done
        window = MainWindow(settings, debug=args.debug)
        if not args.hidden: window.show()
        sys.exit(app.exec_())
    else:
        # show login window on first startup
        window = LoginWindow(debug=args.debug)
        if window.exec_() == QtWidgets.QDialog.Accepted:
            sys.exit(app.exec_())
