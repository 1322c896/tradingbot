import json
import logging
import threading
import time
import websocket
from collections import defaultdict
from config import API_KEY, API_SECRET, WEBSOCKET_URL

class WebSocketClient:
    def __init__(self, symbols):
        self.ws = None
        self.symbols = [symbol.upper() for symbol in symbols]
        self.latest_ticker_data = defaultdict(dict)
        self.latest_orderbook_data = defaultdict(dict)
        self.is_running = False
        self.lock = threading.Lock()
        self.should_reconnect = True
        self.shutdown_flag = threading.Event()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.asset_info = {}
        self.balances = {}
        self.orders = {}
        self.pending_responses = {}
        self.pending_responses_lock = threading.Lock()
        self.order_events = {}
        self.id_mapping = {}

    def on_message(self, ws, message):
        data = json.loads(message)
        logging.debug(f"WebSocket message received: {data}")

        if 'id' in data:
            response_id = data['id']
            with self.pending_responses_lock:
                if response_id in self.pending_responses:
                    self.pending_responses[response_id]['response'] = data
                    self.pending_responses[response_id]['event'].set()

            if 'result' in data:
                orders = data.get('result', [])
                for order in orders:
                    self.process_order_update(order)

        elif 'method' in data:
            method = data['method']
            params = data.get('params', {})

            if method == 'ticker':
                self.handle_ticker_update(params)
            elif method == 'snapshotOrderbook':
                self.handle_orderbook_snapshot(params)
            elif method == 'updateOrderbook':
                self.update_orderbook(params)
            elif method in ['activeOrders', 'report']:
                self.process_order_update(params)
            elif method == 'getAsset':
                self.asset_info[params.get('ticker', '').upper()] = params
            elif method == 'getTradingBalance':
                self.balances = {balance['asset']: balance for balance in params}
            else:
                logging.warning(f"Unhandled method: {method}")

    def place_order_with_event(self, order_data, retries=3):
        internal_order_id = order_data['id']
        order_event = threading.Event()

        with self.lock:
            self.order_events[internal_order_id] = order_event

        # Place the order via the API
        payload = {
            "method": "newOrder",
            "params": order_data
        }
        self.send_message(payload)

        for attempt in range(retries):
            order_event.wait(timeout=30)
            with self.pending_responses_lock:
                response = self.pending_responses.pop(internal_order_id, {}).get('response')

            if response:
                if 'error' in response:
                    error_message = response['error'].get('message', '')
                    error_code = response['error'].get('code')
                    if error_code == 20001:  # Insufficient funds
                        logging.error(f"Order failed with error: {error_message}. Insufficient funds.")
                    else:
                        logging.error(f"Order failed with error: {error_message}")
                    return None

                if 'result' in response:
                    exchange_order_id = response['result']['id']
                    with self.lock:
                        self.id_mapping[exchange_order_id] = internal_order_id
                    logging.debug(f"Order successfully placed: {exchange_order_id}")
                    return order_event, internal_order_id

            logging.warning(f"Retrying order placement ({attempt + 1}/{retries})...")

        logging.error("No response received for the order or invalid response.")
        return None

    def cancel_order(self, order_id):
        """Cancel an order using the exchange's API."""
        payload = {
            "method": "cancelOrder",
            "params": {"id": order_id}
        }
        self.send_message(payload)
        logging.info(f"Cancellation request sent for order {order_id}")


    def send_message(self, payload):
        if self.ws:
            try:
                message = json.dumps(payload)
                self.ws.send(message)
                logging.debug(f"Message sent: {message}")
            except Exception as e:
                logging.error(f"Failed to send message: {e}")
        else:
            logging.error("WebSocket is not connected.")

    def handle_ticker_update(self, params):
        symbol = params.get('symbol', '').upper()
        if symbol in self.symbols:
            self.latest_ticker_data[symbol] = params
            logging.debug(f"Ticker update received for {symbol}: {params}")

    def handle_orderbook_snapshot(self, params):
        symbol = params.get('symbol', '').upper()
        if symbol in self.symbols:
            self.latest_orderbook_data[symbol] = params
            logging.info(f"Order book snapshot received for {symbol}.")

    def update_orderbook(self, params):
        symbol = params.get('symbol', '').upper()
        if symbol in self.symbols:
            orderbook = self.latest_orderbook_data.get(symbol, {'asks': [], 'bids': []})
            
            for ask in params.get('asks', []):
                orderbook['asks'] = self.update_orderbook_side(orderbook['asks'], ask)

            for bid in params.get('bids', []):
                orderbook['bids'] = self.update_orderbook_side(orderbook['bids'], bid, reverse=True)

            self.latest_orderbook_data[symbol] = orderbook

    def update_orderbook_side(self, side, update, reverse=False):
        price = update['price']
        quantity = update['quantity']

        side = [entry for entry in side if entry['price'] != price]
        if float(quantity) > 0:
            side.append({'price': price, 'quantity': quantity})
        side.sort(key=lambda x: float(x['price']), reverse=reverse)

        return side

    def process_order_update(self, order_update):
        if not isinstance(order_update, dict):
            logging.error(f"Invalid order update: {order_update}")
            return

        exchange_order_id = order_update.get('id')
        if not exchange_order_id:
            logging.error(f"Order update missing 'id': {order_update}")
            return

        with self.lock:
            internal_order_id = self.id_mapping.get(exchange_order_id)
            if internal_order_id is None:
                logging.warning(f"No internal order mapping found for exchange order {exchange_order_id}")
                return
            
            if internal_order_id in self.order_events:
                event = self.order_events[internal_order_id]
                event.set()
                # Optionally, clean up after the event is set
                del self.order_events[internal_order_id]
                logging.info(f"Order update processed and event set for {exchange_order_id}")
            else:
                logging.warning(f"Internal order event not found for {exchange_order_id}")

        # Periodic cleanup for old orders in id_mapping and order_events
        self.cleanup_old_orders()

    def cleanup_old_orders(self):
        """Clean up old orders that are no longer relevant."""
        # Example cleanup logic: remove orders that have been processed and are not in the active list
        with self.lock:
            # Adjust condition as needed, e.g., based on time or order status
            processed_orders = [order_id for order_id, event in self.order_events.items() if event.is_set()]
            for order_id in processed_orders:
                if order_id in self.id_mapping:
                    del self.id_mapping[order_id]
                    del self.order_events[order_id]
                    logging.debug(f"Cleaned up order {order_id}")


    def on_open(self, ws):
        logging.info("WebSocket connection established.")
        self.is_running = True
        self.authenticate()

        for symbol in self.symbols:
            self.subscribe_ticker(symbol)
            self.subscribe_orderbook(symbol)

        self.subscribe_reports()

    def subscribe_ticker(self, symbol):
        payload = {"method": "subscribeTicker", "params": {"symbol": symbol}}
        self.send_message(payload)

    def subscribe_orderbook(self, symbol):
        payload = {"method": "subscribeOrderbook", "params": {"symbol": symbol, "limit": 100}}
        self.send_message(payload)

    def subscribe_reports(self):
        payload = {"method": "subscribeReports", "params": {}}
        self.send_message(payload)

    def authenticate(self):
        payload = {
            "method": "login",
            "params": {
                "algo": "BASIC",
                "pKey": API_KEY,
                "sKey": API_SECRET
            }
        }
        self.send_message(payload)

    def start(self):
        self.ws = websocket.WebSocketApp(
            WEBSOCKET_URL,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.thread = threading.Thread(target=self.ws.run_forever)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.should_reconnect = False
        self.shutdown_flag.set()
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=5)
        self.is_running = False

    def on_error(self, ws, error):
        logging.error(f"WebSocket error: {error}")
        self.is_running = False
        self.reconnect()

    def on_close(self, ws, close_status_code, close_msg):
        logging.warning(f"WebSocket closed: {close_status_code}, {close_msg}")
        if self.should_reconnect:
            self.reconnect()

    def reconnect(self):
        if self.reconnect_attempts < self.max_reconnect_attempts:
            logging.info("Reconnecting...")
            self.reconnect_attempts += 1
            time.sleep(5)
            self.start()
        else:
            logging.error("Max reconnection attempts reached.")

    def get_latest_ticker_data(self, symbol):
        """
        Returns the latest ticker data for the given symbol.
        """
        symbol = symbol.upper()
        return self.latest_ticker_data.get(symbol, {})

    def get_latest_orderbook_data(self, symbol):
        """
        Returns the latest order book data for the given symbol.
        """
        symbol = symbol.upper()
        return self.latest_orderbook_data.get(symbol, {'asks': [], 'bids': []})

    def get_asset_info(self, symbol):
        """
        Returns the asset information for the given symbol.
        """
        symbol = symbol.upper()
        return self.asset_info.get(symbol, {})

    def get_balances(self):
        """
        Returns the account balances.
        """
        return self.balances

    def get_orders(self):
        """
        Returns the current orders.
        """
        return self.orders
