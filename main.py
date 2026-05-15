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
from src.notifier import send_email


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
    print(f"  예측 방식 : 1M 선형회귀  |  3·6·12M Prophet")
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

    # 주요 신호 추출
    overbought = [r["analysis"]["ticker"] for r in results if r["analysis"]["rsi"] > 70]
    oversold   = [r["analysis"]["ticker"] for r in results if r["analysis"]["rsi"] < 30]
    ma_up      = [r["analysis"]["ticker"] for r in results if r["analysis"]["ma_signal"] == "상승"]

    lines = [
        f"오늘의 포트폴리오 분석 리포트가 준비됐습니다.",
        f"기준일: {today} 오전 7:00",
        "",
        "─" * 40,
        "📌 주요 신호",
        f"  과매수(RSI > 70) : {', '.join(overbought) if overbought else '없음'}",
        f"  과매도(RSI < 30) : {', '.join(oversold)   if oversold   else '없음'}",
        f"  MA 상승 추세     : {', '.join(ma_up)       if ma_up      else '없음'}",
        "",
    ]

    if page_url:
        lines += [
            "📊 상세 분석 리포트 (노션)",
            f"  {page_url}",
            "",
        ]

    lines += [
        "─" * 40,
        f"분석 종목 {len(results)}개  |  Prophet + 선형회귀 앙상블",
        "매일 오전 7:00 자동 실행",
    ]

    email_body = "\n".join(lines)

    try:
        send_email(f"[포트폴리오 분석] {today}", email_body)
    except Exception as e:
        print(f"  ❌ 이메일 발송 실패: {e}")

    print(f"\n{'='*54}")
    print("  ✅ 모든 작업 완료")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
