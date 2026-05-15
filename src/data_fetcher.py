import yfinance as yf
import pandas as pd


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
    data = yf.download(ticker, start=start_date, end=end_date,
                       progress=False, auto_adjust=True)

    if data is None or data.empty:
        return None

    # MultiIndex 컬럼 평탄화 (yfinance 버전에 따라 발생)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Date가 컬럼으로 내려온 경우 인덱스로 복원
    if "Date" in data.columns:
        data.set_index("Date", inplace=True)

    return data
