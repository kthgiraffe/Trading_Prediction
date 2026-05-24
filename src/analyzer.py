import numpy as np
import pandas as pd
import yfinance as yf
from src.logger import get_logger
from src.fundamentals import get_dividend_cagr, get_payout_and_fcf, get_per_band

logger = get_logger(__name__)


def _calculate_rsi(series, period=14):
    delta = series.diff(1)
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _period_return(df_close, current_price, trading_days):
    """NaN을 제외한 유효 종가 기준으로 과거 수익률을 계산한다."""
    valid = df_close.dropna()
    if len(valid) > trading_days:
        past_price = float(valid.iloc[-trading_days])
        if past_price > 0:
            return (current_price - past_price) / past_price
    return None


def analyze_ticker(ticker, df, ticker_info):
    """
    종목의 현재 상태를 분석해 지표 딕셔너리를 반환한다.

    Returns
    -------
    dict : 현재가, 52주 범위, 기간별 수익률, RSI, 이동평균, 배당률,
           배당 CAGR, Payout/FCF 커버리지, PER 밴드 등
    """
    close = df["Close"]

    # 마지막 유효한(non-NaN) 종가를 사용해 NaN 전파를 방지한다
    valid_close = close.dropna()
    if valid_close.empty:
        raise ValueError(f"{ticker}: 유효한 종가 데이터가 없습니다.")
    current_price = float(valid_close.iloc[-1])

    # 52주 고가/저가 (약 252 거래일)
    year_df = df.tail(252)
    high_52w = float(year_df["High"].max())
    low_52w = float(year_df["Low"].min())

    # 52주 범위 내 현재가의 상대적 위치 (0 = 최저, 1 = 최고)
    price_vs_52w_high = (
        (current_price - low_52w) / (high_52w - low_52w)
        if high_52w != low_52w else 0.5
    )

    # YTD 수익률 (올해 첫 거래일 기준)
    current_year = df.index[-1].year
    ytd_data = df[df.index.year == current_year]
    ytd_return = (
        (current_price - float(ytd_data["Close"].iloc[0])) / float(ytd_data["Close"].iloc[0])
        if len(ytd_data) > 0 else None
    )

    # 기간별 수익률 (거래일 기준)
    return_1m = _period_return(close, current_price, 21)
    return_3m = _period_return(close, current_price, 63)
    return_6m = _period_return(close, current_price, 126)
    return_1y = _period_return(close, current_price, 252)

    # RSI (14일) 및 신호 판단
    rsi = float(_calculate_rsi(close).iloc[-1])
    if rsi > 70:
        rsi_signal = "과매수"
    elif rsi < 30:
        rsi_signal = "과매도"
    else:
        rsi_signal = "중립"

    # 이동평균 (20일, 60일, 200일) 및 추세 신호
    ma20  = float(close.rolling(20).mean().iloc[-1])
    ma60  = float(close.rolling(60).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    if current_price > ma20 and ma20 > ma60:
        ma_signal = "상승"
    elif current_price < ma20 and ma20 < ma60:
        ma_signal = "하락"
    else:
        ma_signal = "중립"

    # 단기 모멘텀 (최근 20거래일 수익률 방향)
    momentum_20d = return_1m if return_1m is not None else 0.0

    # 연율화 변동성 (최근 20거래일 기준)
    daily_vol = close.pct_change().tail(20).std()
    annualized_vol = float(daily_vol * np.sqrt(252)) if not np.isnan(daily_vol) else None

    # 배당률 수집
    # yfinance 키별 반환 형태가 다르다:
    #   'yield'                     : 소수 형태  (0.0042 = 0.42%)  → 그대로 사용
    #   'dividendYield'             : 퍼센트 형태 (0.42  = 0.42%)  → 100으로 나눔
    #   'trailingAnnualDividendYield': 소수 형태이나 부정확한 경우가 많아 3순위
    # 위 키가 모두 0/None 이면(예: SPYM), 실제 배당 이력에서 연간 합계를 계산한다.
    div_yield = 0.0
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info

        raw_y = float(info.get("yield") or 0.0)
        if raw_y > 0:
            div_yield = raw_y                          # 이미 소수 형태
        else:
            raw_dy = float(info.get("dividendYield") or 0.0)
            if raw_dy > 0:
                div_yield = raw_dy / 100.0             # 퍼센트 형태 → 소수로 변환

        # yield / dividendYield 모두 0이면 실제 배당 이력으로 계산
        if div_yield == 0.0 and current_price > 0:
            divs = ticker_obj.dividends
            if not divs.empty:
                cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
                annual_div = divs[divs.index >= cutoff].sum()
                if annual_div > 0:
                    div_yield = float(annual_div) / current_price
    except Exception:
        pass

    # 펀더멘털 지표 수집 (실패 시 빈 딕셔너리를 사용해 파이프라인을 유지한다)
    div_cagr   = get_dividend_cagr(ticker)
    payout_fcf = get_payout_and_fcf(ticker)
    per_band   = get_per_band(ticker, close)

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
        "div_cagr": div_cagr,
        "payout_fcf": payout_fcf,
        "per_band": per_band,
    }
