import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

REQUIRED_ENV = ["NOTION_TOKEN", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "TARGET_EMAIL"]


def validate_env():
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"필수 환경변수가 누락되었습니다: {missing}\n"
            ".env 파일을 확인하거나 시스템 환경변수를 설정해주세요."
        )
