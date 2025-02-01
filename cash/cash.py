#cash.py - Trading Bot main program file
import argparse
import json
import logging
import time
import sys
import signal
import uuid
import pandas as pd
from config import ACCOUNT_BALANCE, MAX_RISK, SLEEP_INTERVALS
from data_fetcher import get_historical_data
from risk_management import apply_risk_management, calculate_stop_loss, calculate_take_profit
from strategies import select_strategy
#from trade_executor import execute_trade
from utils import validate_symbols, setup_logging
from websocket_handler import WebSocketClient
from balance_manager import BalanceManager




import threading

setup_logging()
logger = logging.getLogger()
ascii_art = """
●▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬๑۩۩๑▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬●
"""



# Global dictionary to store historical data for each symbol
historical_data_cache = {}

# Lock for thread-safe operations on the cache
cache_lock = threading.Lock()

# Declare ws_client as a global variable
ws_client = None

def parse_arguments():
    parser = argparse.ArgumentParser(description='Crypto Trading Bot')
    parser.add_argument('--symbols', nargs='+', required=True,
                        help='List of trading pairs (e.g., RVN/BTC BTC/USDT WLC/USDT)')
    parser.add_argument('--balance', type=float, default=ACCOUNT_BALANCE,
                        help='Account balance for position sizing')
    parser.add_argument('--max_risk', type=float, default=MAX_RISK,
                        help='Maximum risk per trade as a decimal (e.g., 0.02 for 2%)')
    parser.add_argument('--strategy', type=str, default='sma_crossover',
                        help='Trading strategy to use (e.g., sma_crossover, rsi_strategy)')
    return parser.parse_args()

def initialize_historical_data(symbols):
    logging.info("Initializing historical data for all symbols...")
    for symbol in symbols:
        data = get_historical_data(symbol)
        if data.empty:
            logging.warning(f"No historical data for {symbol}. Skipping.")
            historical_data_cache[symbol] = pd.DataFrame()
        else:
            data.index = data.index.tz_convert('UTC') if data.index.tzinfo else data.index.tz_localize('UTC')
            with cache_lock:
                historical_data_cache[symbol] = data
            logging.info(f"Historical data initialized for {symbol}.")


# Function to handle cleanup operations
def cleanup():
    logging.critical("Cleaning up resources...")
    if ws_client:
        ws_client.should_reconnect = False  # Prevent reconnection
        ws_client.shutdown_flag.set()  # Set the shutdown flag
        ws_client.stop()

    # Ensure all threads are properly joined
    main_thread = threading.current_thread()
    for thread in threading.enumerate():
        if thread is not main_thread:
            logging.critical(f"Joining thread {thread.name}")
            thread.join(timeout=5)

    logging.critical("Cleanup complete.")

# Signal handler function
def signal_handler(sig, frame):
    logging.critical("Interrupt received, shutting down...")
    cleanup()
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)

# The main trading bot function
def run_trading_bot(symbols, account_balance, max_risk, strategy_name):
    global ws_client
    print(ascii_art)
    logging.info("Initializing WebSocket client...")
    ws_client = WebSocketClient(symbols)
    ws_client.start()
    logging.info("WebSocket client started.")

    balance_manager = BalanceManager(refresh_interval=60)  # Adjust the interval as needed

    # Initial balance refresh
    logging.info("Performing initial balance refresh...")
    balance_manager.get_balance('USDT', force_refresh=True)
    time.sleep(2)  # Adjust the delay as needed to ensure balance fetching

    initialize_historical_data(symbols)
    wait_for_data(ws_client, symbols)

    try:
        while True:
            logging.info("Starting main trading loop...")
            threads = []

            for symbol in symbols:
                t = threading.Thread(
                    target=process_symbol,
                    args=(symbol, account_balance, max_risk, strategy_name, ws_client, balance_manager)
                )
                threads.append(t)
                t.start()
                time.sleep(SLEEP_INTERVALS['between_symbols'])  # Adjust if needed

            for t in threads:
                t.join()

            time.sleep(SLEEP_INTERVALS['main_loop'])

    except KeyboardInterrupt:
        logging.critical("Bot interrupted by user. Shutting down.")
        cleanup()
        sys.exit(0)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        cleanup()
        sys.exit(1)



def wait_for_data(ws_client, symbols, timeout=10):
    start_time = time.time()
    while True:
        ticker_data_ready = all(ws_client.get_latest_ticker_data(sym) for sym in symbols)
        orderbook_data_ready = all(ws_client.get_latest_orderbook_data(sym) for sym in symbols)
        
        if ticker_data_ready and orderbook_data_ready:
            logging.info("Received initial real-time data for all symbols.")
            break
        elif time.time() - start_time > timeout:
            logging.warning("Timeout reached while waiting for real-time data.")
            break
        else:
            time.sleep(0.5)


def ensure_datetime_format(timestamp):
    if isinstance(timestamp, int) or isinstance(timestamp, float):
        return pd.to_datetime(timestamp, unit='ms', utc=True)
    elif isinstance(timestamp, str):
        return pd.to_datetime(timestamp, utc=True)
    elif isinstance(timestamp, pd.Timestamp):
        return timestamp.tz_convert('UTC') if timestamp.tzinfo else timestamp.tz_localize('UTC')
    else:
        logging.warning(f"Unrecognized timestamp format: {timestamp}. Using current UTC time.")
        return pd.Timestamp.now(tz='UTC')

def append_latest_ticker_to_data(data, latest_ticker, latest_orderbook, max_rows=1000):
    timestamp = latest_ticker.get('updatedAt')
    if timestamp is None:
        logging.warning(f"No 'updatedAt' in latest_ticker; using current time.")
        timestamp = pd.Timestamp.now(tz='UTC')
    else:
        timestamp = ensure_datetime_format(timestamp)
        timestamp = timestamp.tz_convert('UTC') if timestamp.tzinfo else timestamp.tz_localize('UTC')

    try:
        high_price = float(latest_ticker.get('highPrice', 0))
        low_price = float(latest_ticker.get('lowPrice', 0))
        volume = float(latest_ticker.get('volume', 0))
        last_price_ticker = float(latest_ticker.get('lastPrice', 0))
        best_bid = float(latest_orderbook['bids'][0]['price']) if latest_orderbook and latest_orderbook.get('bids') else None
        best_ask = float(latest_orderbook['asks'][0]['price']) if latest_orderbook and latest_orderbook.get('asks') else None

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2
        else:
            logging.warning("Order book data incomplete or unavailable. Using last price from ticker.")
            mid_price = last_price_ticker

        last_price = mid_price
        open_price = best_bid if best_bid is not None else last_price_ticker

        if last_price == 0.0:
            logging.warning(f"Invalid latest price for {latest_ticker.get('symbol')}: {last_price}")
            return data
    except (TypeError, ValueError, IndexError, KeyError) as e:
        logging.warning(f"Invalid data received; skipping update. Error: {e}")
        return data

    latest_df = pd.DataFrame({
        'open': [open_price],
        'high': [high_price],
        'low': [low_price],
        'close': [last_price],
        'volume': [volume]
    }, index=[timestamp])

    data.index = pd.to_datetime(data.index, utc=True)
    latest_df.index = pd.to_datetime(latest_df.index, utc=True)

    logging.debug(f"latest_df.index[0] type: {type(latest_df.index[0])}")
    logging.debug(f"data.index[-1] type: {type(data.index[-1])}")

    if not data.empty and latest_df.index[0] <= data.index[-1]:
        logging.debug("Received older or duplicate data; skipping update.")
        return data

    data = pd.concat([data, latest_df])
    data = data.tail(max_rows)
    data = data[~data.index.duplicated(keep='last')]

    return data

# This looks at order book data to determine what the best prices are to fill orders
def determine_order_details(bids, asks, side, desired_quantity):
    try:
        orders = []
        total_quantity = 0

        if side == 'buy':
            if not asks:
                logger.error("No asks available in order book for buying. Skipping trade.")
                return None

            for ask in asks:
                price = float(ask['price'])
                quantity = float(ask['quantity'])
                if price <= 0 or quantity <= 0:
                    logger.error(f"Invalid ask price or quantity: price={price}, quantity={quantity}")
                    continue

                if total_quantity + quantity >= desired_quantity:
                    partial_quantity = desired_quantity - total_quantity
                    orders.append((price, partial_quantity))
                    total_quantity += partial_quantity
                    break
                orders.append((price, quantity))
                total_quantity += quantity

            if total_quantity < desired_quantity:
                logger.error("Not enough quantity available in order book for buying. Skipping trade.")
                return None

        elif side == 'sell':
            if not bids:
                logger.error("No bids available in order book for selling. Skipping trade.")
                return None

            for bid in bids:
                price = float(bid['price'])
                quantity = float(bid['quantity'])
                if price <= 0 or quantity <= 0:
                    logger.error(f"Invalid bid price or quantity: price={price}, quantity={quantity}")
                    continue

                if total_quantity + quantity >= desired_quantity:
                    partial_quantity = desired_quantity - total_quantity
                    orders.append((price, partial_quantity))
                    total_quantity += partial_quantity
                    break
                orders.append((price, quantity))
                total_quantity += quantity

            if total_quantity < desired_quantity:
                logger.error("Not enough quantity available in order book for selling. Skipping trade.")
                return None

        else:
            logger.error("Invalid order side")
            return None

        return orders

    except Exception as e:
        logger.error(f"Error in determine_order_details: {e}", exc_info=True)
        return None


def process_symbol(symbol, account_balance, max_risk, strategy_name, ws_client, balance_manager):
    """
    Process a single trading symbol by applying the selected strategy,
    managing risks, and placing trades if conditions are met.

    Args:
        symbol (str): Trading pair (e.g., "BTC/USDT").
        account_balance (float): Total account balance.
        max_risk (float): Maximum allowable risk per trade.
        strategy_name (str): Name of the trading strategy to apply.
        ws_client (WebSocketClient): WebSocket client for real-time data.
        balance_manager (BalanceManager): Balance management instance.

    Returns:
        None
    """
    try:
        # Validate WebSocket client
        if ws_client is None:
            logger.error("WebSocket client is not initialized. Skipping symbol processing.")
            return

        # Fetch real-time ticker and order book data
        latest_ticker = ws_client.get_latest_ticker_data(symbol)
        if not latest_ticker:
            logger.warning(f"No real-time ticker data for {symbol}. Retrying...")
            return

        latest_close_price = latest_ticker.get('lastPrice')
        if not latest_close_price or float(latest_close_price) <= 0.0:
            logger.error(f"Invalid latest ticker close price for {symbol}: {latest_close_price}")
            return
        latest_close_price = float(latest_close_price)

        latest_orderbook = ws_client.get_latest_orderbook_data(symbol)
        if not latest_orderbook:
            logger.warning(f"No order book data for {symbol}. Skipping.")
            return

        bids = latest_orderbook.get('bids', [])
        asks = latest_orderbook.get('asks', [])
        if not bids or not asks:
            logger.error(f"Order book data for {symbol} is incomplete. Skipping trade.")
            return

        # Fetch and update historical data
        with cache_lock:
            data = historical_data_cache.get(symbol, pd.DataFrame())
            if data.empty:
                logger.warning(f"No historical data for {symbol} in cache. Skipping.")
                return

            data = append_latest_ticker_to_data(data, latest_ticker, latest_orderbook)
            historical_data_cache[symbol] = data

        # Apply trading strategy
        strategy_func, strategy_params = select_strategy(strategy_name)
        data_copy = data.copy()
        if 'orderbook' in strategy_func.__code__.co_varnames:
            data_copy = strategy_func(data_copy, latest_orderbook, strategy_params)
        else:
            data_copy = strategy_func(data_copy, strategy_params)

        if 'positions' not in data_copy.columns:
            logger.error(f"Missing 'positions' column after applying strategy for {symbol}. Skipping.")
            return

        # Ensure data consistency
        data_copy.dropna(subset=['high', 'low', 'close'], inplace=True)

        # Apply risk management
        total_account_balance = balance_manager.get_total_balance()
        logger.info(f"Total account balance: {total_account_balance} USD")

        base_asset, quote_asset = symbol.split('/')
        available_quote_balance = balance_manager.get_balance(quote_asset)
        available_base_balance = balance_manager.get_balance(base_asset)

        logger.info(f"Available {quote_asset} balance: {available_quote_balance}")
        logger.info(f"Available {base_asset} balance: {available_base_balance}")

        data_copy = apply_risk_management(
            data_copy,
            total_account_balance,
            max_risk,
            atr_window=7,  # Keep atr_window if you want to configure the ATR window size
            available_balance=available_quote_balance  # Keep available_balance if needed
        )


        position_size = data_copy['position_size'].iloc[-1]
        logger.debug(f"Calculated position size for {symbol}: {position_size}")

        # Generate trading signal
        signal = data_copy['positions'].iloc[-1]
        if signal == 0:
            logger.info(f"No trade signal for {symbol}.")
            return

        # Validate position size
        if position_size <= 0.0:
            logger.warning(f"Position size for {symbol} is invalid. Skipping.")
            return

        # Determine trade details
        trade_side = 'buy' if signal == 1 else 'sell'
        orders = determine_order_details(
            bids if trade_side == 'buy' else asks,
            asks if trade_side == 'buy' else bids,
            trade_side, position_size
        )

        if not orders:
            logger.error(f"Failed to determine order details for {symbol}. Skipping.")
            return

        # Place orders
        for order_price, order_quantity in orders:
            if order_price <= 0 or order_quantity <= 0:
                logger.error(f"Invalid order details for {symbol}. Skipping.")
                continue

            logger.info(f"Placing {trade_side} order for {symbol}: price={order_price}, quantity={order_quantity}")
            trade_success = execute_trade(
                signal, symbol, order_quantity, ws_client,
                order_price, balance_manager
            )

            if not trade_success:
                logger.error(f"Failed to execute trade for {symbol}.")
                continue

            logger.info(f"Trade executed successfully for {symbol}.")

    except KeyError as ke:
        logger.error(f"Key error while processing {symbol}: {ke}", exc_info=True)
    except ValueError as ve:
        logger.error(f"Value error while processing {symbol}: {ve}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error while processing {symbol}: {e}", exc_info=True)


def monitor_trade(symbol, side, quantity, entry_price, stop_loss, take_profit, ws_client, balance_manager, trailing_stop=0.01):
    """
    Monitors the trade and handles trailing stop-loss logic.
    trailing_stop is the percentage for trailing stop (e.g., 0.01 for 1%).
    """
    logger = logging.getLogger()
    logger.trade(
        f"Monitoring trade for {symbol}. Entry: {entry_price}, Stop-Loss: {stop_loss}, Take-Profit: {take_profit}, Trailing Stop: {trailing_stop}"
    )

    close_side = 'sell' if side == 'buy' else 'buy'
    close_signal = -1 if side == 'buy' else 1

    last_high = entry_price if side == 'buy' else None
    last_low = entry_price if side == 'sell' else None

    while not ws_client.shutdown_flag.is_set():
        try:
            current_price = ws_client.get_latest_ticker_data(symbol).get('lastPrice', None)
            if current_price is None or current_price <= 0.0:
                logger.warning(f"Invalid current price for {symbol}: {current_price}")
                time.sleep(1)
                continue

            current_price = float(current_price)

            # Trailing Stop-Loss Logic
            if side == 'buy' and current_price > last_high:
                last_high = current_price
            elif side == 'sell' and current_price < last_low:
                last_low = current_price

            new_stop_loss = (
                last_high - (last_high * trailing_stop) if side == 'buy' else last_low + (last_low * trailing_stop)
            )

            if (side == 'buy' and current_price <= new_stop_loss) or (side == 'sell' and current_price >= new_stop_loss):
                logger.trade(f"Trailing Stop-Loss triggered for {symbol} at {current_price}.")
                success = execute_trade(close_signal, symbol, quantity, ws_client, price=current_price, balance_manager=balance_manager)
                if success:
                    break

            # Take-Profit Logic
            if (side == 'buy' and current_price >= take_profit) or (side == 'sell' and current_price <= take_profit):
                logger.trade(f"Take-Profit triggered for {symbol} at {current_price}.")
                success = execute_trade(close_signal, symbol, quantity, ws_client, price=current_price, balance_manager=balance_manager)
                if success:
                    break

            time.sleep(1)
        except Exception as e:
            logger.error(f"Error monitoring trade for {symbol}: {e}", exc_info=True)
            break


def execute_trade(signal, symbol, quantity, ws_client, price, balance_manager=None):
    if ws_client is None:
        logger.error("WebSocket client is None. Cannot execute trade.")
        return False

    # Validate inputs
    if quantity is None or quantity <= 0:
        logger.error(f"Invalid quantity provided for {symbol}: {quantity}")
        return False

    # Dynamically fetch market limits
    market_limits = ws_client.get_market_info(symbol)
    market_min_quantity = float(market_limits.get('minQuantity', 0.00001))
    tick_size = float(market_limits.get('tickSize', 0.00001))

    if quantity < market_min_quantity:
        logger.warning(f"Quantity {quantity} is below market minimum {market_min_quantity}. Adjusting to market minimum.")
        quantity = market_min_quantity

    if price is None or price <= 0:
        logger.error(f"Invalid price provided for {symbol}: {price}")
        return False

    # Format price and quantity to exchange standards
    price = round(price, int(abs(tick_size).as_integer_ratio()[1]))  # Adjust to tick size
    quantity_str = f"{quantity:.8f}"
    price_str = f"{price:.8f}"

    logger.trade(f"### Preparing to execute trade: {symbol}, {signal}, {quantity_str} at {price_str} ###")

    internal_order_id = int(time.time() * 1000)
    order_data = {
        "method": "newOrder",
        "params": {
            "userProvidedId": str(uuid.uuid4()),
            "symbol": symbol,
            "side": 'buy' if signal == 1 else 'sell',
            "price": price_str,
            "quantity": quantity_str,
        },
        "id": internal_order_id,
    }

    logger.debug(f"Order data: {json.dumps(order_data)}")

    retries = 3  # Max retries for placing an order
    for attempt in range(retries):
        try:
            # Place the order
            order_response = ws_client.place_order_with_event(order_data)
            if order_response is None:
                logger.error("Failed to place order: No response received.")
                return False

            order_event, internal_order_id = order_response
            logger.trade(f"Order sent: {order_data}. Event created for tracking order ID: {internal_order_id}")

            for _ in range(30):  # Poll every second for 30 seconds
                response = ws_client.get_order_status(internal_order_id)
                if response and response.get('status') in ['filled', 'partially_filled']:
                    break
                time.sleep(1)
            else:
                logger.error(f"Order {internal_order_id} was not filled within the timeout period.")
                return False

            # Validate response
            with ws_client.pending_responses_lock:
                response = ws_client.pending_responses.get(internal_order_id, {}).get('response')
                if response and 'error' in response:
                    logger.error(f"Failed to execute trade for {symbol}: {response['error']['message']}")
                    return False

            # Retrieve order execution details
            with ws_client.lock:
                exchange_order_id = next((k for k, v in ws_client.id_mapping.items() if v == internal_order_id), None)
                if not exchange_order_id:
                    logger.error(f"Failed to find exchange order ID for internal order ID: {internal_order_id}")
                    return False

                order_info = ws_client.orders.get(exchange_order_id)
                if not order_info:
                    logger.error(f"No order information found for order ID {exchange_order_id}.")
                    return False

                executed_quantity = float(order_info.get('executed_quantity', 0))
                actual_price = float(order_info.get('price', 0))

            if executed_quantity < quantity:
                remaining_quantity = quantity - executed_quantity
                logger.warning(f"Partial fill detected. Remaining quantity: {remaining_quantity}")
                # Optionally place a new order for the remaining quantity

            # Update balances if balance_manager is provided
            if balance_manager:
                base_asset, quote_asset = symbol.split('/')
                trade_value = actual_price * executed_quantity
                balance_changes = {
                    quote_asset: -trade_value if signal == 1 else trade_value,
                    base_asset: executed_quantity if signal == 1 else -executed_quantity
                }
                balance_manager.update_balance_after_trade(balance_changes)

            # Calculate stop-loss and take-profit with dynamic risk and reward
            risk_percentage = 0.01
            reward_percentage = 0.03
            stop_loss = calculate_stop_loss(actual_price, risk_percentage)
            take_profit = calculate_take_profit(actual_price, reward_percentage)

            # Start trade monitoring
            monitor_thread = threading.Thread(
                target=monitor_trade,
                args=(symbol, 'buy' if signal == 1 else 'sell', executed_quantity, actual_price,
                      stop_loss, take_profit, ws_client, balance_manager)
            )
            monitor_thread.start()

            # Log trade summary
            trade_summary = format_trade_summary(
                symbol, 'buy' if signal == 1 else 'sell', executed_quantity, actual_price,
                stop_loss, take_profit, exchange_order_id, 'Executed',
                balance_manager.get_balance(quote_asset) if balance_manager else None,
                balance_manager.get_balance(base_asset) if balance_manager else None,
            )
            logger.critical(trade_summary)

            return True
        except Exception as e:
            logger.error(f"Failed to execute trade for {symbol} on attempt {attempt+1}: {e}", exc_info=True)
            if attempt == retries - 1:
                return False
            time.sleep(2 ** attempt)  # Exponential backoff

# Helper functions for stop-loss and take-profit calculations
def calculate_stop_loss(entry_price, risk_percentage):
    return entry_price * (1 - risk_percentage)

def calculate_take_profit(entry_price, reward_percentage):
    return entry_price * (1 + reward_percentage)





##
def format_trade_summary(symbol, side, quantity, price, stop_loss, take_profit, order_id, status, balance_quote, balance_base):
    return f"""
## 🚀 Trade Execution Summary 🚀

### 📊 **Trade Details**:
- **Symbol**: {symbol}
- **Side**: {'Buy 🟢' if side == 'buy' else 'Sell 🔴'}
- **Quantity**: {quantity}
- **Entry Price**: {price} {symbol.split('/')[1]}  

### 📈 **Position Details**:
- **Stop-Loss**: {stop_loss} {symbol.split('/')[1]}  
- **Take-Profit**: {take_profit} {symbol.split('/')[1]}  

### 📋 **Order Status**:
- **Order ID**: {order_id}
- **Status**: {status} ✅
- **Time**: {time.strftime('%Y-%m-%d %H:%M:%S')}

### 📉 **Balance Update**:
- **{symbol.split('/')[1]} Balance**: {balance_quote}  
- **{symbol.split('/')[0]} Balance**: {balance_base}


### **Detailed Log**:
- **[{time.strftime('%H:%M:%S')}]** 🟢 **Trade Executed**: {symbol} {side.capitalize()} at {price}
- **[{time.strftime('%H:%M:%S')}]** ✅ **Balance Updated**: {symbol.split('/')[1]}: {balance_quote}, {symbol.split('/')[0]}: {balance_base}
    """



##### Program Entry Point
if __name__ == '__main__':
    args = parse_arguments()
    symbols = validate_symbols(args.symbols)
    if not symbols:
        logging.error("No valid symbols provided")
    else:
        run_trading_bot(symbols, args.balance, args.max_risk, args.strategy)

