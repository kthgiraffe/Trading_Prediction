# 노션 투자 포트폴리오 기준 종목 구성 (2026-05-16 기준)
# 출처: https://www.notion.so/361a527b807781d483c1fea659f98b22

PORTFOLIO = [
    {
        "ticker": "SCHD",
        "name": "슈왑 미국 배당주",
        "category": "고배당 저성장 ETF",
        "weight": 0.25,
        "div_freq": "분기",
    },
    {
        "ticker": "VIG",
        "name": "뱅가드 배당성장",
        "category": "고성장 저배당 ETF",
        "weight": 0.175,
        "div_freq": "분기",
    },
    {
        "ticker": "DGRO",
        "name": "iShares 배당성장",
        "category": "고성장 저배당 ETF",
        "weight": 0.175,
        "div_freq": "분기",
    },
    {
        "ticker": "VOO",
        "name": "뱅가드 S&P500",
        "category": "인덱스 ETF",
        "weight": 0.16,
        "div_freq": "분기",
    },
    {
        "ticker": "QQQ",
        "name": "인베스코 나스닥100",
        "category": "인덱스 ETF",
        "weight": 0.04,
        "div_freq": "분기",
    },
    {
        "ticker": "SPYM",
        "name": "스테이트 스트리트 S&P500",
        "category": "인덱스 ETF (VOO 대체재 · 실제 보유)",
        "weight": 0.0,
        "div_freq": "분기",
    },
    {
        "ticker": "JNJ",
        "name": "존슨앤존슨",
        "category": "해외 개별 배당주",
        "weight": 0.02,
        "div_freq": "분기",
    },
    {
        "ticker": "KO",
        "name": "코카콜라",
        "category": "해외 개별 배당주",
        "weight": 0.02,
        "div_freq": "분기",
    },
    {
        "ticker": "ABBV",
        "name": "애브비",
        "category": "해외 개별 배당주",
        "weight": 0.02,
        "div_freq": "분기",
    },
    {
        "ticker": "JPM",
        "name": "JP모건",
        "category": "해외 개별 배당주",
        "weight": 0.02,
        "div_freq": "분기",
    },
    {
        "ticker": "XOM",
        "name": "엑슨모빌",
        "category": "해외 개별 배당주",
        "weight": 0.02,
        "div_freq": "분기",
    },
    {
        "ticker": "O",
        "name": "리얼티인컴",
        "category": "월 배당 (독립)",
        "weight": 0.05,
        "div_freq": "월",
    },
]

# 노션 페이지 ID
# 투자 포트폴리오 최상위 페이지 (기존 분석 리포트 직속 저장용)
NOTION_PORTFOLIO_PAGE_ID = "361a527b-8077-81d4-83c1-fea659f98b22"

# 포트폴리오 분석 리포트 루트 페이지 ID
# 투자 포트폴리오 하위의 "포트폴리오 분석 리포트" 페이지
# 하위 구조: 연도 -> 월 -> 주간 -> 일별 리포트
NOTION_REPORT_ROOT_PAGE_ID = "36aa527b-8077-8118-9682-dfd23ea36a95"
