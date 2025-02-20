from flask import Flask, render_template, jsonify, send_from_directory
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
import os
from dotenv import load_dotenv
import logging
import traceback
import json
import re

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.FileHandler('logs/app.log'),  # Log to a file
                       logging.StreamHandler()  # Log to console
                   ])
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')

# Google Sheets API setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
logger.debug(f"Using Spreadsheet ID: {SPREADSHEET_ID}")

def get_google_sheets_service():
    try:
        credentials_path = os.path.abspath('src/config/credentials.json')
        logger.debug(f"Looking for credentials at: {credentials_path}")
        
        if not os.path.exists(credentials_path):
            logger.error(f"Credentials file not found at {credentials_path}")
            return None

        try:
            with open(credentials_path, 'r') as f:
                creds_json = json.load(f)
                service_email = creds_json.get('client_email')
                project_id = creds_json.get('project_id')
                logger.debug(f"Service account email: {service_email}")
                logger.debug(f"Project ID: {project_id}")

            creds = service_account.Credentials.from_service_account_file(
                credentials_path, 
                scopes=SCOPES
            )
            logger.debug("Successfully created credentials object")
            
            service = build('sheets', 'v4', credentials=creds)
            logger.debug("Successfully built sheets service")
            
            return service
                
        except Exception as e:
            logger.error(f"Error creating service: {str(e)}")
            logger.error(traceback.format_exc())
            return None
            
    except Exception as e:
        logger.error(f"Error in get_google_sheets_service: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def parse_vehicle_data(values):
    vehicles = []
    try:
        for row in values:
            if len(row) >= 6:
                # Get the category based on the sheet or column
                category = 'FLOTTE'  # Default category
                if 'FRANCE SERV' in str(row[4]):
                    category = 'CHAUFFEUR'
                elif any(status in str(row[5]).upper() for status in ['MC', 'FC']):
                    category = 'TRANSCO'

                vehicle = {
                    'type': str(row[0]) if len(row) > 0 else '',
                    'registration': str(row[2]) if len(row) > 2 else '',
                    'cucar': str(row[1]) if len(row) > 1 else '',
                    'service': str(row[4]) if len(row) > 4 else '',
                    'status': str(row[5]) if len(row) > 5 else '',
                    'mc_fc': str(row[6]) if len(row) > 6 else '',
                    'category': category
                }
                vehicles.append(vehicle)
        
        # Sort vehicles by category and type
        vehicles.sort(key=lambda x: (x['category'], x['type']))
        
        logger.debug(f"Parsed {len(vehicles)} vehicles")
        if vehicles:
            logger.debug(f"First vehicle: {vehicles[0]}")
    except Exception as e:
        logger.error(f"Error parsing vehicle data: {str(e)}")
        logger.error(traceback.format_exc())
    return vehicles

def parse_point_fs_data(values):
    data = {
        'active_drivers': 0,
        'total_vehicles': 0,
        'available_vehicles': 0,
        'categories': {
            'FLOTTE': 0,
            'CHAUFFEUR': 0,
            'TRANSCO': 0,
            'DISPONIBLE': 0
        },
        'status': {
            'MC': 0,
            'FC': 0,
            'FRANCE_SERV': 0
        },
        'vehicle_types': [],
        'weekly_departures': 0,
        'daily_departures': 0,
        'weekly_stops': 0,
        'daily_stops': 0,
        'ca_semaine': 0,
        'ca_jour': 0
    }
    
    try:
        if not values:
            logger.error("No values received from Point FS sheet")
            return data

        logger.debug(f"Processing {len(values)} rows from Point FS")
        for row in values:
            if len(row) < 2:
                continue
                
            label = str(row[0]).lower() if row[0] else ''
            value = row[1] if len(row) > 1 else 0
            
            try:
                if isinstance(value, str):
                    value = value.replace('€', '').replace(',', '.').strip()
                    numeric_value = float(value) if '.' in value else int(value)
                else:
                    numeric_value = float(value) if isinstance(value, (int, float)) else 0
            except (ValueError, AttributeError):
                numeric_value = 0

            # Update category counts
            if 'flotte' in label:
                data['categories']['FLOTTE'] = numeric_value
            elif 'chauffeur' in label:
                data['categories']['CHAUFFEUR'] = numeric_value
            elif 'transco' in label:
                data['categories']['TRANSCO'] = numeric_value
            elif 'dispo' in label:
                data['categories']['DISPONIBLE'] = numeric_value

            # Update other metrics
            if 'chauffeur' in label and 'actif' in label:
                data['active_drivers'] = numeric_value
            elif 'vehicule' in label and 'total' in label:
                data['total_vehicles'] = numeric_value
            elif 'vehicule' in label and 'dispo' in label:
                data['available_vehicles'] = numeric_value
            elif any(v in label for v in ['chr', 'corolla', 'kona', 'model 3', 'swace', 'auris', 'isuzu']):
                if str(row[0]) not in data['vehicle_types']:
                    data['vehicle_types'].append(str(row[0]))
            elif 'depart' in label and 'semaine' in label:
                data['weekly_departures'] = numeric_value
            elif 'depart' in label and 'jour' in label:
                data['daily_departures'] = numeric_value
            elif 'stop' in label and 'semaine' in label:
                data['weekly_stops'] = numeric_value
            elif 'stop' in label and 'jour' in label:
                data['daily_stops'] = numeric_value
            elif 'ca s-1' in label:
                data['ca_semaine'] = numeric_value
            elif label.startswith('ca') and 'semaine' not in label:
                data['ca_jour'] = numeric_value
                
        logger.debug(f"Parsed Point FS data: {data}")
    except Exception as e:
        logger.error(f"Error parsing Point FS data: {str(e)}")
        logger.error(traceback.format_exc())
    return data

def parse_vehicle_with_immat(cell_value):
    """Helper function to parse vehicle type and immatriculation from a cell like 'CHR (GG441SX)'"""
    if not cell_value or '(' not in cell_value or ')' not in cell_value:
        return cell_value, ''
    
    try:
        # Split by opening parenthesis and remove closing parenthesis
        parts = cell_value.split('(')
        vehicle_type = parts[0].strip()
        immat = parts[1].replace(')', '').strip()
        return vehicle_type, immat
    except:
        return cell_value, ''

def get_sheet_names(service, spreadsheet_id):
    try:
        # Get spreadsheet metadata
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])
        sheet_names = [sheet['properties']['title'] for sheet in sheets]
        logger.debug(f"Available sheets: {sheet_names}")
        return sheet_names
    except Exception as e:
        logger.error(f"Error getting sheet names: {str(e)}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/dashboard-data')
def get_dashboard_data():
    try:
        service = get_google_sheets_service()
        if not service:
            logger.error("No service available")
            return jsonify({'error': 'Failed to initialize Google Sheets service'})

        try:
            logger.debug("Fetching data from Point FS sheet...")
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range="'Point FS'!A1:B50",
                valueRenderOption='UNFORMATTED_VALUE'
            ).execute()
            values = result.get('values', [])
            logger.debug(f"Got {len(values)} rows from Point FS sheet")
            logger.debug(f"First few rows: {values[:3] if values else 'No data'}")

            if not values:
                return jsonify({
                    'active_drivers': 0,
                    'total_vehicles': 0,
                    'available_vehicles': 0,
                    'categories': {
                        'FLOTTE': 0,
                        'CHAUFFEUR': 0,
                        'TRANSCO': 0,
                        'DISPONIBLE': 0
                    },
                    'status': {
                        'MC': 0,
                        'FC': 0,
                        'FRANCE_SERV': 0
                    },
                    'vehicle_types': [],
                    'weekly_departures': 0,
                    'daily_departures': 0,
                    'weekly_stops': 0,
                    'daily_stops': 0,
                    'ca_semaine': 0,
                    'ca_jour': 0
                })

            dashboard_data = parse_point_fs_data(values)
            return jsonify(dashboard_data)

        except Exception as e:
            logger.error(f"Error getting Point FS data: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'active_drivers': 0,
                'total_vehicles': 0,
                'available_vehicles': 0,
                'categories': {
                    'FLOTTE': 0,
                    'CHAUFFEUR': 0,
                    'TRANSCO': 0,
                    'DISPONIBLE': 0
                },
                'status': {
                    'MC': 0,
                    'FC': 0,
                    'FRANCE_SERV': 0
                },
                'vehicle_types': [],
                'weekly_departures': 0,
                'daily_departures': 0,
                'weekly_stops': 0,
                'daily_stops': 0,
                'ca_semaine': 0,
                'ca_jour': 0
            })

    except Exception as e:
        logger.error(f"Error in get_dashboard_data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)})

@app.route('/api/vehicles')
def get_vehicles():
    try:
        service = get_google_sheets_service()
        if not service:
            logger.error("No service available")
            return jsonify({'error': 'Service not available'})

        try:
            # Get all data from VÉHICULE sheet
            range_name = "'VÉHICULE'!A1:Z1000"
            logger.debug(f"Fetching data from range: {range_name}")
            
            try:
                result = service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=range_name,
                    valueRenderOption='FORMATTED_VALUE'
                ).execute()
                logger.debug(f"API Response: {result}")
            except Exception as api_error:
                logger.error(f"API Error: {str(api_error)}")
                return jsonify({'error': f'API Error: {str(api_error)}'})

            values = result.get('values', [])
            if not values:
                logger.error("No data found in sheet")
                return jsonify({'error': 'No data found'})

            # Initialize categories and stats
            categories = {
                'flotte': [],
                'chauffeur': [],
                'transco': [],
                'disponible_fs': [],
                'disponible_mc': [],
                'immo': [],
                'gestionnaire': [],
                'gratuit': []
            }
            
            stats = {
                'total': 0,
                'by_type': {},
                'by_category': {},
                'by_status': {}
            }

            # Process each section
            for row_index, row in enumerate(values[1:], start=1):  # Skip header row
                try:
                    # Flotte vehicles (columns A-C)
                    if len(row) >= 3 and row[0] and row[1]:
                        vehicle = {
                            'type': str(row[0]),
                            'immatriculation': str(row[1]),
                            'status': str(row[2]) if len(row) > 2 else '',
                            'category': 'flotte'
                        }
                        categories['flotte'].append(vehicle)
                        stats['total'] += 1
                        stats['by_type'][vehicle['type']] = stats['by_type'].get(vehicle['type'], 0) + 1
                        stats['by_category']['flotte'] = stats['by_category'].get('flotte', 0) + 1
                        if vehicle['status']:
                            stats['by_status'][vehicle['status']] = stats['by_status'].get(vehicle['status'], 0) + 1

                    # Disponible FS vehicles (column N)
                    if len(row) >= 14 and row[13] and str(row[13]).strip() != '0':
                        vehicle_type, immat = parse_vehicle_with_immat(str(row[13]))
                        if vehicle_type and immat:
                            vehicle = {
                                'type': vehicle_type,
                                'immatriculation': immat,
                                'cucar': '',
                                'status': 'Disponible FS',
                                'category': 'disponible_fs'
                            }
                            categories['disponible_fs'].append(vehicle)
                            stats['total'] += 1
                            stats['by_type'][vehicle_type] = stats['by_type'].get(vehicle_type, 0) + 1
                            stats['by_category']['disponible_fs'] = stats['by_category'].get('disponible_fs', 0) + 1

                    # Disponible MC vehicles (column Q)
                    if len(row) >= 17 and row[16] and str(row[16]).strip() != '0':
                        vehicle_type, immat = parse_vehicle_with_immat(str(row[16]))
                        if vehicle_type and immat:
                            vehicle = {
                                'type': vehicle_type,
                                'immatriculation': immat,
                                'cucar': '',
                                'status': 'Disponible MC',
                                'category': 'disponible_mc'
                            }
                            categories['disponible_mc'].append(vehicle)
                            stats['total'] += 1
                            stats['by_type'][vehicle_type] = stats['by_type'].get(vehicle_type, 0) + 1
                            stats['by_category']['disponible_mc'] = stats['by_category'].get('disponible_mc', 0) + 1

                    # IMMO vehicles (column T2)
                    if len(row) >= 20 and row[19] and str(row[19]).strip() != '0':
                        vehicle_type, immat = parse_vehicle_with_immat(str(row[19]))
                        if vehicle_type and immat:
                            vehicle = {
                                'type': vehicle_type,
                                'immatriculation': immat,
                                'cucar': '',
                                'status': 'IMMO',
                                'category': 'immo'
                            }
                            categories['immo'].append(vehicle)
                            stats['total'] += 1
                            stats['by_type'][vehicle_type] = stats['by_type'].get(vehicle_type, 0) + 1
                            stats['by_category']['immo'] = stats['by_category'].get('immo', 0) + 1

                    # Chauffeur vehicles (columns D-F)
                    if len(row) >= 6 and row[3] and row[4]:
                        vehicle = {
                            'type': str(row[3]),
                            'immatriculation': str(row[4]),
                            'status': str(row[5]) if len(row) > 5 else '',
                            'category': 'chauffeur'
                        }
                        categories['chauffeur'].append(vehicle)
                        stats['total'] += 1
                        stats['by_type'][vehicle['type']] = stats['by_type'].get(vehicle['type'], 0) + 1
                        stats['by_category']['chauffeur'] = stats['by_category'].get('chauffeur', 0) + 1
                        if vehicle['status']:
                            stats['by_status'][vehicle['status']] = stats['by_status'].get(vehicle['status'], 0) + 1

                    # Transco vehicles (columns G-I)
                    if len(row) >= 9 and row[6] and row[7]:
                        vehicle = {
                            'type': str(row[6]),
                            'immatriculation': str(row[7]),
                            'status': str(row[8]) if len(row) > 8 else '',
                            'category': 'transco'
                        }
                        categories['transco'].append(vehicle)
                        stats['total'] += 1
                        stats['by_type'][vehicle['type']] = stats['by_type'].get(vehicle['type'], 0) + 1
                        stats['by_category']['transco'] = stats['by_category'].get('transco', 0) + 1
                        if vehicle['status']:
                            stats['by_status'][vehicle['status']] = stats['by_status'].get(vehicle['status'], 0) + 1

                    # Gestionnaire vehicles (columns T-V)
                    if len(row) >= 22 and row[19]:
                        vehicle = {
                            'type': str(row[19]),
                            'immatriculation': str(row[20]) if len(row) > 20 else '',
                            'status': 'Gestionnaire',
                            'category': 'gestionnaire'
                        }
                        categories['gestionnaire'].append(vehicle)
                        stats['total'] += 1
                        stats['by_type'][vehicle['type']] = stats['by_type'].get(vehicle['type'], 0) + 1
                        stats['by_category']['gestionnaire'] = stats['by_category'].get('gestionnaire', 0) + 1

                    # Gratuit vehicles (columns W-Y)
                    if len(row) >= 25 and row[22]:
                        vehicle = {
                            'type': str(row[22]),
                            'immatriculation': str(row[23]) if len(row) > 23 else '',
                            'status': 'Gratuit',
                            'category': 'gratuit'
                        }
                        categories['gratuit'].append(vehicle)
                        stats['total'] += 1
                        stats['by_type'][vehicle['type']] = stats['by_type'].get(vehicle['type'], 0) + 1
                        stats['by_category']['gratuit'] = stats['by_category'].get('gratuit', 0) + 1

                except Exception as row_error:
                    logger.error(f"Error processing row {row}: {str(row_error)}")
                    continue

            # Add debug logging
            logger.debug("Disponible MC vehicles:")
            for vehicle in categories['disponible_mc']:
                logger.debug(f"  {vehicle}")

            return jsonify({
                'categories': categories,
                'stats': stats,
                'success': True
            })

        except Exception as e:
            logger.error(f"Error getting vehicle data: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': str(e)})

    except Exception as e:
        logger.error(f"Error in get_vehicles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)})

@app.route('/point_fs')
def point_fs():
    return render_template('point_fs.html')

@app.route('/get_point_fs_data')
def get_point_fs_data():
    try:
        service = get_google_sheets_service()
        if not service:
            logger.error("Failed to get Google Sheets service")
            return jsonify({})

        # Get all sheets to verify POINT FS exists
        sheets_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheet_titles = [sheet['properties']['title'] for sheet in sheets_metadata.get('sheets', [])]
        logger.debug("Available sheets: {}".format(sheet_titles))

        # Récupérer les données de la feuille POINT FS
        range_name = "'POINT FS'!B2:D45"  
        logger.debug("Fetching range: {}".format(range_name))
        
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        
        # Print detailed information about the data
        logger.debug("\n=== DATA FROM GOOGLE SHEETS ===")
        logger.debug("Total rows received: {}".format(len(values)))
        
        # Filter out empty rows and process the data
        processed_values = []
        for i, row in enumerate(values):
            logger.debug("Row {}: {}".format(i+2, row))  
            if row and any(cell.strip() for cell in row if isinstance(cell, str)):  
                processed_values.append(row)
        
        logger.debug("\nProcessed rows: {}".format(len(processed_values)))
        logger.debug("Processed values:")
        for row in processed_values:
            logger.debug(row)
        logger.debug("============================\n")

        return jsonify({'data': processed_values})

    except Exception as e:
        logger.error("Error fetching Point FS data: {}".format(str(e)))
        logger.error(traceback.format_exc())
        return jsonify({})

@app.route('/test')
def test_sheets():
    try:
        service = get_google_sheets_service()
        if not service:
            return jsonify({'error': 'No service available'})

        # Try to get spreadsheet info
        try:
            spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
            sheets = spreadsheet.get('sheets', [])
            sheet_names = [sheet['properties']['title'] for sheet in sheets]
            
            # Try to read data from VÉHICULE sheet
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range="'VÉHICULE'!A1:D5",  
                valueRenderOption='FORMATTED_VALUE'
            ).execute()
            
            return jsonify({
                'spreadsheet_title': spreadsheet.get('properties', {}).get('title'),
                'sheet_names': sheet_names,
                'data': result.get('values', []),
                'spreadsheet_id': SPREADSHEET_ID
            })
            
        except Exception as e:
            return jsonify({
                'error': str(e),
                'spreadsheet_id': SPREADSHEET_ID,
                'service_account': 'acc-s-feuille-de-calcul@centering-valve-448613-e3.iam.gserviceaccount.com'
            })

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    # Test connection on startup
    service = get_google_sheets_service()
    if not service:
        logger.error("Failed to initialize Google Sheets service on startup!")
    else:
        logger.info("Successfully connected to Google Sheets API")
    app.run(debug=True)
