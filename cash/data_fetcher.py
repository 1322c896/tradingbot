#data_fetcher.py
import requests
import logging
import pandas as pd
from datetime import datetime, timedelta
from config import API_KEY, API_SECRET, BASE_URL

def get_historical_data(symbol):
    logging.info(f"Fetching historical data for {symbol}...")
    
    df = fetch_historical_data(symbol, days=90)  # Ensure the period does not exceed 90 days
    
    if df.empty:
        logging.warning(f"No historical data for {symbol}. Skipping.")
    else:
        logging.info(f"Successfully fetched historical data for {symbol}.")
    
    if not df.empty:
        logging.debug(f"First 5 rows of historical data for {symbol}: \n{df.head()}")
        logging.debug(f"Column names: {df.columns}")

    return df

def fetch_historical_data(symbol, resolution='1440', days=90):
    endpoint = '/market/candles'
    url = f'{BASE_URL}{endpoint}'
    
    current_time = datetime.utcnow()
    from_time = current_time - timedelta(days=days)
    from_timestamp = int(from_time.timestamp() * 1000)
    to_timestamp = int(current_time.timestamp() * 1000)
    
    params = {
        'symbol': symbol,
        'from': from_timestamp,
        'to': to_timestamp,
        'resolution': resolution,
        'countBack': days,
        'firstDataRequest': 1
    }
    
    headers = {
        'accept': 'application/json',
        'X-API-KEY': API_KEY,
        'X-API-SECRET': API_SECRET
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'bars' in data:
            df = pd.DataFrame(data['bars'])
            df.columns = ['time', 'close', 'open', 'high', 'low', 'volume']  # Use lowercase
            
            # Convert 'time' column to datetime
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            
            # **Set 'time' as the index**
            df.set_index('time', inplace=True)
            
            # **Ensure the index is timezone-aware (UTC)**
            df.index = df.index.tz_localize('UTC')
            
            return df
        else:
            logging.warning(f"No candle data returned for {symbol}.")
            return pd.DataFrame()
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching historical data for {symbol}: {e}")
        return pd.DataFrame()


