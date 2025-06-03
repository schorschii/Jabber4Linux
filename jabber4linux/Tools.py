#!/usr/bin/env python3

import contextlib
import os, sys


@contextlib.contextmanager
def ignoreStderr():
    yield
    return
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)

def niceTime(secs):
    secs = int(secs)
    mins = secs // 60
    secs = secs % 60
    hours = mins // 60
    mins = mins % 60
    return '{:02d}:{:02d}:{:02d}'.format(int(hours), int(mins), secs)

def getFiles(folder):
    files = []
    if(os.path.isdir(folder)):
        for fileName in os.listdir(folder):
            files.append(folder+'/'+fileName)
    return files
