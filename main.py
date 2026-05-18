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
    # [수정] 필수 환경변수 검증 — 누락 시 명확한 오류 메시지와 함께 즉시 종료
    validate_env()

    today = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    # [수정] yfinance는 end_date를 exclusive로 처리하므로 내일 날짜로 설정해 오늘 종가까지 포함
    end_date = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info("=" * 54)
    logger.info(f"  📡 포트폴리오 분석 리포트  ({today})")
    logger.info("=" * 54)
    logger.info(f"  분석 종목 : {len(PORTFOLIO)}개")
    logger.info(f"  데이터 기간: {start_date} ~ {today} (3년)")
    logger.info("  예측 방식 : 1M XGBoost  |  3·6·12M Prophet")
    logger.info("=" * 54)

    # [수정] 병렬 fetch — ThreadPoolExecutor로 12개 종목을 동시 수집해 시간 단축
    def _fetch_one(info):
        ticker = info["ticker"]
        logger.info(f"[{ticker}] 데이터 수집 중...")
        df = fetch_data(ticker, start_date, end_date)
        return info, df

    logger.info(f"데이터 병렬 수집 시작 (최대 {min(len(PORTFOLIO), 6)}개 동시)")
    with ThreadPoolExecutor(max_workers=min(len(PORTFOLIO), 6)) as executor:
        # PORTFOLIO 순서를 유지하기 위해 executor.map 사용
        fetched = list(executor.map(_fetch_one, PORTFOLIO))

    results = []
    failed = []

    for info, df in fetched:
        ticker = info["ticker"]

        if df is None or df.empty:
            logger.warning(f"[{ticker}] 데이터 수집 실패 — 건너뜁니다.")
            failed.append(ticker)
            continue

        # [수정] 실제로 가져온 마지막 데이터 날짜를 출력해 최신 여부 확인
        data_date = df.index[-1].strftime("%Y-%m-%d")
        logger.info(f"[{ticker}] 수집 완료  (마지막 데이터: {data_date})")

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

        # [수정] data_date 필드를 result에 포함시켜 notion_writer에서 리포트 제목에 반영
        results.append({"analysis": analysis, "predictions": predictions, "data_date": data_date})

    # ── 콘솔 요약 출력 ────────────────────────────────────────
    logger.info("─" * 54)
    logger.info("  종목별 요약")
    logger.info("─" * 54)
    for r in results:
        a = r["analysis"]
        p = r["predictions"]
        # [수정] PredictionResult 속성 접근 + ok() 로 성공 여부 판단
        p12 = p.get("12m")
        pred_str = (
            f"예측(12개월 후) ${p12.predicted_price:.2f} ({_fmt_pct(p12.predicted_return)})"
            if p12 is not None and p12.ok()
            else "12개월 후 예측 실패"
        )
        logger.info(
            f"  {a['ticker']:<5}  현재가 ${a['current_price']:>8.2f}  "
            f"과거 1년 {_fmt_pct(a['return_1y']):>7}  RSI {a['rsi']:>5.1f}  "
            f"{pred_str}"
        )

    if failed:
        logger.warning(f"데이터 수집/분석 실패 종목: {', '.join(failed)}")

    # ── 노션 리포트 저장 ──────────────────────────────────────
    logger.info("─" * 54)
    logger.info("노션 리포트 저장 중...")
    try:
        page_url = write_report_to_notion(results)
        logger.info(f"저장 완료: {page_url}")
    except Exception as e:
        logger.error(f"노션 저장 실패: {e}")
        page_url = None

    # ── 이메일 발송 (경량 알림) ───────────────────────────────
    logger.info("─" * 54)
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
