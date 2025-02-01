# risk_management.py
import pandas as pd
from ta.volatility import AverageTrueRange
import logging

def calculate_stop_loss(entry_price, risk_percentage):
    return entry_price * (1 - risk_percentage)

def calculate_take_profit(entry_price, reward_percentage):
    return entry_price * (1 + reward_percentage)

def calculate_dynamic_atr_multiplier(data, volatility_window=14):
    """
    Adjust ATR multiplier based on market volatility using standard deviation of price returns.
    Higher volatility leads to a higher ATR multiplier.
    """
    # Calculate price returns (percentage change)
    data['price_return'] = data['close'].pct_change()

    # Calculate volatility (standard deviation of returns)
    volatility = data['price_return'].rolling(window=volatility_window).std().iloc[-1]

    # Normalize volatility for ATR multiplier adjustment (e.g., higher volatility -> higher multiplier)
    volatility_factor = 1 + volatility * 10  # Example: scale the volatility factor for ATR multiplier

    # Example: Adjust the ATR multiplier based on volatility
    atr_multiplier = max(1, volatility_factor)  # Ensure multiplier doesn't go below 1

    logging.debug(f"Calculated dynamic ATR multiplier: {atr_multiplier} based on volatility: {volatility}")
    
    return atr_multiplier

def apply_risk_management(data, account_balance, max_risk, atr_window=7, available_balance=None):
    logging.debug(f"Data received for risk management:\n{data.head()}")
    logging.debug(f"Column names: {data.columns}")

    # Check for required columns
    if 'close' not in data.columns or 'high' not in data.columns or 'low' not in data.columns:
        logging.error("Required columns ('close', 'high', 'low') are missing in the data.")
        return data

    # Convert columns to float
    try:
        data['high'] = data['high'].astype(float)
        data['low'] = data['low'].astype(float)
        data['close'] = data['close'].astype(float)
    except ValueError as e:
        logging.error(f"Error converting data to float: {e}")
        return data

    data = data.dropna(subset=['high', 'low', 'close'])

    # Check if enough data points to calculate ATR
    if len(data) < atr_window:
        logging.warning(f"Not enough data points to calculate ATR. Required: {atr_window}, Available: {len(data)}")
        data['atr'] = float('nan')
        data['position_size'] = 0
        return data

    # Calculate ATR
    atr_indicator = AverageTrueRange(high=data['high'], low=data['low'], close=data['close'], window=atr_window)
    data['atr'] = atr_indicator.average_true_range()

    # Calculate dynamic ATR multiplier based on market volatility
    atr_multiple = calculate_dynamic_atr_multiplier(data)

    # Check for valid ATR value
    if data['atr'].iloc[-1] == 0 or pd.isna(data['atr'].iloc[-1]):
        logging.warning("ATR value is zero or NaN, unable to calculate position size.")
        data['position_size'] = 0
        return data

    # Calculate risk amount
    if isinstance(max_risk, float) and max_risk < 1:
        risk_amount = account_balance * max_risk
    else:
        risk_amount = min(max_risk, account_balance)

    # Calculate position size
    adjusted_atr = data['atr'].iloc[-1] * atr_multiple
    position_size = risk_amount / adjusted_atr
    current_price = data['close'].iloc[-1]

    # Adjust position size to fit balance
    if position_size * current_price > risk_amount:
        logging.debug("Calculated position size exceeds risk amount. Adjusting position size to fit balance.")
        position_size = risk_amount / current_price

    # Further adjust based on available balance
    if available_balance is not None:
        max_affordable_position_size = available_balance / current_price
        if position_size > max_affordable_position_size:
            logging.debug(f"Available balance (${available_balance}) is less than required for position size. Adjusting to {max_affordable_position_size} units.")
            position_size = max_affordable_position_size

    data['position_size'] = position_size

    logging.debug(f"Calculated position size with dynamic ATR multiplier: {position_size}")
    return data
