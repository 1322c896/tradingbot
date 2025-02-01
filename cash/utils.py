import websocket
import json
import threading
import logging
import colorlog
from datetime import datetime
from config import WEBSOCKET_URL

def validate_symbols(symbols):
    symbols = [sym.upper() for sym in symbols]  # Normalize input symbols
    available_symbols = []

    def on_message(ws, message):
        data = json.loads(message)
        if 'result' in data and data['result']:
            markets = data['result']
            for market in markets:
                symbol = market.get('symbol', '').upper()
                if symbol:
                    available_symbols.append(symbol)
        ws.close()

    def on_error(ws, error):
        logging.error(f"WebSocket error: {error}")
        ws.close()

    def on_open(ws):
        request = {
            "method": "getMarkets",
            "params": {},
            "id": 1
        }
        ws.send(json.dumps(request))

    ws = websocket.WebSocketApp(
        WEBSOCKET_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error
    )

    # Run the WebSocket connection in a separate thread
    ws_thread = threading.Thread(target=ws.run_forever)
    ws_thread.start()

    # Wait for the WebSocket thread to finish
    ws_thread.join()

    # Normalize input symbols to match API symbols
    symbols = [sym.upper() for sym in symbols]

    # Validate symbols
    valid_symbols = [sym for sym in symbols if sym in available_symbols]

    invalid_symbols = set(symbols) - set(valid_symbols)
    if invalid_symbols:
        logging.warning(f"Invalid symbols: {', '.join(invalid_symbols)}")
    else:
        logging.info("All symbols are valid.")

    return valid_symbols

def log_trade(trade_id, timestamp, symbol, entry_price, exit_price, position_size, side, profit_loss, fees):
    trade_log = {
        'trade_id': trade_id,
        'timestamp': timestamp,
        'symbol': symbol,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'position_size': position_size,
        'side': side,
        'profit_loss': profit_loss,
        'fees': fees
    }
    logging.info(json.dumps(trade_log))

def setup_logging():
    # Define custom log level for trades
    TRADE_LOG_LEVEL = 25
    logging.addLevelName(TRADE_LOG_LEVEL, "TRADE")

    # Add custom logging method to the logging.Logger class
    def trade(self, message, *args, **kws):
        if self.isEnabledFor(TRADE_LOG_LEVEL):
            self._log(TRADE_LOG_LEVEL, message, args, **kws)

    logging.Logger.trade = trade

    # Color definitions for different log levels
    log_colors = {
        'DEBUG': 'light_black',
        'INFO': 'light_blue',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'light_white',
        'TRADE': 'green'  # Custom color for trade logs
    }

    # Formatter with colors
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s [%(levelname)s] %(message)s',
        log_colors=log_colors
    )

    # Stream handler for console output
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # Basic configuration for logging
    logging.basicConfig(
        level=logging.DEBUG,  # Set the default level to DEBUG
        handlers=[stream_handler]
    )

    # File handler for error logs
    error_handler = logging.FileHandler('error.log')
    error_handler.setLevel(logging.ERROR)
    logging.getLogger().addHandler(error_handler)


# Setup logging
setup_logging()

