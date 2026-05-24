import os
import time
from datetime import datetime, date, timedelta
from notion_client import Client
from dotenv import load_dotenv
from src.portfolio_config import NOTION_REPORT_ROOT_PAGE_ID
from src.logger import get_logger

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

logger = get_logger(__name__)


# -- Notion 클라이언트 ---------------------------------------------------------

def _get_client():
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise EnvironmentError(
            "NOTION_TOKEN이 .env 파일에 없습니다. "
            "Notion 통합 토큰을 발급받아 설정해 주세요."
        )
    return Client(auth=token)


# -- 포맷 헬퍼 -----------------------------------------------------------------

def _fmt_price(v):
    return f"${v:.2f}" if v is not None else "N/A"

def _fmt_pct(v, plus=True):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 and plus else ""
    return f"{sign}{v:.2%}"

def _fmt_pct_pos(v):
    return _fmt_pct(v, plus=False)


# -- Notion 블록 빌더 ----------------------------------------------------------

def _text(content, bold=False, color="default"):
    t = {"type": "text", "text": {"content": content}}
    if bold or color != "default":
        t["annotations"] = {"bold": bold, "color": color}
    return t

def _heading2(text):
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [_text(text)]}}

def _heading3(text):
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [_text(text)]}}

def _bullet(text, bold_prefix=None):
    rich = []
    if bold_prefix:
        rich.append(_text(bold_prefix + " ", bold=True))
        rich.append(_text(text))
    else:
        rich.append(_text(text))
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich}}

def _divider():
    return {"object": "block", "type": "divider", "divider": {}}

def _callout(text, color="blue_background"):
    """아이콘 없이 배경색만 적용된 callout 블록을 반환한다."""
    return {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [_text(text)],
            "color": color,
        },
    }

def _paragraph(text):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [_text(text)]}}


# -- 종목 블록 생성 ------------------------------------------------------------

def _rsi_bar(rsi):
    """RSI 값(0~100)을 10칸 블록 바로 시각화한다."""
    filled = round(rsi / 10)
    return "[" + "#" * filled + "-" * (10 - filled) + "]"

def _build_ticker_blocks(result):
    a = result["analysis"]
    p = result["predictions"]
    blocks = []

    # 비중 표시: 소수점 없이 떨어지면 정수 포맷, 아니면 소수 첫째 자리까지 표시
    w = a["weight"]
    if w > 0:
        weight_str = f"{w:.0%}" if (w * 100) == int(w * 100) else f"{w:.1%}"
    else:
        weight_str = "보유 중"

    blocks.append(_heading3(
        f"{a['ticker']}  |  {a['name']}  ·  {a['category']}  [{weight_str}]"
    ))

    blocks.append(_bullet(
        f"{_fmt_price(a['current_price'])}  "
        f"(52주: {_fmt_price(a['low_52w'])} ~ {_fmt_price(a['high_52w'])}  "
        f"위치 {a['price_vs_52w_high']:.0%})",
        bold_prefix="현재가"
    ))
    blocks.append(_bullet(
        f"{_fmt_pct(a['div_yield'], plus=False)}  ({a['div_freq']} 지급)",
        bold_prefix="배당률"
    ))
    blocks.append(_bullet(
        f"YTD(올해) {_fmt_pct(a['ytd_return'])}  |  "
        f"1개월 전 {_fmt_pct(a['return_1m'])}  |  "
        f"3개월 전 {_fmt_pct(a['return_3m'])}  |  "
        f"6개월 전 {_fmt_pct(a['return_6m'])}  |  "
        f"1년 전 {_fmt_pct(a['return_1y'])}",
        bold_prefix="과거 수익률"
    ))

    vol_str = f"변동성(연율) {_fmt_pct_pos(a['annualized_vol'])}" if a["annualized_vol"] else ""
    blocks.append(_bullet(
        f"RSI {a['rsi']:.1f} {_rsi_bar(a['rsi'])} {a['rsi_signal']}  |  "
        f"MA추세 {a['ma_signal']}  |  "
        f"MA20 {_fmt_price(a['ma20'])} / MA60 {_fmt_price(a['ma60'])} / MA200 {_fmt_price(a['ma200'])}  |  "
        f"{vol_str}",
        bold_prefix="기술지표"
    ))

    # PredictionResult 속성으로 접근하고 ok()로 성공 여부를 판단한다
    pred_lines = []
    period_labels = [
        ("1m",  "1개월 후",  "XGBoost"),
        ("3m",  "3개월 후",  "Prophet"),
        ("6m",  "6개월 후",  "Prophet"),
        ("12m", "12개월 후", "Prophet"),
    ]
    for key, label, method in period_labels:
        pred = p.get(key)
        if pred is None or not pred.ok():
            pred_lines.append(f"{label} ({method}): 예측 실패")
            continue
        total_str = ""
        if key == "12m" and pred.total_return is not None:
            total_str = f"  |  배당 포함 총수익 {_fmt_pct(pred.total_return)}"
        pred_lines.append(
            f"{label} ({method}): {_fmt_price(pred.predicted_price)} "
            f"({_fmt_pct(pred.predicted_return)})  "
            f"예상 범위 {_fmt_price(pred.lower)} ~ {_fmt_price(pred.upper)}"
            f"{total_str}"
        )

    blocks.append(_bullet("\n".join(pred_lines), bold_prefix="예측가 (오늘 기준)"))

    # 펀더멘털 지표 섹션 (배당 CAGR, Payout/FCF, PER 밴드)
    blocks.extend(_build_fundamentals_blocks(a))

    blocks.append(_divider())
    return blocks


def _build_fundamentals_blocks(a: dict) -> list:
    """
    펀더멘털 지표(배당 CAGR, Payout Ratio/FCF, PER 밴드)를 Notion 블록 리스트로 변환한다.
    데이터가 없는 항목은 출력에서 조용히 생략한다.
    """
    blocks = []
    div_cagr   = a.get("div_cagr") or {}
    payout     = a.get("payout_fcf") or {}
    per        = a.get("per_band") or {}

    # -- 배당 CAGR 및 Yield on Cost -------------------------------------------
    cagr_5y  = div_cagr.get("cagr_5y")
    cagr_10y = div_cagr.get("cagr_10y")
    yoc_5y   = div_cagr.get("yoc_5y")
    yoc_10y  = div_cagr.get("yoc_10y")

    if cagr_5y is not None or cagr_10y is not None:
        parts = [p for p in [
            f"5년: {cagr_5y:.1%}" if cagr_5y is not None else None,
            f"10년: {cagr_10y:.1%}" if cagr_10y is not None else None,
        ] if p]
        blocks.append(_bullet("  |  ".join(parts), bold_prefix="배당 CAGR"))

    if yoc_5y is not None or yoc_10y is not None:
        div_yield = a.get("div_yield") or 0.0
        parts = [p for p in [
            f"5년 후: {yoc_5y:.1%}" if yoc_5y is not None else None,
            f"10년 후: {yoc_10y:.1%}" if yoc_10y is not None else None,
            f"(현재 배당률 {div_yield:.1%} 기준)" if div_yield > 0 else None,
        ] if p]
        blocks.append(_bullet("  |  ".join(parts), bold_prefix="Yield on Cost"))

    # -- Payout Ratio + FCF 커버리지 ------------------------------------------
    pr      = payout.get("payout_ratio")
    fcf_pr  = payout.get("fcf_payout_ratio")
    warning = payout.get("warning")
    is_reit = payout.get("is_reit", False)

    if pr is not None or fcf_pr is not None:
        parts = [p for p in [
            f"Payout Ratio: {pr:.0%}" if pr is not None else None,
            f"FCF 커버리지: {fcf_pr:.0%}" if fcf_pr is not None else None,
            "(REIT — EPS 기준 해석 주의)" if is_reit else None,
        ] if p]
        blocks.append(_bullet("  |  ".join(parts), bold_prefix="배당 지속성"))
        if warning:
            blocks.append(_bullet(f"[주의] {warning}"))

    # -- PER 밴드 (ETF 제외, per_band 데이터가 있는 경우에만 출력) ---------------
    current_pe  = per.get("current_pe")
    pe_low      = per.get("pe_low")
    pe_mid      = per.get("pe_mid")
    pe_high     = per.get("pe_high")
    fair_val    = per.get("fair_value")
    valuation   = per.get("valuation")
    current_price = a.get("current_price")

    if current_pe is not None and pe_mid is not None:
        pe_text = (
            f"현재 PER: {current_pe:.1f}x  |  "
            f"역사적 범위: {pe_low:.1f}x ~ {pe_high:.1f}x (중간: {pe_mid:.1f}x)"
        )
        blocks.append(_bullet(pe_text, bold_prefix="밸류에이션"))

        if fair_val is not None and current_price is not None:
            val_label_map = {
                "undervalued": "저평가",
                "fair": "적정",
                "overvalued": "고평가",
            }
            val_label = val_label_map.get(valuation, "")
            diff_pct = (current_price - fair_val) / fair_val
            direction = "고평가" if diff_pct > 0 else "저평가"
            fair_text = (
                f"적정가 추정: ${fair_val:.2f}  |  "
                f"현재가 대비: {abs(diff_pct):.1%} {direction}  [{val_label}]"
            )
            blocks.append(_bullet(fair_text))

    return blocks


# -- 포트폴리오 요약 블록 ------------------------------------------------------

def _build_summary_blocks(results, today, data_date):
    """실행일/데이터 기준일 callout과 카테고리별 현황 요약 블록을 반환한다."""
    blocks = [
        _callout(
            f"실행일: {today}  |  데이터 기준일: {data_date}  |  "
            f"총 {len(results)}개 종목  |  매일 자동 업데이트",
            color="blue_background",
        ),
        _heading2("포트폴리오 현황 요약"),
    ]

    categories = {}
    for r in results:
        cat = r["analysis"]["category"]
        categories.setdefault(cat, []).append(r["analysis"])

    for cat, items in categories.items():
        tickers = "  /  ".join(
            f"{a['ticker']} {_fmt_price(a['current_price'])} ({_fmt_pct(a['return_1m'])})"
            for a in items
        )
        blocks.append(_bullet(tickers, bold_prefix=f"[{cat}]"))

    blocks.append(_divider())
    blocks.append(_heading2("종목별 상세 분석"))
    return blocks


# -- Notion API 유틸 -----------------------------------------------------------

def _append_in_chunks(notion, page_id, blocks, chunk_size=50):
    """Notion Rate Limit(초당 3회) 대응을 위해 블록을 chunk_size 단위로 나눠 추가한다."""
    for i in range(0, len(blocks), chunk_size):
        notion.blocks.children.append(
            block_id=page_id,
            children=blocks[i : i + chunk_size],
        )
        time.sleep(0.4)


def _find_or_create_child_page(notion, parent_id: str, title: str) -> str:
    """
    parent_id 하위에서 title과 일치하는 child_page를 탐색한다.
    존재하지 않으면 해당 제목으로 새 페이지를 생성하고 페이지 ID를 반환한다.
    has_more / next_cursor 페이지네이션으로 전체 하위 페이지를 순회한다.
    """
    cursor = None
    while True:
        kwargs = {"block_id": parent_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            if block.get("type") == "child_page":
                if block["child_page"].get("title") == title:
                    return block["id"]
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    page = notion.pages.create(
        parent={"type": "page_id", "page_id": parent_id},
        properties={"title": [{"type": "text", "text": {"content": title}}]},
    )
    logger.info(f"하위 페이지 생성: '{title}'")
    return page["id"]


# -- 연도/월/주간 계층 구조 헬퍼 -----------------------------------------------

def _get_week_range(d: date):
    """ISO 주차 기준 월요일~일요일 날짜 범위를 반환한다."""
    iso = d.isocalendar()
    year, week_num = iso[0], iso[1]
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return year, week_num, monday, sunday


def _format_week_title(week_num: int, monday: date, sunday: date) -> str:
    """'W{번호} ({월.일} - {월.일})' 형식 주간 페이지 제목을 반환한다."""
    return f"W{week_num:02d} ({monday.strftime('%m.%d')} - {sunday.strftime('%m.%d')})"


def _format_month_title(d: date) -> str:
    """'{월:02d} - {영어월}' 형식 월 페이지 제목을 반환한다 (예: '05 - May')."""
    return d.strftime("%m - %b")


def _resolve_target_page_id(notion, run_date: date) -> str:
    """
    실행일 기준 연도/월/주간 페이지를 순서대로 탐색하고, 없으면 자동 생성한다.
    리포트를 저장할 주간 페이지 ID를 반환한다.

    저장 구조:
        포트폴리오 분석 리포트 (NOTION_REPORT_ROOT_PAGE_ID)
        └── 2026
            └── 05 - May
                └── W21 (05.18 - 05.24)
                    └── 분석 리포트 (날짜)
    """
    year, week_num, monday, sunday = _get_week_range(run_date)
    year_title  = str(year)
    month_title = _format_month_title(run_date)
    week_title  = _format_week_title(week_num, monday, sunday)

    year_id  = _find_or_create_child_page(notion, NOTION_REPORT_ROOT_PAGE_ID, year_title)
    month_id = _find_or_create_child_page(notion, year_id, month_title)
    week_id  = _find_or_create_child_page(notion, month_id, week_title)
    return week_id


# -- 퍼블릭 API ----------------------------------------------------------------

def write_report_to_notion(results):
    """
    실행일 기준 연도/월/주간 계층 구조 하위에 당일 리포트 페이지를 생성한다.
    같은 날짜의 기존 리포트가 주간 페이지 내에 있으면 아카이브 후 새로 생성한다.
    """
    notion   = _get_client()
    run_date = date.today()
    today    = run_date.strftime("%Y-%m-%d")

    # 종목별 data_date 중 가장 최신 날짜를 대표 기준일로 사용한다
    data_date = max(
        (r.get("data_date", today) for r in results),
        default=today,
    )

    # 저장 대상 주간 페이지를 탐색하거나 자동 생성한다
    target_page_id = _resolve_target_page_id(notion, run_date)

    page_title = f"분석 리포트 ({today} 실행 / 데이터 기준: {data_date})"

    # 주간 페이지 내에서 당일 중복 리포트를 탐색해 아카이브한다
    resp = notion.blocks.children.list(block_id=target_page_id)
    for block in resp.get("results", []):
        if block.get("type") == "child_page":
            if today in block["child_page"].get("title", ""):
                notion.pages.update(block["id"], archived=True)
                logger.info(f"기존 리포트 아카이브: {block['child_page']['title']}")

    new_page = notion.pages.create(
        parent={"type": "page_id", "page_id": target_page_id},
        properties={"title": [{"type": "text", "text": {"content": page_title}}]},
    )
    page_id = new_page["id"]

    summary_blocks = _build_summary_blocks(results, today, data_date)
    _append_in_chunks(notion, page_id, summary_blocks)

    for result in results:
        ticker_blocks = _build_ticker_blocks(result)
        _append_in_chunks(notion, page_id, ticker_blocks)

    page_url = new_page["url"]
    logger.info(f"리포트 생성 완료: {page_url}")
    return page_url
