#!/bin/bash
set -e

# build .deb package

# check root permissions
if [ "$EUID" -ne 0 ]
	then echo "Please run this script as root!"
	exit
fi

# cd to working dir
cd "$(dirname "$0")"

# create necessary directories
mkdir -p jabber4linux/usr/share/jabber4linux

# copy files in place
cp ../../*.py jabber4linux/usr/share/jabber4linux
cp ../../*.svg jabber4linux/usr/share/jabber4linux
cp ../../*.wav jabber4linux/usr/share/jabber4linux
cp ../../README.md jabber4linux/usr/share/jabber4linux
cp ../../LICENSE jabber4linux/usr/share/jabber4linux

# set file permissions
chown -R root:root jabber4linux
chmod 775 jabber4linux/usr/share/jabber4linux/Jabber4Linux.py

# build deb
dpkg-deb -Zxz --build jabber4linux

echo "Build finished"
