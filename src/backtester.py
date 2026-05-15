import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def calculate_performance(df):
    """
    Calculates strategy performance metrics.
    
    Args:
        df (pd.DataFrame): Dataframe with 'Close' prices and 'Signal' columns.
        
    Returns:
        dict: Performance metrics (Total Return, Win Rate, MDD).
    """
    if df is None or df.empty:
        return {}
        
    df = df.copy()
    
    # Calculate Daily Returns
    df['Daily_Return'] = df['Close'].pct_change()
    
    # Calculate Strategy Returns
    # Shift signal and position size by 1 day to apply today's decision to tomorrow's return
    # If Position_Size doesn't exist (older strategies), assume it's equal to Signal (0 or 1)
    if 'Position_Size' in df.columns:
        df['Strategy_Return'] = df['Position_Size'].shift(1) * df['Daily_Return']
    else:
        df['Strategy_Return'] = df['Signal'].shift(1) * df['Daily_Return']
    
    # Calculate Cumulative Returns
    df['Cumulative_Market_Return'] = (1 + df['Daily_Return']).cumprod()
    df['Cumulative_Strategy_Return'] = (1 + df['Strategy_Return']).cumprod()
    
    # Total Return
    total_return = df['Cumulative_Strategy_Return'].iloc[-1] - 1
    
    # Win Rate
    wins = df[df['Strategy_Return'] > 0]
    losses = df[df['Strategy_Return'] < 0]
    total_trades = len(wins) + len(losses)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0
    
    # MDD (Maximum Drawdown)
    rolling_max = df['Cumulative_Strategy_Return'].cummax()
    drawdown = (df['Cumulative_Strategy_Return'] - rolling_max) / rolling_max
    max_drawdown = drawdown.min()
    
    return {
        "Total Return": total_return,
        "Win Rate": win_rate,
        "Max Drawdown": max_drawdown
    }

def plot_results(df, filename="result_chart.png"):
    """
    Plots the price, moving averages, and buy/sell signals, and saves to a file.
    
    Args:
        df (pd.DataFrame): Dataframe with 'Close', 'Short_MA', 'Long_MA', and 'Position' columns.
        filename (str): Filename to save the plot.
    """
    if df is None or df.empty:
        print("No data to plot.")
        return

    plt.figure(figsize=(14, 7))
    
    # Plot Close Price
    plt.plot(df.index, df['Close'], label='Close Price', alpha=0.5)
    
    # Plot Moving Averages
    plt.plot(df.index, df['Short_MA'], label='5-Day SMA', alpha=0.7)
    plt.plot(df.index, df['Long_MA'], label='20-Day SMA', alpha=0.7)

    # Plot Buy/Sell Signals based on Signal transitions (0→1: buy, 1→0: sell)
    signal_diff = df['Signal'].diff()
    buy_signals = df[signal_diff == 1.0]
    sell_signals = df[signal_diff == -1.0]

    plt.plot(buy_signals.index,
             df['Short_MA'][buy_signals.index],
             '^', markersize=10, color='g', lw=0, label='Buy Signal')

    plt.plot(sell_signals.index,
             df['Short_MA'][sell_signals.index],
             'v', markersize=10, color='r', lw=0, label='Sell Signal')
    
    plt.title('IVV Trading Bot - Moving Average Crossover Strategy')
    plt.xlabel('Date')
    plt.ylabel('Price (USD)')
    plt.legend()
    plt.grid()
    
    # Save to file
    import os
    os.makedirs('results', exist_ok=True)
    save_path = f"results/{filename}"
    plt.savefig(save_path)
    print(f"Chart saved to {save_path}")
    plt.close()
