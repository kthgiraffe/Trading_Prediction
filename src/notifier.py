import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)


def send_email(subject, body):
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
