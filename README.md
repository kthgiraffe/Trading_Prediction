# Trading Prediction — Portfolio Analyzer

노션에 정리된 배당 성장 포트폴리오를 기반으로 12개 종목을 매일 자동 분석하고,
**Prophet + XGBoost 앙상블**로 1·3·6·12개월 후 가격을 예측하여 노션 리포트로 저장합니다.

> An automated portfolio analysis tool based on a dividend growth strategy.  
> Analyzes 12 tickers daily and predicts future prices using a **Prophet + XGBoost ensemble**, then saves the report directly to Notion.

---

## 주요 기능 / Key Features

- **종목 분석** — 현재가, 52주 범위, 기간별 수익률, RSI, 이동평균, 배당률  
  **Stock Analysis** — Current price, 52-week range, period returns, RSI, moving averages, dividend yield

- **가격 예측** — XGBoost(1개월) + Prophet(3·6·12개월) 앙상블, 80% 신뢰 구간 포함  
  **Price Prediction** — XGBoost (1M) + Prophet (3·6·12M) ensemble with 80% confidence intervals

- **노션 연동** — 매일 분석 리포트 페이지 자동 생성·업데이트  
  **Notion Integration** — Daily report page auto-created under your portfolio page

- **이메일 알림** — 과매수/과매도 신호 + 노션 리포트 링크 경량 발송  
  **Email Alert** — Lightweight daily signal summary with Notion report link

- **자동 실행** — Windows 작업 스케줄러로 매일 오전 7:00 KST 자동 실행  
  **Automation** — Runs daily at 07:00 KST via Windows Task Scheduler (2h after US market close)

---

## 분석 대상 종목 / Portfolio

| 티커 / Ticker | 종목명 / Name | 카테고리 / Category | 비중 / Weight |
|:---|:---|:---|:---:|
| SCHD | 슈왑 미국 배당주 | 고배당 저성장 ETF | 25% |
| VIG | 뱅가드 배당성장 | 고성장 저배당 ETF | 17.5% |
| DGRO | iShares 배당성장 | 고성장 저배당 ETF | 17.5% |
| VOO | 뱅가드 S&P500 | 인덱스 ETF | 16% |
| QQQ | 인베스코 나스닥100 | 인덱스 ETF | 4% |
| SPYM | 스테이트 스트리트 S&P500 | 인덱스 ETF (실제 보유) | — |
| JNJ | 존슨앤존슨 | 해외 개별 배당주 | 2% |
| KO | 코카콜라 | 해외 개별 배당주 | 2% |
| ABBV | 애브비 | 해외 개별 배당주 | 2% |
| JPM | JP모건 | 해외 개별 배당주 | 2% |
| XOM | 엑슨모빌 | 해외 개별 배당주 | 2% |
| O | 리얼티인컴 | 월 배당 (독립) | 5% |

---

## 예측 모델 / Prediction Model

| 구간 / Period | 모델 / Model | 특징 / Notes |
|:---|:---|:---|
| 1개월 후 / 1 Month | XGBoost + 기술적 지표 | RSI·MA·변동성 조합 패턴 학습, 분위수 회귀로 신뢰 구간 산출 |
| 3개월 후 / 3 Months | Prophet | 트렌드 + 주간·연간 계절성 |
| 6개월 후 / 6 Months | Prophet | 반기 리밸런싱 참고용 |
| 12개월 후 / 12 Months | Prophet + 배당 | 배당 포함 총수익률(Total Return) 추가 산출 |

---

## 프로젝트 구조 / Project Structure

```
Trading_Bot/
├── main.py                  # 실행 진입점 / Entry point
├── requirements.txt         # 의존성 (버전 고정) / Dependencies (pinned)
├── .env                     # 인증 정보 — Git 제외 / Credentials — Git-ignored
├── run_daily.bat            # 작업 스케줄러용 / For Task Scheduler
├── src/
│   ├── portfolio_config.py  # 종목 구성 · 노션 ID / Tickers & Notion page ID
│   ├── data_fetcher.py      # yfinance 데이터 수집 / Price data fetching
│   ├── analyzer.py          # 현황 분석 / Current state analysis
│   ├── predictor.py         # 가격 예측 앙상블 / Price prediction ensemble
│   ├── notion_writer.py     # 노션 리포트 생성 / Notion report writer
│   └── notifier.py          # 이메일 알림 / Email notification
└── docs/
    └── index.html           # 프로젝트 문서 / Project documentation
```

---

## 설치 및 실행 / Setup & Usage

### 1. 의존성 설치 / Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정 / Configure Environment

`.env` 파일을 생성하고 아래 값을 입력하세요.  
Create a `.env` file with the following values:

```
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_google_app_password
TARGET_EMAIL=your_email@gmail.com
NOTION_TOKEN=your_notion_integration_token
```

### 3. Notion 통합 연결 / Connect Notion Integration

1. [notion.so/my-integrations](https://notion.so/my-integrations) 에서 Internal Integration 생성  
   Create an Internal Integration at [notion.so/my-integrations](https://notion.so/my-integrations)
2. **💼 투자 포트폴리오** 페이지 → `···` → Connections → 통합 선택  
   Open the portfolio page → `···` → Connections → select your integration

### 4. 실행 / Run

```bash
python main.py
```

### 5. 자동 실행 등록 / Schedule Daily Run (Windows)

관리자 PowerShell에서 실행 / Run in Administrator PowerShell:

```powershell
$action  = New-ScheduledTaskAction -Execute "python.exe" -Argument "main.py" -WorkingDirectory "C:\...\Trading_Bot"
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "IVV_Trading_Bot" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force
```

---

## 의존성 / Dependencies

| 패키지 / Package | 용도 / Purpose | 버전 / Version |
|:---|:---|:---|
| yfinance | 주가 데이터 / Price data | 1.1.0 (고정) |
| prophet | 중·장기 예측 / Mid-long term prediction | latest |
| xgboost | 단기 예측 / Short-term prediction | 3.2.0 (고정) |
| scikit-learn | 특성 스케일링 / Feature scaling | latest |
| notion-client | Notion API 연동 | latest |
| pandas / numpy | 데이터 처리 / Data processing | latest |

---

## 주의사항 / Disclaimer

이 소프트웨어는 **교육 및 참고 목적**으로만 제작되었습니다. 특정 종목의 매수를 추천하지 않으며, 실제 투자 전 반드시 직접 조사하시기 바랍니다.

> This software is for **educational and reference purposes only**.  
> It does not constitute investment advice. Always do your own research before investing.
