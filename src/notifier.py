import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)


# [개선] 내부 구현용으로 private 처리 (_send_email)
def _send_email(subject, body):
    sender_email    = os.getenv("EMAIL_ADDRESS")
    sender_password = os.getenv("EMAIL_PASSWORD")
    receiver_email  = os.getenv("TARGET_EMAIL")

    if not all([sender_email, sender_password, receiver_email]):
        print("  ⚠️  이메일 자격증명 누락 — .env 파일을 확인하세요.")
        return False

    msg = MIMEMultipart()
    msg["From"]    = sender_email
    msg["To"]      = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print(f"  ✅ 이메일 발송 완료 → {receiver_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        print(
            "  ❌ 이메일 인증 실패 (앱 비밀번호 만료 또는 오류)\n"
            "     해결 방법: Google 계정 → 보안 → 앱 비밀번호 → 새로 발급\n"
            "     발급 후 .env 의 EMAIL_PASSWORD 값을 교체하세요."
        )
        return False

    except smtplib.SMTPException as e:
        print(f"  ❌ SMTP 오류: {e}")
        return False

    except Exception as e:
        print(f"  ❌ 이메일 발송 실패: {e}")
        return False


# [개선] RSI 신호 필터링 및 이메일 본문 구성 로직을 notifier 내부로 이동
def send_portfolio_alert(results, notion_url):
    """
    RSI 과매수/과매도 신호를 필터링해 경량 이메일 알림을 발송한다.

    Parameters
    ----------
    results    : main.py의 results 리스트 (analysis + predictions 포함)
    notion_url : 당일 생성된 Notion 리포트 URL (None 허용)
    """
    today = datetime.today().strftime("%Y-%m-%d")

    # RSI 과매수(> 70) 또는 과매도(< 30) 종목 필터링
    signals = [
        r["analysis"] for r in results
        if r["analysis"]["rsi"] > 70 or r["analysis"]["rsi"] < 30
    ]
    n_signals = len(signals)

    subject = f"[포트폴리오 알림] {today} — 신호 {n_signals}개"

    lines = [
        f"기준일: {today}  |  분석 종목: {len(results)}개",
        "",
    ]

    if signals:
        lines += [
            "📌 과매수/과매도 신호 종목",
            "─" * 52,
            f"{'티커':<6} {'종목명':<18} {'RSI':>5}  {'신호':<5}  {'현재가':>10}  {'YTD':>8}",
            "─" * 52,
        ]
        for a in signals:
            ytd = f"{a['ytd_return']:+.2%}" if a["ytd_return"] is not None else "N/A"
            lines.append(
                f"{a['ticker']:<6} {a['name']:<18} {a['rsi']:>5.1f}  "
                f"{a['rsi_signal']:<5}  ${a['current_price']:>9.2f}  {ytd:>8}"
            )
        lines.append("─" * 52)
    else:
        lines.append("오늘은 과매수/과매도 신호가 없습니다.")

    lines += [
        "",
        "📊 상세 분석 리포트 (노션)",
        f"  {notion_url}" if notion_url else "  (리포트 URL 없음 — 노션 저장 실패)",
        "",
        "─" * 52,
        "Prophet + XGBoost 앙상블  |  매일 오전 7:00 자동 실행",
    ]

    body = "\n".join(lines)
    return _send_email(subject, body)
