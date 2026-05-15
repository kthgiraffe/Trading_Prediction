import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_adx(df, period=14):
    """
    Calculates Average Directional Index (ADX) to measure trend strength.
    """
    # Simply using a simplified ADX calculation or TR/DM logic
    # For full ADX, we need High, Low, Close
    # Assuming df has 'High', 'Low', 'Close'
    # If not available (e.g. only Close), we can't calc standard ADX.
    # But yfinance provides High/Low.
    
    # Calculate True Range (TR)
    df['tr1'] = df['High'] - df['Low']
    df['tr2'] = abs(df['High'] - df['Close'].shift(1))
    df['tr3'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # Directional Movement
    df['up_move'] = df['High'] - df['High'].shift(1)
    df['down_move'] = df['Low'].shift(1) - df['Low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    # Smooth
    df['TR_smooth'] = df['TR'].rolling(window=period).sum()
    df['plus_di'] = 100 * (df['plus_dm'].rolling(window=period).sum() / df['TR_smooth'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(window=period).sum() / df['TR_smooth'])
    
    # DX and ADX
    df['DX'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    df['ADX'] = df['DX'].rolling(window=period).mean()
    
    # Cleanup temp columns
    df.drop(['tr1', 'tr2', 'tr3', 'TR', 'up_move', 'down_move', 'plus_dm', 'minus_dm', 'TR_smooth', 'plus_di', 'minus_di', 'DX'], axis=1, inplace=True)
    return df

def apply_strategy(df, short_window=5, long_window=20, rsi_period=14, target_vol=0.22, min_position=0.4, vol_window=10):
    """
    Apply Alpha Strategy v2.0 (Hybrid Sizing + Market Regime + Sentiment Filter)
    """
    # 1. Base Strategy: High Performance (5/20 MA + RSI)
    df['Short_MA'] = df['Close'].rolling(window=short_window).mean()
    df['Long_MA'] = df['Close'].rolling(window=long_window).mean()
    df['RSI'] = calculate_rsi(df['Close'], period=rsi_period)
    
    buy_condition = (df['Short_MA'] > df['Long_MA']) & (df['RSI'] > 50)
    df['Signal'] = 0.0
    df.loc[buy_condition, 'Signal'] = 1.0
    
    # 2. Sentiment Filter: Avoid buying if price drops for 5 consecutive days ("Falling Knife")
    # Close < Close[1] for 5 days straight
    # (Close < Close.shift(1)) & (Close.shift(1) < Close.shift(2)) ... 
    # Or simpler: Rolling sum of (Close < Close.shift(1)) == 5
    is_down_day = (df['Close'] < df['Close'].shift(1)).astype(int)
    consecutive_down_days = is_down_day.rolling(window=5).sum()
    
    # Override Signal to 0 if 5 consecutive down days
    df.loc[consecutive_down_days == 5, 'Signal'] = 0.0

    # 3. Position Sizing
    # A) Calculate Volatility Targeting Position
    df['Rolling_Vol'] = df['Close'].pct_change().rolling(window=vol_window).std() * np.sqrt(252) # Annualized Vol
    df['Vol_Position_Size'] = target_vol / df['Rolling_Vol']
    df['Vol_Position_Size'] = df['Vol_Position_Size'].clip(lower=min_position, upper=1.0)
    df['Vol_Position_Size'] = df['Vol_Position_Size'].ffill()
    df['Vol_Position_Size'] = df['Vol_Position_Size'].fillna(min_position)
    
    # B) Calculate ADX for Market Regime
    df = calculate_adx(df)
    
    # C) Hybrid Sizing
    # If ADX > 25 (Strong Trend) -> Use 100% position (Aggressive)
    # Else (Weak Trend/Choppy) -> Use Volatility Targeting (Defensive)
    df['Hybrid_Position_Size'] = df['Vol_Position_Size'] # Default to Volatility Targeting size
    df.loc[df['ADX'] > 25, 'Hybrid_Position_Size'] = 1.0 # Override for strong trends
    
    # Final Position Size = Signal * Sizing
    df['Position_Size'] = df['Signal'] * df['Hybrid_Position_Size']
    
    # Position Diff for Turnover (optional)
    df['Position'] = df['Position_Size'].diff() # Just for compatibility with backtester if needed
    
    return df
