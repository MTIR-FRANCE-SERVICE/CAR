import sys
import os

# Add virtualenv site-packages to path
VIRTUALENV = os.path.join('/home/MtirFS/CAR', 'venv')
PYTHON_VERSION = '3.9'
VIRTUALENV_SITE = os.path.join(VIRTUALENV, 'lib', f'python{PYTHON_VERSION}', 'site-packages')
sys.path.insert(0, VIRTUALENV_SITE)

# Add your project directory to the sys.path
path = '/home/MtirFS/CAR'
if path not in sys.path:
    sys.path.append(path)

# Set environment variables
os.environ['SPREADSHEET_ID'] = '1OivLY5r_EZ-aTesVP7SmLiojeNc78AdzTWgdAN_Qwcs'
os.environ['SECRET_KEY'] = 'b29a0b3c7d1e4f5a6b8c9d0e1f2a3b4c5d6e7f8g9h0i1j2k3l4m5n6o7p8q9'

# Import your Flask app
from src.app import app as application
