import time
import yfinance as yf
import pandas as pd
from src.logger import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 5  # seconds


def fetch_data(ticker, start_date, end_date):
    """
    yfinance Ticker.history()로 단일 종목의 OHLCV 데이터를 수집한다.

    yf.download()는 병렬 호출 시 내부 캐시 공유로 인해 종목 간 데이터가
    혼재될 수 있다. Ticker 인스턴스 단위로 호출하는 history()는 이 문제를
    방지한다.

    Parameters
    ----------
    ticker     : 종목 티커 (예: 'SCHD')
    start_date : 시작일 'YYYY-MM-DD'
    end_date   : 종료일 'YYYY-MM-DD'

    Returns
    -------
    pd.DataFrame | None
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            ticker_obj = yf.Ticker(ticker)
            data = ticker_obj.history(
                start=start_date,
                end=end_date,
                auto_adjust=True,
            )
        except Exception as e:
            if attempt < _MAX_RETRIES:
                logger.warning(f"[{ticker}] {attempt}회차 재시도 중... ({e})")
                time.sleep(_RETRY_DELAY)
                continue
            return None

        if data is not None and not data.empty:
            break

        if attempt < _MAX_RETRIES:
            logger.warning(f"[{ticker}] {attempt}회차 재시도 중... (빈 응답)")
            time.sleep(_RETRY_DELAY)
    else:
        return None

    # history()는 timezone-aware DatetimeIndex를 반환하므로 tz-naive로 변환
    # Prophet 및 pandas 연산의 호환성을 위해 UTC 기준으로 정규화한다
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)

    # 수집된 데이터의 마지막 날짜와 종가를 출력해 최신성을 즉시 확인할 수 있도록 한다
    if "Close" in data.columns:
        last_date = data.index[-1].strftime("%Y-%m-%d")
        last_close = float(data["Close"].dropna().iloc[-1])
        logger.info(f"[{ticker}] last date: {last_date} / close: ${last_close:.2f}")

    return data
