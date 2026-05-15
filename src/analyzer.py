import numpy as np
import pandas as pd
import yfinance as yf


def _calculate_rsi(series, period=14):
    delta = series.diff(1)
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _period_return(df_close, current_price, trading_days):
    if len(df_close) > trading_days:
        past_price = df_close.iloc[-trading_days]
        if past_price > 0:
            return (current_price - past_price) / past_price
    return None


def analyze_ticker(ticker, df, ticker_info):
    """
    종목의 현재 상태를 분석해 지표 딕셔너리를 반환한다.

    Returns
    -------
    dict : 현재가, 52주 범위, 기간별 수익률, RSI, 이동평균, 배당률 등
    """
    close = df["Close"]
    current_price = float(close.iloc[-1])

    # 52주 고가/저가 (약 252 거래일)
    year_df = df.tail(252)
    high_52w = float(year_df["High"].max())
    low_52w = float(year_df["Low"].min())

    # 52주 고가 대비 현재가 위치 (0~1)
    price_vs_52w_high = (current_price - low_52w) / (high_52w - low_52w) if high_52w != low_52w else 0.5

    # YTD 수익률 (올해 첫 거래일 기준)
    current_year = df.index[-1].year
    ytd_data = df[df.index.year == current_year]
    ytd_return = (current_price - float(ytd_data["Close"].iloc[0])) / float(ytd_data["Close"].iloc[0]) if len(ytd_data) > 0 else None

    # 기간별 수익률
    return_1m = _period_return(close, current_price, 21)
    return_3m = _period_return(close, current_price, 63)
    return_6m = _period_return(close, current_price, 126)
    return_1y = _period_return(close, current_price, 252)

    # RSI (14일)
    rsi = float(_calculate_rsi(close).iloc[-1])
    if rsi > 70:
        rsi_signal = "과매수"
    elif rsi < 30:
        rsi_signal = "과매도"
    else:
        rsi_signal = "중립"

    # 이동평균 (20일, 60일, 200일)
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    if current_price > ma20 and ma20 > ma60:
        ma_signal = "상승"
    elif current_price < ma20 and ma20 < ma60:
        ma_signal = "하락"
    else:
        ma_signal = "중립"

    # 단기 모멘텀: 최근 20일 수익률 방향
    momentum_20d = return_1m if return_1m is not None else 0.0

    # 변동성 (연율화, 최근 20거래일)
    daily_vol = close.pct_change().tail(20).std()
    annualized_vol = float(daily_vol * np.sqrt(252)) if not np.isnan(daily_vol) else None

    # 배당률 (yfinance info)
    div_yield = 0.0
    try:
        info = yf.Ticker(ticker).info
        div_yield = float(info.get("dividendYield") or 0.0)
    except Exception:
        pass

    return {
        "ticker": ticker,
        "name": ticker_info["name"],
        "category": ticker_info["category"],
        "weight": ticker_info["weight"],
        "div_freq": ticker_info["div_freq"],
        "current_price": current_price,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "price_vs_52w_high": price_vs_52w_high,
        "ytd_return": ytd_return,
        "return_1m": return_1m,
        "return_3m": return_3m,
        "return_6m": return_6m,
        "return_1y": return_1y,
        "rsi": rsi,
        "rsi_signal": rsi_signal,
        "ma20": ma20,
        "ma60": ma60,
        "ma200": ma200,
        "ma_signal": ma_signal,
        "momentum_20d": momentum_20d,
        "annualized_vol": annualized_vol,
        "div_yield": div_yield,
    }
