#api_client.py
import requests
from requests.auth import HTTPBasicAuth
import json
import logging
from config import API_KEY, API_SECRET, BASE_URL

def get_asset_list():
    endpoint = '/asset/getlist'
    url = f"{BASE_URL}{endpoint}"
    auth = HTTPBasicAuth(API_KEY, API_SECRET)

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    logging.debug(f"Requesting URL: {url}")
    logging.debug(f"Using Basic Auth with API_KEY: {repr(API_KEY)}")

    try:
        response = requests.get(url, headers=headers, auth=auth)
        response.raise_for_status()
        asset_list = response.json()

        # Log the fetched asset list
        logging.debug(f"Fetched asset list: {json.dumps(asset_list, indent=2)}")
        return asset_list
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error fetching asset list with Basic Auth: {e}")
        logging.error(f"Response text: {response.text}")
        return []
    except Exception as e:
        logging.error(f"Error fetching asset list with Basic Auth: {e}")
        return []

def get_account_balances():
    endpoint = '/balances'
    url = f"{BASE_URL}{endpoint}"
    auth = HTTPBasicAuth(API_KEY, API_SECRET)

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    logging.debug(f"Requesting URL: {url}")
    logging.debug(f"Using Basic Auth with API_KEY: {repr(API_KEY)}")

    try:
        response = requests.get(url, headers=headers, auth=auth)
        response.raise_for_status()
        balances = response.json()

        # Log the fetched balances
        logging.debug(f"Fetched account balances: {json.dumps(balances, indent=2)}")
        return balances
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error fetching account balances with Basic Auth: {e}")
        logging.error(f"Response text: {response.text}")
        return None
    except Exception as e:
        logging.error(f"Error fetching account balances with Basic Auth: {e}")
        return None

def get_price_lookup(asset_list):
    return {asset['ticker']: float(asset['usdValue']) for asset in asset_list if 'usdValue' in asset}

if __name__ == '__main__':
    # Set up logging to display debug information
    logging.basicConfig(level=logging.DEBUG)

    # Test the get_account_balances function
    balances = get_account_balances()
    if balances:
        print("Successfully fetched account balances:")
        print(json.dumps(balances, indent=2))
    else:
        print("Failed to fetch account balances.")

    # Test the get_asset_list function
    asset_list = get_asset_list()
    if asset_list:
        print("Successfully fetched asset list:")
        print(json.dumps(asset_list, indent=2))
    else:
        print("Failed to fetch asset list.")

    # Test the get_price_lookup function
    price_lookup = get_price_lookup(asset_list)
    if price_lookup:
        print("Successfully created price lookup:")
        print(json.dumps(price_lookup, indent=2))
    else:
        print("Failed to create price lookup.")
