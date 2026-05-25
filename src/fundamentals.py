import io
import sys
import contextlib
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from typing import Optional
from src.logger import get_logger

logger = get_logger(__name__)


@contextlib.contextmanager
def _suppress_print():
    """yahoo_fin 임포트 시 발생하는 print() 기반 경고를 억제한다."""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


# -- 배당 성장률 CAGR -----------------------------------------------------------

def get_dividend_cagr(ticker: str) -> dict:
    """
    과거 배당 내역을 기반으로 5년 및 10년 배당 성장률(CAGR)을 계산한다.
    배당 성장 추세를 통해 장기 Yield on Cost(매수 시점 기준 배당률)를 추정하는 데 활용한다.

    반환값
    -------
    cagr_5y          : 5년 배당 CAGR (소수, 예: 0.08 = 8%)
    cagr_10y         : 10년 배당 CAGR (소수)
    yoc_5y           : 현재 배당률 기준 5년 후 예상 Yield on Cost
    yoc_10y          : 현재 배당률 기준 10년 후 예상 Yield on Cost
    annual_dividends : 연도별 배당 합계 딕셔너리
    """
    result = {
        "cagr_5y": None,
        "cagr_10y": None,
        "yoc_5y": None,
        "yoc_10y": None,
        "annual_dividends": {},
    }
    try:
        ticker_obj = yf.Ticker(ticker)
        divs = ticker_obj.dividends

        if divs is None or divs.empty:
            return result

        # tz-aware 인덱스를 tz-naive로 변환한다
        if getattr(divs.index, "tz", None) is not None:
            divs.index = divs.index.tz_convert(None)

        # 연도별 배당 합계
        annual = divs.groupby(divs.index.year).sum()
        result["annual_dividends"] = annual.to_dict()

        now_year = datetime.today().year

        def _cagr(years: int) -> Optional[float]:
            """start_year ~ (now_year-1) 구간의 연평균 배당 성장률을 반환한다."""
            start_year = now_year - years
            # 비교 기준 연도(start_year)와 최근 완전 연도(now_year-1) 데이터가 모두 필요하다
            if start_year not in annual.index or (now_year - 1) not in annual.index:
                return None
            start_val = float(annual[start_year])
            end_val = float(annual[now_year - 1])
            if start_val <= 0 or end_val <= 0:
                return None
            return (end_val / start_val) ** (1.0 / years) - 1.0

        result["cagr_5y"] = _cagr(5)
        result["cagr_10y"] = _cagr(10)

        # 현재 배당률 기반 Yield on Cost 추정
        # dividendYield는 퍼센트 형태(예: 0.42 = 0.42%)이므로 100으로 나눠 소수로 변환한다
        info = ticker_obj.info
        raw_yield = float(info.get("dividendYield") or 0.0)
        current_yield = raw_yield / 100.0

        if result["cagr_5y"] is not None and current_yield > 0:
            result["yoc_5y"] = current_yield * ((1.0 + result["cagr_5y"]) ** 5)
        if result["cagr_10y"] is not None and current_yield > 0:
            result["yoc_10y"] = current_yield * ((1.0 + result["cagr_10y"]) ** 10)

    except Exception as e:
        logger.debug(f"[{ticker}] 배당 CAGR 수집 실패: {e}")

    return result


# -- Payout Ratio + FCF 커버리지 -----------------------------------------------

def get_payout_and_fcf(ticker: str) -> dict:
    """
    배당 성향(Payout Ratio)과 FCF 대비 배당 지급 비율을 수집한다.
    Payout Ratio가 높거나 FCF 커버리지가 낮은 경우 배당 삭감 위험 신호로 활용한다.
    리츠(REIT)는 회계 구조상 EPS 기준 Payout Ratio가 100%를 크게 초과하므로 별도 해석이 필요하다.

    FCF 수집 우선순위:
        1. yfinance info["freeCashflow"]
        2. yahoo_fin 현금흐름표 (Operating CF - Capex)

    반환값
    -------
    payout_ratio     : EPS 기준 배당 성향 (소수, 예: 0.65 = 65%)
    fcf              : 연간 잉여현금흐름 (달러)
    annual_dividend  : 연간 주당 배당금 (달러)
    shares_out       : 발행 주식수
    fcf_payout_ratio : FCF 대비 배당 지급 비율 (소수)
    is_reit          : 리츠 여부 (bool)
    warning          : 경고 메시지 (없으면 None)
    """
    result = {
        "payout_ratio": None,
        "fcf": None,
        "annual_dividend": None,
        "shares_out": None,
        "fcf_payout_ratio": None,
        "is_reit": False,
        "warning": None,
    }
    try:
        info = yf.Ticker(ticker).info

        # 리츠 여부 판단 (sector 또는 industry 기준)
        sector = info.get("sector", "") or ""
        industry = info.get("industry", "") or ""
        if "REIT" in industry or "Real Estate" in sector:
            result["is_reit"] = True

        # EPS 기준 Payout Ratio
        raw_pr = info.get("payoutRatio")
        if raw_pr is not None:
            result["payout_ratio"] = float(raw_pr)

        # 연간 주당 배당금
        raw_div = info.get("dividendRate")
        if raw_div:
            result["annual_dividend"] = float(raw_div)

        # 발행 주식수
        shares = info.get("sharesOutstanding")
        if shares:
            result["shares_out"] = float(shares)

        # FCF: yfinance info에서 먼저 시도한다
        fcf_raw = info.get("freeCashflow")
        if fcf_raw:
            result["fcf"] = float(fcf_raw)
        else:
            # yahoo_fin으로 현금흐름표를 가져와 Operating CF - Capex로 FCF를 계산한다
            try:
                with _suppress_print():
                    from yahoo_fin import stock_info as si
                cf = si.get_cash_flow(ticker, yearly=True)
                if cf is not None and not cf.empty:
                    ocf_key = "totalCashFromOperatingActivities"
                    capex_key = "capitalExpenditures"
                    if ocf_key in cf.index and capex_key in cf.index:
                        latest_col = cf.columns[0]
                        ocf = float(cf.loc[ocf_key, latest_col])
                        capex = float(cf.loc[capex_key, latest_col])
                        # capex는 음수로 기록되므로 더하면 차감 효과가 난다
                        result["fcf"] = ocf + capex
            except Exception as e:
                logger.debug(f"[{ticker}] yahoo_fin FCF 수집 실패: {e}")

        # 총 배당 지급액 대비 FCF 커버리지 계산
        if (
            result["fcf"] is not None
            and result["annual_dividend"] is not None
            and result["shares_out"] is not None
        ):
            total_div = result["annual_dividend"] * result["shares_out"]
            if total_div > 0 and result["fcf"] > 0:
                result["fcf_payout_ratio"] = total_div / result["fcf"]

        # 지속 가능성 경고 판단
        pr = result["payout_ratio"]
        fcf_pr = result["fcf_payout_ratio"]

        if not result["is_reit"]:
            if pr is not None and pr > 0.85:
                result["warning"] = f"Payout Ratio {pr:.0%} — 배당 지속 가능성 주의"
            elif fcf_pr is not None and fcf_pr > 1.0:
                result["warning"] = f"FCF 커버리지 {fcf_pr:.0%} — FCF가 배당을 감당하지 못하는 상태"
        else:
            # 리츠는 FFO 기준으로 평가해야 하므로 EPS 기준 경고를 생략한다
            if fcf_pr is not None and fcf_pr > 1.2:
                result["warning"] = "REIT: 잉여현금흐름 대비 배당 지급 비율 높음, FFO 기준 별도 확인 권장"

    except Exception as e:
        logger.debug(f"[{ticker}] Payout/FCF 수집 실패: {e}")

    return result


# -- 역사적 PER 밴드 기반 적정가 추정 ------------------------------------------

def get_per_band(ticker: str, df_close: pd.Series) -> dict:
    """
    과거 주가와 분기 EPS를 결합해 역사적 PER 분포를 계산한다.
    현재 PER이 역사적 25~75th percentile 범위에서 벗어난 경우 고평가/저평가로 판단한다.
    ETF는 PER 개념이 다르므로 계산을 생략하고 빈 딕셔너리를 반환한다.

    EPS 수집 우선순위:
        1. yfinance quarterly_earnings (분기 EPS 합산 TTM)
        2. yahoo_fin earnings_history

    반환값
    -------
    current_pe  : 현재 Trailing PER
    pe_low      : 5년 역사적 PER 하단 (25th percentile)
    pe_mid      : 5년 역사적 PER 중간값 (50th percentile)
    pe_high     : 5년 역사적 PER 상단 (75th percentile)
    fair_value  : 중간 PER 기준 적정가 추정 (현재 TTM EPS 적용)
    valuation   : 'undervalued' / 'fair' / 'overvalued'
    current_eps : 현재 TTM EPS (달러)
    """
    result = {
        "current_pe": None,
        "pe_low": None,
        "pe_mid": None,
        "pe_high": None,
        "fair_value": None,
        "valuation": None,
        "current_eps": None,
    }
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info

        # ETF는 PER 계산을 생략한다
        if info.get("quoteType", "") == "ETF":
            return result

        # 현재 Trailing PER과 TTM EPS
        current_pe = info.get("trailingPE")
        current_eps = info.get("trailingEps")

        if not current_pe or not current_eps:
            return result

        result["current_pe"] = float(current_pe)
        result["current_eps"] = float(current_eps)

        # 분기 EPS를 4분기 Rolling Sum(TTM)으로 변환해 시계열 EPS를 구성한다
        eps_series = None

        try:
            # quarterly_income_stmt의 'Diluted EPS' 행을 사용한다
            # 열은 분기 종료 Timestamp, 최신 분기가 왼쪽(열 순서가 역순)이므로 정렬한다
            qis = ticker_obj.quarterly_income_stmt
            if (
                qis is not None
                and not qis.empty
                and "Diluted EPS" in qis.index
            ):
                eps_raw = qis.loc["Diluted EPS"].dropna()
                eps_raw.index = pd.to_datetime(eps_raw.index)
                if getattr(eps_raw.index, "tz", None) is not None:
                    eps_raw.index = eps_raw.index.tz_convert(None)
                eps_raw = eps_raw.sort_index()          # 오름차순 정렬
                eps_ttm = eps_raw.rolling(4).sum().dropna()
                if not eps_ttm.empty:
                    eps_series = eps_ttm
        except Exception as e:
            logger.debug(f"[{ticker}] quarterly_income_stmt EPS 수집 실패: {e}")

        # yfinance 실패 시 yahoo_fin으로 분기 EPS 이력을 수집한다
        if eps_series is None or eps_series.empty:
            try:
                with _suppress_print():
                    from yahoo_fin import stock_info as si
                eh = si.get_earnings_history(ticker)
                if eh is not None and not eh.empty and "epsactual" in eh.columns:
                    eh["startdatetime"] = pd.to_datetime(eh["startdatetime"])
                    eh = eh.sort_values("startdatetime").dropna(subset=["epsactual"])
                    eps_raw = eh.set_index("startdatetime")["epsactual"]
                    eps_series = eps_raw.rolling(4).sum().dropna()
            except Exception as e:
                logger.debug(f"[{ticker}] yahoo_fin EPS 이력 수집 실패: {e}")

        if eps_series is None or eps_series.empty:
            return result

        # 주가 시계열을 tz-naive로 정규화한다 (data_fetcher에서 이미 처리되지만 방어적으로 확인)
        price_series = df_close.copy()
        if getattr(price_series.index, "tz", None) is not None:
            price_series.index = price_series.index.tz_convert(None)
        price_series.index = pd.to_datetime(price_series.index)
        price_df = price_series.reset_index()
        price_df.columns = ["date", "price"]
        price_df = price_df.sort_values("date")

        eps_df = eps_series.reset_index()
        eps_df.columns = ["date", "eps"]
        eps_df = eps_df.sort_values("date")

        # merge_asof: 각 주가 날짜에 해당 시점 이전 최신 EPS를 결합한다
        merged = pd.merge_asof(
            price_df,
            eps_df,
            on="date",
            direction="backward",
        ).dropna()

        # 양수 EPS만 사용해 PER을 계산한다 (손실 구간 제외)
        merged = merged[merged["eps"] > 0]
        if merged.empty:
            return result

        hist_pe = merged["price"] / merged["eps"]

        result["pe_low"] = float(hist_pe.quantile(0.25))
        result["pe_mid"] = float(hist_pe.median())
        result["pe_high"] = float(hist_pe.quantile(0.75))

        # 중간 PER x 현재 TTM EPS = 적정가 추정
        result["fair_value"] = result["pe_mid"] * result["current_eps"]

        # 현재 PER이 역사적 25~75th percentile 범위 밖인지 판단한다
        if result["current_pe"] < result["pe_low"]:
            result["valuation"] = "undervalued"
        elif result["current_pe"] > result["pe_high"]:
            result["valuation"] = "overvalued"
        else:
            result["valuation"] = "fair"

    except Exception as e:
        logger.debug(f"[{ticker}] PER 밴드 계산 실패: {e}")

    return result
