# config.py

import os
import yaml

# Load configuration from YAML file
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# API Credentials
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')

if not API_KEY or not API_SECRET:
    raise ValueError("API_KEY and API_SECRET must be set as environment variables.")

# API Base URLs
BASE_URL = config['api']['base_url']
WEBSOCKET_URL = config['api'].get('websocket_url', 'wss://api.xeggex.com')

USE_WEBSOCKET_FOR_ORDERS = True  # Set to False if you prefer using REST API


# Default Account Settings
ACCOUNT_BALANCE = config['account_balance']
MAX_RISK = config['max_risk']

# Strategies Configuration
STRATEGIES_CONFIG = config['strategies']

# Sleep Intervals
SLEEP_INTERVALS = config['sleep_intervals']
