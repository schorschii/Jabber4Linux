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

# compile language files
lrelease ../../lang/*.ts

# empty / create necessary directories
if [ -d "jabber4linux/usr/share/jabber4linux" ]; then
	rm -r jabber4linux/usr/share/jabber4linux
fi
mkdir -p jabber4linux/usr/share/jabber4linux/lang
mkdir -p jabber4linux/usr/share/jabber4linux/assets
mkdir -p jabber4linux/usr/share/applications
mkdir -p jabber4linux/etc/xdg/autostart

# copy files in place
cp ../../assets/jabber4linux-autostart.desktop jabber4linux/etc/xdg/autostart
cp ../../assets/jabber4linux.desktop jabber4linux/usr/share/applications
cp ../../*.py jabber4linux/usr/share/jabber4linux
cp ../../lang/*.qm jabber4linux/usr/share/jabber4linux/lang
cp ../../assets/*.svg jabber4linux/usr/share/jabber4linux/assets
cp ../../assets/*.wav jabber4linux/usr/share/jabber4linux/assets
cp ../../README.md jabber4linux/usr/share/jabber4linux
cp ../../LICENSE jabber4linux/usr/share/jabber4linux

# set file permissions
chown -R root:root jabber4linux
chmod 775 jabber4linux/usr/share/jabber4linux/Jabber4Linux.py

# build deb
dpkg-deb -Zxz --build jabber4linux

echo "Build finished"
