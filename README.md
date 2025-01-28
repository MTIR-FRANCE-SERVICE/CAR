# Fleet Management Dashboard

A modern web application for managing vehicle fleet operations with Google Sheets integration.

## Features

- Real-time connection to Google Sheets
- Interactive dashboard with key metrics
- Vehicle fleet management
- Point FS operations overview
- Mobile-friendly responsive design
- Automatic data synchronization

## Prerequisites

- Python 3.8+
- Google Cloud Platform account with Sheets API enabled
- Google Service Account credentials

## Setup

1. Create a virtual environment and activate it:
```bash
python -m venv venv
.\venv\Scripts\activate  # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up Google Sheets API:
   - Create a project in Google Cloud Console
   - Enable Google Sheets API
   - Create a Service Account and download credentials
   - Place the credentials file in `src/config/credentials.json`

4. Create a `.env` file in the root directory with the following:
```
SPREADSHEET_ID=your_spreadsheet_id
SECRET_KEY=your_secret_key
```

5. Run the application:
```bash
python src/app.py
```

## Project Structure

```
fleet-management/
├── requirements.txt
├── README.md
├── .env
└── src/
    ├── app.py
    ├── config/
    │   └── credentials.json
    ├── static/
    │   ├── css/
    │   │   └── style.css
    │   └── js/
    │       └── main.js
    └── templates/
        └── index.html
```

## Configuration

1. Update the `SPREADSHEET_ID` in `.env` to point to your Google Sheet
2. Adjust the sheet ranges in `app.py` to match your spreadsheet structure
3. Customize the UI elements in `templates/index.html` as needed

## Usage

1. Access the dashboard at `http://localhost:5000`
2. Use the sidebar navigation to switch between different views
3. Apply filters to sort and find specific vehicles
4. Monitor real-time updates from the Google Sheet

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
