# IVV Trading Bot (Alpha Strategy v2.0)

An automated trading system for the **iShares Core S&P 500 ETF (IVV)**.
This project implements a sophisticated **Alpha Strategy v2.0** that combines momentum, volatility targeting, and market regime detection to maximize returns while managing risk.

## 🚀 Key Features

*   **Alpha Strategy v2.0**: A hybrid strategy that switches between "Max Return" and "Safety First" modes based on market trends (ADX) and sentiment.
*   **Auto-Trading**: Fetches daily data, calculates indicators, and generates trading signals (BUY/SELL/HOLD).
*   **Email Notification**: Sends a daily trading report with the signal and target position size to your email.
*   **Performance Monitoring**: Generates comprehensive backtest reports and equity curves.

## 📊 Strategy Performance (Past 10 Years)

| Metric | Performance |
| :--- | :--- |
| **Total Return** | **137.56%** |
| **Max Drawdown (MDD)** | **-16.80%** |
| **Win Rate** | 55.14% |

> **Result**: Significantly outperformed the buy-and-hold strategy in risk-adjusted returns, successfully avoiding major crashes while capturing strong uptrends.

## 📂 Project Structure

```
├── main.py              # Entry point (Run this!)
├── src/
│   ├── strategy.py      # Alpha v2.0 Logic
│   ├── data_fetcher.py  # Data gathering (yfinance)
│   ├── backtester.py    # Performance calculation
│   └── notifier.py      # Email sender
├── results/             # Reports & Charts
├── .env                 # API Keys (Git-ignored)
└── requirements.txt     # Dependencies
```

## 🛠️ Usage

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure Environment**:
    Create a `.env` file with your email credentials:
    ```
    EMAIL_ADDRESS=your_email@gmail.com
    EMAIL_PASSWORD=your_app_password
    TARGET_EMAIL=target_email@example.com
    ```

3.  **Run the Bot**:
    ```bash
    python main.py
    ```

4.  **Check Results**:
    - Console Output: Detailed performance metrics.
    - Email: Concise daily signal report.
    - `results/`: Saved report and chart.

## ⚠️ Disclaimer
This software is for educational purposes only. Do not trade with money you cannot afford to lose.
