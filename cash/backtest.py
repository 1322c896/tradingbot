import pandas as pd
import numpy as np

def backtest_ema_crossover(data, short_window, long_window, signal_threshold):
    data['ema_short'] = data['close'].ewm(span=short_window, adjust=False).mean()
    data['ema_long'] = data['close'].ewm(span=long_window, adjust=False).mean()
    
    data['signal'] = 0
    data.loc[data.index[long_window:], 'signal'] = np.where(
        (data['ema_short'][long_window:] - data['ema_long'][long_window:]) > signal_threshold, 1,
        np.where((data['ema_short'][long_window:] - data['ema_long'][long_window:]) < -signal_threshold, -1, 0)
    )

    data['positions'] = data['signal'].diff()
    data['returns'] = data['close'].pct_change()
    data['strategy_returns'] = data['returns'] * data['signal'].shift(1)

    cumulative_returns = (1 + data['strategy_returns']).cumprod() - 1

    return cumulative_returns.iloc[-1]  # Returns the final cumulative return

# Example usage with historical data
data = pd.read_csv('historical_data.csv')
short_window = 5
long_window = 15

# Test different signal thresholds
for threshold in np.arange(0.001, 0.010, 0.001):
    final_return = backtest_ema_crossover(data, short_window, long_window, threshold)
    print(f'Signal Threshold: {threshold}, Final Return: {final_return:.2f}')
