from distutils.command.clean import clean
from distutils import log
from setuptools import setup

# Get the long description from the README file
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
      name='jabber4linux',
      version=__import__('jabber4linux').__version__,
      description='Unofficial Cisco Jabber Softphone Implementation for Linux',
      long_description=long_description,
      long_description_content_type='text/markdown',
      install_requires=[i.strip() for i in open('requirements.txt').readlines()],
      license=__import__('jabber4linux').__license__,
      author='Georg Sieber',
      keywords='python3 pdf sign certify certificate stamp',
      url=__import__('jabber4linux').__website__,
      classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: End Users/Desktop',
            'Operating System :: POSIX :: Linux',
            'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
            'Programming Language :: Python',
            'Programming Language :: Python :: 3',
      ],
      packages=['jabber4linux'],
      include_package_data = True,
      data_files=[('', [
            'jabber4linux/assets/add.light.svg',
            'jabber4linux/assets/add.svg',
            'jabber4linux/assets/add-book.light.svg',
            'jabber4linux/assets/add-book.svg',
            'jabber4linux/assets/delete.light.svg',
            'jabber4linux/assets/delete.svg',
            'jabber4linux/assets/edit.light.svg',
            'jabber4linux/assets/edit.svg',
            'jabber4linux/assets/incoming.light.svg',
            'jabber4linux/assets/incoming.missed.svg',
            'jabber4linux/assets/incoming.svg',
            'jabber4linux/assets/outgoing.light.svg',
            'jabber4linux/assets/outgoing.svg',
            'jabber4linux/assets/phone.svg',
            'jabber4linux/assets/phone-fail.svg',
            'jabber4linux/assets/phone-notification.svg',
            'jabber4linux/assets/ringelingeling.wav',
            'jabber4linux/assets/tux-phone.svg',
      ])],
      entry_points={
            'gui_scripts': [
                  'jabber4linux = jabber4linux.Jabber4Linux:main',
            ],
            'console_scripts': [
                  'capfwrapper = jabber4linux.CapfWrapper:main',
            ],
      },
      platforms=['all'],
      #install_requires=[],
      #test_suite='tests',
)
