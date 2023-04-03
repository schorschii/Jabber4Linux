#!/usr/bin/python3

from PyQt5 import QtWidgets
from PyQt5 import QtGui
from PyQt5 import QtCore

from UdsWrapper import UdsWrapper
from SipHandler import SipHandler
from AudioSocket import AudioPlayer

from pathlib import Path
import json
import sys, os
import traceback


PRODUCT_VERSION = '0.1'
DEBUG = True

CFG_DIR  = str(Path.home())+'/.config/jabber4linux'
CFG_PATH = CFG_DIR+'/settings.json'


def showErrorDialog(title, text, additionalText=''):
    print('Error: '+text)
    msg = QtWidgets.QMessageBox()
    msg.setIcon(QtWidgets.QMessageBox.Critical)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setDetailedText(additionalText)
    msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
    retval = msg.exec_()

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

class LoginWindow(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
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
            uds = UdsWrapper(self.txtUsername.text(), self.txtPassword.text(), self.txtServerName.text(), self.txtServerPort.text(), DEBUG)
            userDetails = uds.getUserDetails()
            devices = []
            for device in uds.getDevices():
                deviceDetails = uds.getDevice(device['id'])
                if deviceDetails != None and deviceDetails['model'] == 'Cisco Unified Client Services Framework':
                    devices.append(deviceDetails)
            if len(devices) == 0: raise Exception('Unable to find a Jabber softphone device')

            window = MainWindow({'user':userDetails, 'devices':devices, 'config':{}})
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

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

class CallWindow(QtWidgets.QDialog):
    isOutgoingCall = None

    def __init__(self, remotePartyName, isOutgoingCall, *args, **kwargs):
        self.isOutgoingCall = isOutgoingCall
        super(CallWindow, self).__init__(*args, **kwargs)

        # window layout
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.rejected.connect(self.accept) # accept means: close call (BYE)!

        self.layout = QtWidgets.QGridLayout(self)

        self.lblRemotePartyName = QtWidgets.QLabel(remotePartyName)
        self.layout.addWidget(self.lblRemotePartyName, 0, 0)

        self.layout.addWidget(self.buttonBox, 3, 1, 1, 2)
        self.setLayout(self.layout)

        # window properties
        self.setWindowTitle('Call')
        self.resize(250, 100)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def endCall(self):
        try:
            # todo: decline
            self.reject()
        except Exception as e:
            print(traceback.format_exc())
            showErrorDialog('Accept Error', str(e))

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
        QtCore.QCoreApplication.exit()

class MainWindow(QtWidgets.QMainWindow):
    user = None
    devices = None
    config = {} # misc settings

    sipHandler = None

    ringtonePlayer = None
    incomingCallWindow = None
    outgoingCallWindow = None
    callWindow = None

    evtRegistrationStatusChanged = QtCore.pyqtSignal(int, str)
    evtIncomingCall = QtCore.pyqtSignal(int)
    evtOutgoingCall = QtCore.pyqtSignal(int, str)
    evtCallClosed = QtCore.pyqtSignal()

    def __init__(self, settings, *args, **kwargs):
        self.user = settings['user']
        self.devices = settings['devices']
        self.config = settings['config']
        super(MainWindow, self).__init__(*args, **kwargs)

        # window layout
        grid = QtWidgets.QGridLayout()

        self.lblPhone = QtWidgets.QLabel('Line') # todo: when changing the phone line, re-register SIP with the new line
        grid.addWidget(self.lblPhone, 0, 0)
        self.sltPhone = QtWidgets.QComboBox()
        for device in self.devices:
            self.sltPhone.addItem(str(device['number']))
        grid.addWidget(self.sltPhone, 0, 1)
        self.lblRegistrationStatus = QtWidgets.QLabel('...')
        grid.addWidget(self.lblRegistrationStatus, 0, 2)

        self.lblCall = QtWidgets.QLabel('Call')
        grid.addWidget(self.lblCall, 1, 0)
        self.txtCall = QtWidgets.QLineEdit()
        grid.addWidget(self.txtCall, 1, 1)
        self.btnCall = QtWidgets.QPushButton('Call')
        self.btnCall.clicked.connect(self.clickCall)
        grid.addWidget(self.btnCall, 1, 2)

        widget = QtWidgets.QWidget(self)
        widget.setLayout(grid)
        self.setCentralWidget(widget)

        # register event handler
        self.evtRegistrationStatusChanged.connect(self.evtRegistrationStatusChangedHandler)
        self.evtIncomingCall.connect(self.evtIncomingCallHandler)
        self.evtOutgoingCall.connect(self.evtOutgoingCallHandler)
        self.evtCallClosed.connect(self.evtCallClosedHandler)

        # Menubar
        mainMenu = self.menuBar()

        # File Menu
        fileMenu = mainMenu.addMenu('&File')

        quitAction = QtWidgets.QAction('&Quit', self)
        quitAction.setShortcut('Ctrl+Q')
        quitAction.triggered.connect(self.clickQuit)
        fileMenu.addAction(quitAction)

        # Help Menu
        helpMenu = mainMenu.addMenu('&Help')

        aboutAction = QtWidgets.QAction('&About', self)
        aboutAction.setShortcut('F1')
        aboutAction.triggered.connect(self.clickAboutDialog)
        helpMenu.addAction(aboutAction)

        # window properties
        self.setWindowTitle('Jabber4Linux')
        self.resize(450, 250)
        self.txtCall.setFocus()

        # center screen
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        # tray icon
        trayIcon = SystemTrayIcon(QtGui.QIcon('./phone.svg'), self)
        trayIcon.show()

        # start SIP registration
        self.initSipSession(0)

    def closeEvent(self, event):
        saveSettings({
            'user': self.user,
            'devices': self.devices,
            'config': self.config,
        })
        if(not DEBUG):
            event.ignore()
            self.hide()

    def clickQuit(self, e):
        sys.exit()

    def clickAboutDialog(self, e):
        dlg = AboutWindow(self)
        dlg.exec_()

    def initSipSession(self, deviceIndex):
        device = self.devices[deviceIndex]
        self.sipHandler = SipHandler(
            device['callManagers'][0]['address'], device['callManagers'][0]['sipPort'],
            self.user['displayName'], device['number'], device['deviceName'], device['contact'],
            DEBUG
        )
        self.sipHandler.evtRegistrationStatusChanged = self.evtRegistrationStatusChanged
        self.sipHandler.evtIncomingCall = self.evtIncomingCall
        self.sipHandler.evtOutgoingCall = self.evtOutgoingCall
        self.sipHandler.evtCallClosed = self.evtCallClosed
        self.sipHandler.start()

    def evtRegistrationStatusChangedHandler(self, status, text):
        if(status == SipHandler.REGISTRATION_REGISTERED):
            self.lblRegistrationStatus.setText('OK!')
        else:
            self.lblRegistrationStatus.setText('FAILED!')
            showErrorDialog('Registration Error', text)
        self.lblRegistrationStatus.setToolTip(text)

    def evtIncomingCallHandler(self, status):
        if(status == SipHandler.INCOMING_CALL_RINGING):
            callerText = self.sipHandler.currentCall['headers']['From_parsed']
            diversionText = ('Forwarded for: '+self.sipHandler.currentCall['headers']['Diversion'].split(';')[0]) if 'Diversion' in self.sipHandler.currentCall['headers'] else ''
            self.incomingCallWindow = IncomingCallWindow(callerText, diversionText)
            try:
                self.ringtonePlayer = AudioPlayer(
                    self.config['ringtone'] if 'ringtone' in self.config else os.path.dirname(os.path.realpath(__file__))+'/ringelingeling.wav',
                    self.sipHandler.audio
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
            self.callWindow = CallWindow('...', False) # todo: show SIP header 'Remote-Party' here
            self.callWindow.finished.connect(self.callWindowFinished)
            self.callWindow.show()
        else:
            showErrorDialog('Incoming Call Failed', str(status))

    def incomingCallWindowFinished(self, status):
        if status == QtWidgets.QDialog.Accepted:
            self.sipHandler.acceptCall()
        else:
            self.sipHandler.rejectCall()
            self.closeIncomingCallWindow()

    def closeIncomingCallWindow(self):
        if(self.incomingCallWindow != None):
            self.incomingCallWindow.close()
        if(self.ringtonePlayer != None):
            self.ringtonePlayer.stop()
            del self.ringtonePlayer

    def clickCall(self, sender):
        numberStripped = self.txtCall.text().strip()
        self.sipHandler.call(numberStripped)

    def evtOutgoingCallHandler(self, status, text):
        if(status == SipHandler.OUTGOING_CALL_RINGING):
            self.outgoingCallWindow = OutgoingCallWindow(self.txtCall.text())
            self.outgoingCallWindow.finished.connect(self.outgoingCallWindowFinished)
            self.outgoingCallWindow.show()
        elif(status == SipHandler.OUTGOING_CALL_ACCEPTED):
            self.closeOutgoingCallWindow()
            self.callWindow = CallWindow('...', True) # todo: show SIP header 'Remote-Party' here
            self.callWindow.finished.connect(self.callWindowFinished)
            self.callWindow.show()
        else:
            self.closeOutgoingCallWindow()
            showErrorDialog('Outgoing Call Failed', str(text))

    def outgoingCallWindowFinished(self, status):
        if status == QtWidgets.QDialog.Accepted:
            self.sipHandler.cancelCall()

    def closeOutgoingCallWindow(self):
        if(self.outgoingCallWindow != None):
            self.outgoingCallWindow.close()
        if(self.ringtonePlayer != None):
            self.ringtonePlayer.stop()
            del self.ringtonePlayer

    def callWindowFinished(self, status):
        if status == QtWidgets.QDialog.Accepted:
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

# main entry point
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    settings = loadSettings(True)
    if settings != None and 'user' in settings and 'devices' in settings and len(settings['devices']) > 0:
        window = MainWindow(settings)
        window.show()
        sys.exit(app.exec_())
    else:
        window = LoginWindow()
        if window.exec_() == QtWidgets.QDialog.Accepted:
            sys.exit(app.exec_())
