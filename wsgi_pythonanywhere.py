import sys
import os

# Add the path to your CAR directory
path = '/home/MtirFS/CAR'
if path not in sys.path:
    sys.path.append(path)

# Set environment variables
os.environ['SPREADSHEET_ID'] = '1OivLY5r_EZ-aTesVP7SmLiojeNc78AdzTWgdAN_Qwcs'
os.environ['SECRET_KEY'] = 'your_secret_key_here'  # Replace with your actual secret key

# Import the Flask application
from src.app import app as application
