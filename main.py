import sys
import warnings
from datetime import datetime, timedelta

import pandas as pd

warnings.filterwarnings("ignore")
pd.options.mode.chained_assignment = None
sys.stdout.reconfigure(encoding="utf-8")

from src.portfolio_config import PORTFOLIO
from src.data_fetcher import fetch_data
from src.analyzer import analyze_ticker
from src.predictor import predict_ticker
from src.notion_writer import write_report_to_notion
from src.notifier import send_portfolio_alert


def _fmt_pct(v):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2%}"


def main():
    today = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    print(f"\n{'='*54}")
    print(f"  📡 포트폴리오 분석 리포트  ({today})")
    print(f"{'='*54}")
    print(f"  분석 종목 : {len(PORTFOLIO)}개")
    print(f"  데이터 기간: {start_date} ~ {today} (3년)")
    print(f"  예측 방식 : 1M XGBoost  |  3·6·12M Prophet")
    print(f"{'='*54}\n")

    results = []
    failed = []

    for info in PORTFOLIO:
        ticker = info["ticker"]
        print(f"[{ticker}] 데이터 수집 중...", end=" ", flush=True)

        df = fetch_data(ticker, start_date, today)
        if df is None or df.empty:
            print("실패 — 건너뜁니다.")
            failed.append(ticker)
            continue
        print("완료")

        print(f"[{ticker}] 분석 중...", end=" ", flush=True)
        analysis = analyze_ticker(ticker, df, info)
        print(f"현재가 ${analysis['current_price']:.2f}")

        print(f"[{ticker}] 예측 중 (1M/3M/6M/12M)...", end=" ", flush=True)
        predictions = predict_ticker(ticker, df, div_yield=analysis["div_yield"])
        print("완료")

        results.append({"analysis": analysis, "predictions": predictions})

    # ── 콘솔 요약 출력 ────────────────────────────────────────
    print(f"\n{'─'*54}")
    print("  종목별 요약")
    print(f"{'─'*54}")
    for r in results:
        a = r["analysis"]
        p = r["predictions"]
        p12 = p.get("12m", {})
        pred_str = (
            f"예측(12개월 후) ${p12['predicted_price']:.2f} ({_fmt_pct(p12['predicted_return'])})"
            if "error" not in p12
            else "12개월 후 예측 실패"
        )
        print(
            f"  {a['ticker']:<5}  현재가 ${a['current_price']:>8.2f}  "
            f"과거 1년 {_fmt_pct(a['return_1y']):>7}  RSI {a['rsi']:>5.1f}  "
            f"{pred_str}"
        )

    if failed:
        print(f"\n  ⚠️  데이터 수집 실패 종목: {', '.join(failed)}")

    # ── 노션 리포트 저장 ──────────────────────────────────────
    print(f"\n{'─'*54}")
    print("  노션 리포트 저장 중...")
    try:
        page_url = write_report_to_notion(results)
        print(f"  ✅ 저장 완료: {page_url}")
    except Exception as e:
        print(f"  ❌ 노션 저장 실패: {e}")
        page_url = None

    # ── 이메일 발송 (경량 알림) ───────────────────────────────
    print(f"\n{'─'*54}")
    print("  이메일 발송 중...")
    try:
        send_portfolio_alert(results, page_url)
    except Exception as e:
        print(f"  ❌ 이메일 발송 실패: {e}")

    print(f"\n{'='*54}")
    print("  ✅ 모든 작업 완료")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
