import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pandas as pd

warnings.filterwarnings("ignore")
pd.options.mode.chained_assignment = None
sys.stdout.reconfigure(encoding="utf-8")

from src.config import validate_env
from src.logger import get_logger
from src.portfolio_config import PORTFOLIO
from src.data_fetcher import fetch_data
from src.analyzer import analyze_ticker
from src.predictor import predict_ticker
from src.notion_writer import write_report_to_notion
from src.notifier import send_portfolio_alert

logger = get_logger(__name__)


def _fmt_pct(v):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2%}"


def main():
    # 필수 환경변수 누락 시 즉시 종료한다
    validate_env()

    today      = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    # yfinance history()는 end 날짜를 exclusive로 처리하므로 내일 날짜를 전달한다
    end_date   = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info("=" * 54)
    logger.info(f"  Portfolio Analysis Report  ({today})")
    logger.info("=" * 54)
    logger.info(f"  분석 종목 : {len(PORTFOLIO)}개")
    logger.info(f"  데이터 기간: {start_date} ~ {today} (3년)")
    logger.info("  예측 방식 : 1M XGBoost  |  3/6/12M Prophet")
    logger.info("=" * 54)

    # fetch 단계만 병렬화한다. 분석/예측은 순차 처리를 유지한다.
    def _fetch_one(info):
        return info, fetch_data(info["ticker"], start_date, end_date)

    logger.info(f"데이터 병렬 수집 시작 (최대 {min(len(PORTFOLIO), 6)}개 동시)")
    with ThreadPoolExecutor(max_workers=min(len(PORTFOLIO), 6)) as executor:
        fetched = list(executor.map(_fetch_one, PORTFOLIO))

    results = []
    failed  = []

    for info, df in fetched:
        ticker = info["ticker"]

        if df is None or df.empty:
            logger.warning(f"[{ticker}] 데이터 수집 실패 - 건너뜁니다.")
            failed.append(ticker)
            continue

        data_date = df.index[-1].strftime("%Y-%m-%d")

        try:
            analysis = analyze_ticker(ticker, df, info)
            logger.info(f"[{ticker}] 분석 완료  현재가 ${analysis['current_price']:.2f}")
        except Exception as e:
            logger.error(f"[{ticker}] 분석 실패: {e}")
            failed.append(ticker)
            continue

        logger.info(f"[{ticker}] 예측 중 (1M/3M/6M/12M)...")
        predictions = predict_ticker(ticker, df, div_yield=analysis["div_yield"])
        logger.info(f"[{ticker}] 예측 완료")

        results.append({
            "analysis":    analysis,
            "predictions": predictions,
            "data_date":   data_date,
        })

    # 종목별 요약 출력
    logger.info("-" * 54)
    logger.info("  종목별 요약")
    logger.info("-" * 54)
    for r in results:
        a   = r["analysis"]
        p12 = r["predictions"].get("12m")
        pred_str = (
            f"예측(12M) ${p12.predicted_price:.2f} ({_fmt_pct(p12.predicted_return)})"
            if p12 is not None and p12.ok()
            else "12개월 예측 실패"
        )
        logger.info(
            f"  {a['ticker']:<5}  현재가 ${a['current_price']:>8.2f}  "
            f"과거 1년 {_fmt_pct(a['return_1y']):>7}  RSI {a['rsi']:>5.1f}  "
            f"{pred_str}"
        )

    if failed:
        logger.warning(f"수집/분석 실패 종목: {', '.join(failed)}")

    # Notion 리포트 저장
    logger.info("-" * 54)
    logger.info("Notion 리포트 저장 중...")
    try:
        page_url = write_report_to_notion(results)
        logger.info(f"저장 완료: {page_url}")
    except Exception as e:
        logger.error(f"Notion 저장 실패: {e}")
        page_url = None

    # 이메일 발송
    logger.info("-" * 54)
    logger.info("이메일 발송 중...")
    try:
        send_portfolio_alert(results, page_url)
    except Exception as e:
        logger.error(f"이메일 발송 실패: {e}")

    logger.info("=" * 54)
    logger.info("모든 작업 완료")
    logger.info("=" * 54)


if __name__ == "__main__":
    main()
