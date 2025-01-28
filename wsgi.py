import sys
import os

# Ajouter le chemin de votre application
path = os.path.expanduser('~/CAR')
if path not in sys.path:
    sys.path.append(path)

# Configuration des variables d'environnement
os.environ['SPREADSHEET_ID'] = '1OivLY5r_EZ-aTesVP7SmLiojeNc78AdzTWgdAN_Qwcs'
os.environ['SECRET_KEY'] = 'b29a0b3c7d1e4f5a6b8c9d0e1f2a3b4c5d6e7f8g9h0i1j2k3l4m5n6o7p8q9'

# Importer l'application Flask
from src.app import app as application
