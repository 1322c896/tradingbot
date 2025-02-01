#trade_executor.py
#
import time
import uuid
import json
import logging
from requests.exceptions import HTTPError, RequestException
import pandas as pd
from risk_management import calculate_stop_loss, calculate_take_profit
import threading
from balance_manager import BalanceManager
from utils import setup_logging  # Import the logging setup

# Ensure the logging is set up
setup_logging()

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

### 📝 **Notes**:
- Trade executed successfully.
- Monitoring stop-loss and take-profit levels.

### 🎉 **Next Steps**:
- Keep an eye on the market trends.
---

### **Detailed Log**:
- **[{time.strftime('%H:%M:%S')}]** 🟢 **Trade Executed**: {symbol} {side.capitalize()} at {price}
- **[{time.strftime('%H:%M:%S')}]** ✅ **Balance Updated**: {symbol.split('/')[1]}: {balance_quote}, {symbol.split('/')[0]}: {balance_base}
    """




last_trade_time = 0
min_hold_period = 60  # Minimum holding period in seconds

def execute_trade(signal, symbol, quantity, price, ws=None):
    side = 'buy' if signal == 1 else 'sell'

    risk_percentage = 0.02  # 2% risk
    reward_percentage = 0.04  # 4% reward

    stop_loss = calculate_stop_loss(price, risk_percentage)
    take_profit = calculate_take_profit(price, reward_percentage)

    quantity_formatted = f"{float(quantity):.8f}"
    price_formatted = f"{float(price):.8f}"

    order_data = {
        "method": "newOrder",
        "params": {
            "userProvidedId": str(uuid.uuid4()),
            "symbol": symbol,
            "side": side,
            "price": price_formatted,
            "quantity": quantity_formatted
        },
        "id": int(time.time() * 1000)
    }

    logging.debug(f"Order data: {json.dumps(order_data)}")

    if ws:
        try:
            event = ws.send_order(order_data)
            event.wait(timeout=5)

            with ws.pending_responses_lock:
                response_data = ws.pending_responses.get(order_data['id'], {}).get('response')
                if order_data['id'] in ws.pending_responses:
                    del ws.pending_responses[order_data['id']]

            if response_data:
                if 'error' in response_data:
                    error_message = response_data['error'].get('message', 'Unknown error')
                    logging.error(f"Trade failed for {symbol}: {error_message}")
                    return False
                else:
                    logging.debug(f"Trade executed successfully for {symbol}. Response: {response_data}")

                    # Fetch updated balances dynamically
                    base_asset, quote_asset = symbol.split('/')
                    balance_manager = BalanceManager()
                    balance_quote = balance_manager.get_balance(quote_asset)
                    balance_base = balance_manager.get_balance(base_asset)

                    # Format and log the trade summary
                    trade_summary = format_trade_summary(
                        symbol=symbol, side=side, quantity=quantity, price=price,
                        stop_loss=stop_loss, take_profit=take_profit, order_id=order_data['id'], status='Executed',
                        balance_quote=balance_quote, balance_base=balance_base  # Updated to match function definition
                    )
                    logging.getLogger().trade(trade_summary)

                    # # Start monitoring in a new thread
                    # monitoring_thread = threading.Thread(
                    #     target=monitor_trade,
                    #     args=(symbol, side, quantity, price, stop_loss, take_profit, ws),
                    #     daemon=True
                    # )
                    # monitoring_thread.start()
                    return True
            else:
                logging.error(f"No response received for order {order_data['id']} within timeout period.")
                return False
        except Exception as e:
            logging.error(f"Failed to send order via WebSocket: {e}")
            return False
    else:
        logging.error("WebSocket connection is not available. Cannot send order.")
        return False
