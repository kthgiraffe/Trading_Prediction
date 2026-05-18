import time
import yfinance as yf
import pandas as pd

_MAX_RETRIES = 3
_RETRY_DELAY = 5  # seconds


def fetch_data(ticker, start_date, end_date):
    """
    yfinance로 주어진 종목의 OHLCV 데이터를 수집한다.

    Parameters
    ----------
    ticker     : 종목 티커 (예: 'SCHD')
    start_date : 시작일 'YYYY-MM-DD'
    end_date   : 종료일 'YYYY-MM-DD'

    Returns
    -------
    pd.DataFrame | None
    """
    # [수정] yfinance 캐시 갱신 워밍업 — 최신 종가가 캐시에 반영되도록 1d 히스토리를 먼저 호출
    try:
        yf.Ticker(ticker).history(period="1d")
    except Exception:
        pass

    # [개선] 네트워크 불안정 대비 최대 3회 재시도
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            data = yf.download(ticker, start=start_date, end=end_date,
                               progress=False, auto_adjust=True)
        except Exception as e:
            if attempt < _MAX_RETRIES:
                print(f"[RETRY] {ticker} — {attempt}회차 재시도 중... ({e})")
                time.sleep(_RETRY_DELAY)
                continue
            return None

        if data is not None and not data.empty:
            break

        if attempt < _MAX_RETRIES:
            print(f"[RETRY] {ticker} — {attempt}회차 재시도 중... (빈 응답)")
            time.sleep(_RETRY_DELAY)
    else:
        return None

    # MultiIndex 컬럼 평탄화 (yfinance 버전에 따라 발생)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Date가 컬럼으로 내려온 경우 인덱스로 복원
    if "Date" in data.columns:
        data.set_index("Date", inplace=True)

    return data
