__title__   = 'Jabber4Linux'
__author__  = 'Georg Sieber'
__license__ = 'GPL-3.0'
__version__ = '0.5.2'
__website__ = 'https://github.com/schorschii/Jabber4Linux'

__all__ = [__author__, __license__, __version__]


from pathlib import Path
CFG_DIR  = str(Path.home())+'/.config/jabber4linux'
CFG_PATH = CFG_DIR+'/settings.json'
HISTORY_PATH = CFG_DIR+'/history.json'
PHONEBOOK_PATH = CFG_DIR+'/phonebook.json'
CLIENT_CERTS_DIR = CFG_DIR+'/client-certs'
SERVER_CERTS_DIR = CFG_DIR+'/server-certs'
