#!/bin/bash
set -e

# build .deb package
INSTALLDIR=/usr/share/jabber4linux
BUILDDIR=jabber4linux

# check root permissions
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as root!"
    #exit 1 # disabled for github workflow. don't know why this check fails here but sudo works.
fi

# cd to working dir
cd "$(dirname "$0")"

# compile language files
lrelease ../../lang/*.ts

# empty / create necessary directories
if [ -d "$BUILDDIR/usr" ]; then
    sudo rm -r $BUILDDIR/usr
fi

# copy files in place
sudo install -D -m 644 ../../assets/jabber4linux-autostart.desktop  -t $BUILDDIR/etc/xdg/autostart
sudo install -D -m 644 ../../assets/jabber4linux.desktop            -t $BUILDDIR/usr/share/applications
sudo install -D -m 644 ../../lang/*.qm                              -t $BUILDDIR/$INSTALLDIR/lang
sudo install -D -m 644 ../../jabber4linux/*.py                      -t $BUILDDIR/$INSTALLDIR/jabber4linux
sudo install -D -m 644 ../../jabber4linux/assets/*                  -t $BUILDDIR/$INSTALLDIR/jabber4linux/assets
sudo install -D -m 644 ../../requirements.txt                       -t $BUILDDIR/$INSTALLDIR
sudo install -D -m 644 ../../setup.py                               -t $BUILDDIR/$INSTALLDIR
sudo install -D -m 644 ../../README.md                              -t $BUILDDIR/$INSTALLDIR

# make binary available in PATH
sudo mkdir -p $BUILDDIR/usr/bin
sudo ln -sf   $INSTALLDIR/venv/bin/jabber4linux     $BUILDDIR/usr/bin/jabber4linux

# build deb
dpkg-deb -Zxz --build $BUILDDIR

echo "Build finished"
