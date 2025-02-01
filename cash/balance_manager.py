import time
import threading
import logging
from api_client import get_asset_list, get_account_balances, get_price_lookup

class BalanceManager:
    def __init__(self, refresh_interval=120, asset_refresh_interval=300):
        self.cached_balances = {}
        self.last_update_time = 0
        self.refresh_interval = refresh_interval  # in seconds
        self.asset_cache = {}
        self.last_asset_update_time = 0
        self.asset_refresh_interval = asset_refresh_interval  # in seconds
        self.lock = threading.Lock()
        self.start_background_refresh()

    def fetch_with_retries(self, api_function, retries=3, delay=2):
        for attempt in range(retries):
            try:
                result = api_function()
                if result:
                    return result
            except Exception as e:
                logging.error(f"Error fetching data: {e}")
            time.sleep(delay)
        logging.error(f"Failed to fetch data after {retries} attempts.")
        return None

    def get_balance(self, asset, force_refresh=False):
        current_time = time.time()
        needs_refresh = force_refresh or (current_time - self.last_update_time) > self.refresh_interval or asset not in self.cached_balances

        if needs_refresh:
            logging.debug(f"Refreshing balance for {asset}")
            # Perform network operation outside of the lock
            balances = self.fetch_with_retries(get_account_balances)
            if balances is not None:
                with self.lock:
                    self.cached_balances = {
                        balance['asset']: float(balance.get('available', 0.0)) for balance in balances
                    }
                    self.last_update_time = current_time
                    logging.debug(f"Balances refreshed: {self.cached_balances}")
            else:
                logging.error("Failed to fetch account balances.")
                return 0.0

        with self.lock:
            logging.debug(f"Returning cached balance for {asset}")
            return self.cached_balances.get(asset, 0.0)

    def update_balance_after_trade(self, asset_changes):
        with self.lock:
            for asset, amount_change in asset_changes.items():
                self.cached_balances[asset] = self.cached_balances.get(asset, 0.0) + amount_change
                logging.info(f"Balance for {asset} updated to {self.cached_balances[asset]} after trade.")
        # Immediately refresh balances from the API
        self.get_balance(next(iter(asset_changes.keys())), force_refresh=True)

    def get_asset_prices(self):
        current_time = time.time()
        needs_refresh = (current_time - self.last_asset_update_time) > self.asset_refresh_interval

        if needs_refresh:
            logging.debug("Refreshing asset prices")
            asset_list = self.fetch_with_retries(get_asset_list)
            if asset_list:
                with self.lock:
                    self.asset_cache = self.fetch_with_retries(lambda: get_price_lookup(asset_list))
                    self.last_asset_update_time = current_time
                    logging.debug(f"Asset prices refreshed: {self.asset_cache}")

        with self.lock:
            logging.debug("Returning cached asset prices")
            return self.asset_cache

    def get_total_balance(self):
        logging.debug("Calculating total balance")
        total_balance = 0
        price_lookup = self.get_asset_prices()

        with self.lock:
            for asset, amount in self.cached_balances.items():
                price_in_usd = price_lookup.get(asset)
                if price_in_usd is None:
                    logging.warning(f"Price for {asset} is missing. Skipping.")
                    continue
                total_balance += amount * price_in_usd
            logging.debug(f"Total account balance in USD calculated: {total_balance}")
            return total_balance

    def start_background_refresh(self):
        def refresh_loop():
            while True:
                self.get_balance(asset=None, force_refresh=True)
                self.get_asset_prices()
                time.sleep(self.refresh_interval)

        threading.Thread(target=refresh_loop, daemon=True).start()

# Example usage of BalanceManager
# balance_manager = BalanceManager()
# print(balance_manager.get_balance('BTC'))
# print(balance_manager.get_total_balance())
