# strategies.py
import logging
import numpy as np
import ta
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
from config import STRATEGIES_CONFIG

def analyze_orderbook_imbalance(orderbook):
    total_bids = sum(float(bid['quantity']) for bid in orderbook['bids'])
    total_asks = sum(float(ask['quantity']) for ask in orderbook['asks'])
    if total_bids + total_asks == 0:
        return 0  # Avoid division by zero
    imbalance = (total_bids - total_asks) / (total_bids + total_asks)
    return imbalance

def sanitize_signal(data):
    # Ensures that Signal contains only valid values: -1, 0, or 1
    data['signal'] = data['signal'].apply(lambda x: 0 if x not in [-1, 0, 1] else x)
    return data

def sma_crossover_strategy(data, params):
    logging.info("Applying SMA Crossover Strategy")
    short_window = params.get('short_window', 20)
    long_window = params.get('long_window', 50)

    data['sma_short'] = data['close'].rolling(window=short_window).mean()
    data['sma_long'] = data['close'].rolling(window=long_window).mean()
    data['signal'] = 0
    data.loc[data.index[long_window:], 'signal'] = np.where(
        data['sma_short'][long_window:] > data['sma_long'][long_window:], 1, -1
    )

    # Sanitize Signal to ensure only -1, 0, or 1 are present
    data = sanitize_signal(data)

    data['positions'] = data['signal'].diff()
    logging.debug(f"SMA Crossover Strategy Signals: {data[['sma_short', 'sma_long', 'signal']].tail()}")
    return data

def rsi_strategy(data, params):
    logging.info("Applying RSI Strategy")
    window = params.get('window', 14)
    overbought = params.get('overbought', 70)
    oversold = params.get('oversold', 30)

    rsi_indicator = RSIIndicator(close=data['close'], window=window)
    data['rsi'] = rsi_indicator.rsi()

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        data['rsi'] < oversold, 1,
        np.where(data['rsi'] > overbought, -1, 0)
    )

    # Sanitize Signal to ensure only -1, 0, or 1 are present
    data = sanitize_signal(data)

    data['positions'] = data['signal'].diff()
    logging.debug(f"RSI Strategy Signals: {data[['rsi', 'signal']].tail()}")
    return data

def macd_strategy(data, params):
    logging.info("Applying MACD Strategy")
    short_window = params.get('short_window', 12)
    long_window = params.get('long_window', 26)
    signal_window = params.get('signal_window', 9)

    macd_indicator = MACD(
        close=data['close'],
        window_slow=long_window,
        window_fast=short_window,
        window_sign=signal_window
    )
    data['macd'] = macd_indicator.macd()
    data['signal_line'] = macd_indicator.macd_signal()

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        data['macd'] > data['signal_line'], 1,
        np.where(data['macd'] < data['signal_line'], -1, 0)
    )

    # Sanitize Signal to ensure only -1, 0, or 1 are present
    data = sanitize_signal(data)

    data['positions'] = data['signal'].diff()
    logging.debug(f"MACD Strategy Signals: {data[['macd', 'signal_line', 'signal']].tail()}")
    return data

def bollinger_bands_strategy(data, params):
    logging.info("Applying Bollinger Bands Strategy")
    window = params.get('window', 20)
    num_std_dev = params.get('num_std_dev', 2)

    bb_indicator = BollingerBands(
        close=data['close'],
        window=window,
        window_dev=num_std_dev
    )
    data['bb_middle'] = bb_indicator.bollinger_mavg()
    data['bb_upper'] = bb_indicator.bollinger_hband()
    data['bb_lower'] = bb_indicator.bollinger_lband()

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        data['close'] < data['bb_lower'], 1,
        np.where(data['close'] > data['bb_upper'], -1, 0)
    )

    # Sanitize Signal to ensure only -1, 0, or 1 are present
    data = sanitize_signal(data)

    data['positions'] = data['signal'].diff()
    logging.debug(f"Bollinger Bands Strategy Signals: {data[['bb_upper', 'bb_lower', 'signal']].tail()}")
    return data

def combined_strategy(data, params):
    logging.info("Applying Combined Strategy")
    sma_short_window = params.get('sma_short_window', 20)
    sma_long_window = params.get('sma_long_window', 50)
    rsi_window = params.get('rsi_window', 14)
    rsi_overbought = params.get('rsi_overbought', 70)
    rsi_oversold = params.get('rsi_oversold', 30)
    macd_short_window = params.get('macd_short_window', 12)
    macd_long_window = params.get('macd_long_window', 26)
    macd_signal_window = params.get('macd_signal_window', 9)

    data['sma_short'] = data['close'].rolling(window=sma_short_window).mean()
    data['sma_long'] = data['close'].rolling(window=sma_long_window).mean()
    sma_signal = np.where(data['sma_short'] > data['sma_long'], 1, -1)

    rsi_indicator = RSIIndicator(close=data['close'], window=rsi_window)
    data['rsi'] = rsi_indicator.rsi()
    rsi_signal = np.where(
        data['rsi'] < rsi_oversold, 1,
        np.where(data['rsi'] > rsi_overbought, -1, 0)
    )

    macd_indicator = MACD(
        close=data['close'],
        window_slow=macd_long_window,
        window_fast=macd_short_window,
        window_sign=macd_signal_window
    )
    data['macd'] = macd_indicator.macd()
    data['signal_line'] = macd_indicator.macd_signal()
    macd_signal = np.where(
        data['macd'] > data['signal_line'], 1,
        np.where(data['macd'] < data['signal_line'], -1, 0)
    )

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        (sma_signal == 1) & (rsi_signal == 1) & (macd_signal == 1), 1,
        np.where((sma_signal == -1) & (rsi_signal == -1) & (macd_signal == -1), -1, 0)
    )

    # Sanitize Signal to ensure only -1, 0, or 1 are present
    data = sanitize_signal(data)

    data['positions'] = data['signal'].diff()
    logging.info(f"Combined Strategy Signals: {data[['sma_short', 'sma_long', 'rsi', 'macd', 'signal']].tail()}")
    return data

def sma_crossover_with_orderbook_strategy(data, orderbook, params):
    logging.info("Applying SMA Crossover with Order Book Strategy")
    short_window = params.get('short_window', 5)
    long_window = params.get('long_window', 10)
    imbalance_threshold = params.get('imbalance_threshold', 0.03)

    data['sma_short'] = data['close'].rolling(window=short_window).mean()
    data['sma_long'] = data['close'].rolling(window=long_window).mean()

    data['signal'] = 0
    data.loc[data.index[long_window:], 'signal'] = np.where(
        data['sma_short'][long_window:] > data['sma_long'][long_window:], 1, -1
    )

    imbalance = analyze_orderbook_imbalance(orderbook)

    if imbalance > imbalance_threshold:
        data['signal'] = data['signal'].apply(lambda x: x if x == 1 else 0)
    elif imbalance < -imbalance_threshold:
        data['signal'] = data['signal'].apply(lambda x: x if x == -1 else 0)
    else:
        data['signal'] = 0

    # Sanitize Signal to ensure only -1, 0, or 1 are present
    data = sanitize_signal(data)

    data['positions'] = data['signal'].diff()
    logging.debug(f"SMA Crossover with Order Book Strategy Signals: {data[['sma_short', 'sma_long', 'signal']].tail()}")
    return data

def sanitize_signal(data):
    data['signal'] = data['signal'].apply(lambda x: x if x in [-1, 1, 0] else 0)
    return data

def ema_crossover_scalping_strategy(data, params):
    logging.info("Applying EMA Crossover Scalping Strategy")
    logging.debug(f"Data columns before EMA calculation: {data.columns}")

    short_window = params.get('short_window', 5)
    long_window = params.get('long_window', 15)
    signal_threshold = params.get('signal_threshold', 0.005)  # Adjusted threshold

    # Ensure column names are in lowercase
    data.columns = data.columns.str.lower()
    logging.debug(f"Data columns after conversion to lowercase: {data.columns}")

    # Calculate the short-term and long-term EMAs
    data['ema_short'] = data['close'].ewm(span=short_window, adjust=False).mean()
    data['ema_long'] = data['close'].ewm(span=long_window, adjust=False).mean()

    # Calculate RSI using ta library
    rsi_period = params.get('rsi_period', 14) #  period rsi adjust as needed (typical 14)
    rsi_indicator = RSIIndicator(close=data['close'], window=rsi_period)
    data['rsi'] = rsi_indicator.rsi()

    # Generate trading signals based on EMA crossover and RSI confirmation
    data['signal'] = 0
    data.loc[data.index[long_window:], 'signal'] = np.where(
        (data['ema_short'][long_window:] - data['ema_long'][long_window:]) > signal_threshold, 1,
        np.where((data['ema_short'][long_window:] - data['ema_long'][long_window:]) < -signal_threshold, -1, 0)
    )

    # Confirm signals with RSI: only take long trades if RSI < 70 and short trades if RSI > 30
    data['signal'] = np.where(
        (data['signal'] == 1) & (data['rsi'] < 70), 1,
        np.where((data['signal'] == -1) & (data['rsi'] > 30), -1, 0)
    )

    # Debugging before sanitizing
    logging.debug(f"Signals before sanitizing: {data['signal'].unique()}")

    # Sanitize Signal to ensure only -1, 0, or 1 are present
    data = sanitize_signal(data)

    # Debugging after sanitizing
    logging.debug(f"Sanitized Signals: {data['signal'].unique()}")

    # Generate position sizes based on signal changes
    data['positions'] = data['signal'].diff()

    # Ensure positions are only -1, 1, or 0
    data['positions'] = data['positions'].apply(lambda x: x if x in [-1, 1, 0] else 0)
    
    # Debugging positions
    logging.debug(f"Positions: {data['positions'].unique()}")

    logging.debug(f"EMA Crossover Scalping Strategy Signals: {data[['ema_short', 'ema_long', 'signal', 'positions', 'rsi']].tail()}")
    return data



def alma_strategy(data, params):
    logging.info("Applying ALMA Strategy")
    window = params.get('window', 9)
    offset = params.get('offset', 0.85)
    sigma = params.get('sigma', 6)

    data['alma'] = ta.alma(data['close'], window=window, offset=offset, sigma=sigma)

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        data['close'] > data['alma'], 1,
        np.where(data['close'] < data['alma'], -1, 0)
    )

    data = sanitize_signal(data)
    data['positions'] = data['signal'].diff()
    logging.debug(f"ALMA Strategy Signals: {data[['alma', 'signal']].tail()}")
    return data

def ama_strategy(data, params):
    logging.info("Applying Adaptive Moving Average (AMA) Strategy")
    window = params.get('window', 10)
    pow1 = params.get('pow1', 2)
    pow2 = params.get('pow2', 30)

    data['ama'] = ta.kama(data['close'], length=window, pow1=pow1, pow2=pow2)

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        data['close'] > data['ama'], 1,
        np.where(data['close'] < data['ama'], -1, 0)
    )

    data = sanitize_signal(data)
    data['positions'] = data['signal'].diff()
    logging.debug(f"AMA Strategy Signals: {data[['ama', 'signal']].tail()}")
    return data

def ichimoku_strategy(data, params):
    logging.info("Applying Ichimoku Cloud Strategy")
    window1 = params.get('window1', 9)
    window2 = params.get('window2', 26)
    window3 = params.get('window3', 52)

    ichimoku = ta.ichimoku(high=data['high'], low=data['low'], close=data['close'], window1=window1, window2=window2, window3=window3)
    data['ichimoku_a'] = ichimoku['ISA_9']
    data['ichimoku_b'] = ichimoku['ISB_26']

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        data['close'] > data['ichimoku_a'], 1,
        np.where(data['close'] < data['ichimoku_b'], -1, 0)
    )

    data = sanitize_signal(data)
    data['positions'] = data['signal'].diff()
    logging.debug(f"Ichimoku Cloud Strategy Signals: {data[['ichimoku_a', 'ichimoku_b', 'signal']].tail()}")
    return data

def stochastic_strategy(data, params):
    logging.info("Applying Stochastic Oscillator Strategy")
    window = params.get('window', 14)
    smooth_window = params.get('smooth_window', 3)
    upper_bound = params.get('upper_bound', 80)
    lower_bound = params.get('lower_bound', 20)

    stoch = ta.stoch(high=data['high'], low=data['low'], close=data['close'], k=window, d=smooth_window)
    data['stoch_k'] = stoch['STOCHk_14_3_3']
    data['stoch_d'] = stoch['STOCHd_14_3_3']

    data['signal'] = 0
    data.loc[:, 'signal'] = np.where(
        data['stoch_k'] < lower_bound, 1,
        np.where(data['stoch_k'] > upper_bound, -1, 0)
    )

    data = sanitize_signal(data)
    data['positions'] = data['signal'].diff()
    logging.debug(f"Stochastic Strategy Signals: {data[['stoch_k', 'stoch_d', 'signal']].tail()}")
    return data

# End of strategies list

def select_strategy(strategy_name):
    strategy_config = STRATEGIES_CONFIG.get(strategy_name)
    if not strategy_config:
        # Use 'sma_crossover' as the default strategy
        strategy_config = STRATEGIES_CONFIG.get('sma_crossover')
        strategy_name = 'sma_crossover'

    strategy_params = strategy_config['params']

    # Map strategy names to functions
    strategy_functions = {
        'sma_crossover': sma_crossover_strategy,
        'rsi_strategy': rsi_strategy,
        'macd_strategy': macd_strategy,
        'bollinger_bands_strategy': bollinger_bands_strategy,
        'combined_strategy': combined_strategy,
        'sma_crossover_with_orderbook': sma_crossover_with_orderbook_strategy,
        'ema_crossover_scalping': ema_crossover_scalping_strategy,
        'alma_strategy': alma_strategy,  # Add ALMA strategy
        'ama_strategy': ama_strategy,    # Add AMA strategy
        'ichimoku_strategy': ichimoku_strategy,  # Add Ichimoku strategy
        'stochastic_strategy': stochastic_strategy  # Add Stochastic strategy
    }

    strategy_func = strategy_functions.get(strategy_name, sma_crossover_strategy)

    return strategy_func, strategy_params
