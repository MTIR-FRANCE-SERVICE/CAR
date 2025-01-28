import sys
import os

# Add the application directory to the Python path
path = os.path.expanduser('~/CAR')
if path not in sys.path:
    sys.path.append(path)

# Activate the virtual environment
activate_this = os.path.expanduser('~/.virtualenvs/car-env/bin/activate_this.py')
if os.path.exists(activate_this):
    with open(activate_this) as file_:
        exec(file_.read(), dict(__file__=activate_this))

# Configure environment variables
os.environ['SPREADSHEET_ID'] = '1OivLY5r_EZ-aTesVP7SmLiojeNc78AdzTWgdAN_Qwcs'
os.environ['SECRET_KEY'] = 'b29a0b3c7d1e4f5a6b8c9d0e1f2a3b4c5d6e7f8g9h0i1j2k3l4m5n6o7p8q9'

# Import the Flask application
from src.app import app as application
