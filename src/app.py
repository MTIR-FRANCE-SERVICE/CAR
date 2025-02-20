from flask import Flask, jsonify, render_template, request, redirect, url_for, send_from_directory
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
from functools import lru_cache
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Log to stdout for cloud deployment
)
logger = logging.getLogger(__name__)

# Print environment variables for debugging
logger.info("Environment variables check:")
logger.info(f"SPREADSHEET_ID: {'Set' if os.getenv('SPREADSHEET_ID') else 'Not set'}")
logger.info(f"GOOGLE_CREDENTIALS_JSON: {'Set' if os.getenv('GOOGLE_CREDENTIALS_JSON') else 'Not set'}")
logger.info(f"LOG_LEVEL: {os.getenv('LOG_LEVEL', 'Not set')}")

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')

# If GOOGLE_CREDENTIALS_JSON is set in environment, use it
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
logger.debug(f"Using Spreadsheet ID: {SPREADSHEET_ID}")

def get_google_sheets_service():
    try:
        # Get credentials from environment variable
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if not credentials_json:
            logger.error("GOOGLE_CREDENTIALS_JSON environment variable not set")
            return None

        logger.info("GOOGLE_CREDENTIALS_JSON is set")
        logger.debug(f"First 50 chars of credentials: {credentials_json[:50]}...")

        try:
            # Convert string to bytes for the private key
            creds_dict = json.loads(credentials_json)
            if 'private_key' in creds_dict:
                creds_dict['private_key'] = creds_dict['private_key'].encode('utf-8')
            logger.info("Successfully parsed credentials JSON")
        except Exception as e:
            logger.error(f"Error parsing GOOGLE_CREDENTIALS_JSON: {str(e)}")
            return None

        service_email = creds_dict.get('client_email')
        project_id = creds_dict.get('project_id')
        logger.info(f"Service account email: {service_email}")
        logger.info(f"Project ID: {project_id}")

        # Create credentials from the dictionary
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=SCOPES
        )
        logger.info("Successfully created credentials object")
        
        service = build('sheets', 'v4', credentials=creds)
        logger.info("Successfully built sheets service")
        
        return service
            
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
        
        logger.debug("Parsed {} vehicles".format(len(vehicles)))
        if vehicles:
            logger.debug("First vehicle: {}".format(vehicles[0]))
    except Exception as e:
        logger.error("Error parsing vehicle data: {}".format(str(e)))
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

        logger.debug("Processing {} rows from Point FS".format(len(values)))
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
                
        logger.debug("Parsed Point FS data: {}".format(data))
    except Exception as e:
        logger.error("Error parsing Point FS data: {}".format(str(e)))
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
        logger.info(f"Attempting to get sheet names for spreadsheet: {spreadsheet_id}")
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = result.get('sheets', [])
        sheet_names = [sheet['properties']['title'] for sheet in sheets]
        logger.info(f"Found sheets: {sheet_names}")
        return sheet_names
    except Exception as e:
        logger.error(f"Error getting sheet names: {str(e)}")
        logger.error(traceback.format_exc())
        return []

last_fetch_time = None
cached_vehicles_data = None

def get_cached_vehicles_data():
    global last_fetch_time, cached_vehicles_data
    
    # If we have cached data and it's less than 30 seconds old, return it
    if last_fetch_time and cached_vehicles_data:
        if datetime.now() - last_fetch_time < timedelta(seconds=30):
            return cached_vehicles_data
    
    return None

def set_cached_vehicles_data(data):
    global last_fetch_time, cached_vehicles_data
    last_fetch_time = datetime.now()
    cached_vehicles_data = data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/dashboard-data')
def get_dashboard_data():
    try:
        logger.info("Starting get_dashboard_data")
        service = get_google_sheets_service()
        if not service:
            logger.error("Failed to get Google Sheets service")
            return jsonify({'error': 'Failed to initialize Google Sheets service'}), 500

        # Fetch data from Point FS
        logger.info("Fetching data from Point FS sheet")
        result_fs = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="'Point FS'!A1:D50",
            valueRenderOption='UNFORMATTED_VALUE'
        ).execute()
        logger.info(f"Data fetched successfully from Point FS: {result_fs}")

        values_fs = result_fs.get('values', [])
        if not values_fs:
            logger.warning("No data found in Point FS sheet")
            return jsonify({'error': 'No data found in Point FS'}), 404

        logger.info(f"Processing {len(values_fs)} rows of data from Point FS")
        data_fs = []
        for row in values_fs:
            if len(row) >= 2:
                data_fs.append({
                    'name': str(row[0]),
                    'value': row[1]
                })
        logger.info(f"Processed data from Point FS: {data_fs}")

        # Fetch data from Point MC
        logger.info("Fetching data from Point MC sheet")
        result_mc = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="'POINT MC'!A1:D50",  # Adjust range as needed
            valueRenderOption='UNFORMATTED_VALUE'
        ).execute()
        logger.info(f"Data fetched successfully from Point MC: {result_mc}")

        values_mc = result_mc.get('values', [])
        if not values_mc:
            logger.warning("No data found in Point MC sheet")
            return jsonify({'error': 'No data found in Point MC'}), 404

        logger.info(f"Processing {len(values_mc)} rows of data from Point MC")
        data_mc = []
        for row in values_mc:
            if len(row) >= 2:
                data_mc.append({
                    'name': str(row[0]),
                    'value': row[1]
                })
        logger.info(f"Processed data from Point MC: {data_mc}")

        # Combine data from both sheets
        combined_data = {
            'point_fs': data_fs,
            'point_mc': data_mc
        }

        return jsonify(combined_data)

    except Exception as e:
        logger.error(f"Error in get_dashboard_data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/vehicles')
def get_vehicles():
    try:
        # Check cache first
        cached_data = get_cached_vehicles_data()
        if cached_data:
            return jsonify(cached_data)

        service = get_google_sheets_service()
        if not service:
            logger.error("No service available")
            return jsonify({'error': 'Service not available'})

        try:
            # Get only the needed columns
            ranges = [
                "'VÉHICULE'!A2:C1000",  # Flotte
                "'VÉHICULE'!D2:F1000",  # Chauffeur
                "'VÉHICULE'!G2:I1000",  # Transco
                "'VÉHICULE'!N2:N1000",  # Disponible FS
                "'VÉHICULE'!Q2:Q1000",  # Disponible MC
                "'VÉHICULE'!T2:U1000"   # IMMO (Type et Immatriculation)
            ]
            
            try:
                result = service.spreadsheets().values().batchGet(
                    spreadsheetId=SPREADSHEET_ID,
                    ranges=ranges,
                    valueRenderOption='FORMATTED_VALUE'
                ).execute()
                
                valueRanges = result.get('valueRanges', [])
                if not valueRanges:
                    logger.error("No data found in sheet")
                    return jsonify({'error': 'No data found'})
                
            except Exception as api_error:
                logger.error("API Error: {}".format(str(api_error)))
                return jsonify({'error': 'API Error: {}'.format(str(api_error))})

            # Initialize categories
            categories = {
                'flotte': [],
                'chauffeur': [],
                'transco': [],
                'disponible_fs': [],
                'disponible_mc': [],
                'immo': [],
            }
            
            # Process Flotte (A:C)
            if len(valueRanges) > 0 and valueRanges[0].get('values'):
                for row in valueRanges[0]['values']:
                    if row and len(row) >= 2 and row[0] and row[1]:
                        categories['flotte'].append({
                            'type': str(row[0]),
                            'immatriculation': str(row[1]),
                            'status': str(row[2]) if len(row) > 2 else '',
                            'category': 'flotte'
                        })

            # Process Chauffeur (D:F)
            if len(valueRanges) > 1 and valueRanges[1].get('values'):
                for row in valueRanges[1]['values']:
                    if row and len(row) >= 2 and row[0] and row[1]:
                        categories['chauffeur'].append({
                            'type': str(row[0]),
                            'immatriculation': str(row[1]),
                            'status': str(row[2]) if len(row) > 2 else '',
                            'category': 'chauffeur'
                        })

            # Process Transco (G:I)
            if len(valueRanges) > 2 and valueRanges[2].get('values'):
                for row in valueRanges[2]['values']:
                    if row and len(row) >= 2 and row[0] and row[1]:
                        categories['transco'].append({
                            'type': str(row[0]),
                            'immatriculation': str(row[1]),
                            'status': str(row[2]) if len(row) > 2 else '',
                            'category': 'transco'
                        })

            # Process Disponible FS (N)
            if len(valueRanges) > 3 and valueRanges[3].get('values'):
                for row in valueRanges[3]['values']:
                    if row and row[0] and str(row[0]).strip() != '0':
                        vehicle_type, immat = parse_vehicle_with_immat(str(row[0]))
                        if vehicle_type and immat:
                            categories['disponible_fs'].append({
                                'type': vehicle_type,
                                'immatriculation': immat,
                                'status': 'Disponible FS',
                                'category': 'disponible_fs'
                            })

            # Process Disponible MC (Q)
            if len(valueRanges) > 4 and valueRanges[4].get('values'):
                for row in valueRanges[4]['values']:
                    if row and row[0] and str(row[0]).strip() != '0':
                        vehicle_type, immat = parse_vehicle_with_immat(str(row[0]))
                        if vehicle_type and immat:
                            categories['disponible_mc'].append({
                                'type': vehicle_type,
                                'immatriculation': immat,
                                'status': 'Disponible MC',
                                'category': 'disponible_mc'
                            })

            # Process IMMO (T:U)
            if len(valueRanges) > 5 and valueRanges[5].get('values'):
                for row in valueRanges[5]['values']:
                    if row and len(row) >= 2 and row[0] and row[1]:  # Vérifie les colonnes T et U
                        vehicle_type = str(row[0])
                        immat = str(row[1])
                        if vehicle_type and immat and vehicle_type.strip() != '0' and immat.strip() != '0':
                            categories['immo'].append({
                                'type': vehicle_type,
                                'immatriculation': immat,
                                'status': 'IMMO',
                                'category': 'immo'
                            })

            response_data = {
                'categories': categories,
                'success': True
            }

            # Cache the response
            set_cached_vehicles_data(response_data)

            return jsonify(response_data)

        except Exception as e:
            logger.error("Error getting vehicle data: {}".format(str(e)))
            logger.error(traceback.format_exc())
            return jsonify({'error': str(e)})

    except Exception as e:
        logger.error("Error in get_vehicles: {}".format(str(e)))
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
        range_name = "'POINT FS'!B2:D71"  
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

@app.route('/api/immo')
def get_immo():
    try:
        service = get_google_sheets_service()
        if not service:
            logger.error("No service available")
            return jsonify({'error': 'Service not available'})

        # Get IMMO data specifically from T2:U55
        range_name = 'VÉHICULE!T2:U55'
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueRenderOption='FORMATTED_VALUE'
            ).execute()
        except Exception as api_error:
            logger.error("API Error: {}".format(str(api_error)))
            return jsonify({'error': 'API Error: {}'.format(str(api_error))})

        values = result.get('values', [])
        if not values:
            return jsonify({'count': 0, 'data': []})

        immo_count = 0
        immo_data = []

        for row in values:
            if row and len(row) >= 1 and row[0].strip():  # Check if we have data in first column
                immo_count += 1
                immo_data.append({
                    'vehicle': row[0],
                    'status': row[1] if len(row) > 1 else ''
                })

        return jsonify({
            'count': immo_count,
            'data': immo_data
        })

    except Exception as e:
        logger.error("Error in get_immo: {}".format(str(e)))
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)})

@app.route('/api/dashboard')
def get_dashboard():
    try:
        service = get_google_sheets_service()
        if not service:
            return jsonify({'error': 'Failed to connect to Google Sheets'}), 500

        # Get all data from VÉHICULE sheet
        range_name = 'VÉHICULE!A2:U1000'  # Updated to include all needed columns A through U
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueRenderOption='FORMATTED_VALUE'
            ).execute()
            logger.debug(f"Successfully fetched data from {range_name}")
        except Exception as api_error:
            logger.error(f"Error fetching data from {range_name}: {str(api_error)}")
            return jsonify({'error': f'API Error: {str(api_error)}'}), 500

        values = result.get('values', [])
        if not values:
            logger.warning("No data found in VÉHICULE sheet")
            return jsonify({
                'flotte': 0,
                'chauffeur': 0,
                'transco': 0,
                'disponible': 0,
                'immo': 0
            })

        # Initialize counters
        stats = {
            'flotte': 0,
            'chauffeur': 0,
            'transco': 0,
            'disponible': 0,
            'immo': 0
        }

        # Process each row
        for row in values:
            try:
                # Flotte vehicles (columns A-C)
                if len(row) >= 3 and row[0] and row[1]:  # Check columns A and B
                    stats['flotte'] += 1
                
                # Chauffeur vehicles (columns D-F)
                if len(row) >= 6 and row[3] and row[4]:  # Check columns D and E
                    stats['chauffeur'] += 1
                
                # Transco vehicles (columns G-I)
                if len(row) >= 9 and row[6] and row[7]:  # Check columns G and H
                    stats['transco'] += 1

                # Disponible vehicles (columns N and Q)
                if len(row) >= 14 and row[13] and str(row[13]).strip() != '0':  # Column N
                    stats['disponible'] += 1
                if len(row) >= 17 and row[16] and str(row[16]).strip() != '0':  # Column Q
                    stats['disponible'] += 1

                # IMMO vehicles (columns T-U)
                if len(row) >= 21 and row[19] and row[20]:  # Check both T and U columns
                    stats['immo'] += 1

            except Exception as row_error:
                logger.error(f"Error processing row: {str(row_error)}")
                continue

        logger.info(f"Dashboard stats: {stats}")
        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error in get_dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

def parse_point_mc_data(values):
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
            logger.error("No values received from Point MC sheet")
            return data

        logger.debug("Processing {} rows from Point MC".format(len(values)))
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
                
        logger.debug("Parsed Point MC data: {}".format(data))
    except Exception as e:
        logger.error("Error parsing Point MC data: {}".format(str(e)))
        logger.error(traceback.format_exc())
    return data

@app.route('/point_mc')
def point_mc():
    return render_template('point_mc.html')

@app.route('/get_point_mc_data')
def get_point_mc_data():
    try:
        service = get_google_sheets_service()
        if not service:
            logger.error("Failed to get Google Sheets service")
            return jsonify({})

        # Get all sheets to verify POINT MC exists
        sheets_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheet_titles = [sheet['properties']['title'] for sheet in sheets_metadata.get('sheets', [])]
        logger.debug("Available sheets: {}".format(sheet_titles))

        # Récupérer les données de la feuille POINT FS
        range_name = "'POINT MC'!B2:D61"  
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
        logger.error("Error fetching Point MC data: {}".format(str(e)))
        logger.error(traceback.format_exc())
        return jsonify({})        
if __name__ == '__main__':
    # Test connection on startup
    service = get_google_sheets_service()
    if not service:
        logger.error("Failed to initialize Google Sheets service on startup!")
    else:
        logger.info("Successfully connected to Google Sheets API")
    app.run(debug=True)
