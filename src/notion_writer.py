import os
import time
from datetime import datetime
from notion_client import Client
from dotenv import load_dotenv
from src.portfolio_config import NOTION_PORTFOLIO_PAGE_ID

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


# ── Notion 클라이언트 ──────────────────────────────────────────

def _get_client():
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise EnvironmentError(
            "NOTION_TOKEN이 .env 파일에 없습니다. "
            "Notion 통합 토큰을 발급받아 설정해 주세요."
        )
    return Client(auth=token)


# ── 포맷 헬퍼 ─────────────────────────────────────────────────

def _fmt_price(v):
    return f"${v:.2f}" if v is not None else "N/A"

def _fmt_pct(v, plus=True):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 and plus else ""
    return f"{sign}{v:.2%}"

def _fmt_pct_pos(v):
    return _fmt_pct(v, plus=False)


# ── Notion 블록 빌더 ──────────────────────────────────────────

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

def _callout(text, emoji="📅", color="blue_background"):
    return {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [_text(text)],
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color,
        }
    }

def _paragraph(text):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [_text(text)]}}


# ── 종목 블록 생성 ────────────────────────────────────────────

def _rsi_bar(rsi):
    """RSI 값을 시각적 바로 표현."""
    filled = round(rsi / 10)
    return "█" * filled + "░" * (10 - filled)

def _build_ticker_blocks(result):
    a = result["analysis"]
    p = result["predictions"]
    blocks = []

    # 종목 헤딩
    weight_str = f"{a['weight']:.0%}" if a["weight"] > 0 else "보유 중"
    blocks.append(_heading3(
        f"{a['ticker']}  |  {a['name']}  ·  {a['category']}  [{weight_str}]"
    ))

    # 현재 상태
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

    # 기간별 수익률 (과거 실적)
    blocks.append(_bullet(
        f"YTD(올해) {_fmt_pct(a['ytd_return'])}  │  "
        f"1개월 전 {_fmt_pct(a['return_1m'])}  │  "
        f"3개월 전 {_fmt_pct(a['return_3m'])}  │  "
        f"6개월 전 {_fmt_pct(a['return_6m'])}  │  "
        f"1년 전 {_fmt_pct(a['return_1y'])}",
        bold_prefix="과거 수익률"
    ))

    # 기술적 지표
    vol_str = f"변동성(연율) {_fmt_pct_pos(a['annualized_vol'])}" if a["annualized_vol"] else ""
    blocks.append(_bullet(
        f"RSI {a['rsi']:.1f} [{_rsi_bar(a['rsi'])}] {a['rsi_signal']}  │  "
        f"MA추세 {a['ma_signal']}  │  "
        f"MA20 {_fmt_price(a['ma20'])} / MA60 {_fmt_price(a['ma60'])} / MA200 {_fmt_price(a['ma200'])}  │  "
        f"{vol_str}",
        bold_prefix="기술지표"
    ))

    # 예측 가격 (미래 기준)
    pred_lines = []
    period_labels = [
        ("1m",  "1개월 후",  "XGBoost"),
        ("3m",  "3개월 후",  "Prophet"),
        ("6m",  "6개월 후",  "Prophet"),
        ("12m", "12개월 후", "Prophet"),
    ]
    for key, label, method in period_labels:
        pred = p.get(key, {})
        if "error" in pred:
            pred_lines.append(f"{label} ({method}): 예측 실패")
            continue
        total_str = ""
        if key == "12m" and "total_return" in pred:
            total_str = f"  │  배당 포함 총수익 {_fmt_pct(pred['total_return'])}"
        pred_lines.append(
            f"{label} ({method}): {_fmt_price(pred['predicted_price'])} "
            f"({_fmt_pct(pred['predicted_return'])})  "
            f"예상 범위 {_fmt_price(pred['lower'])} ~ {_fmt_price(pred['upper'])}"
            f"{total_str}"
        )

    blocks.append(_bullet(
        "\n".join(pred_lines),
        bold_prefix="예측가 (오늘 기준)"
    ))

    blocks.append(_divider())
    return blocks


# ── 포트폴리오 요약 블록 ──────────────────────────────────────

def _build_summary_blocks(results, today):
    blocks = [
        _callout(
            f"분석 기준일: {today}  │  총 {len(results)}개 종목  │  매일 자동 업데이트",
            emoji="🤖",
            color="blue_background",
        ),
        _heading2("📊 포트폴리오 현황 요약"),
    ]

    # 카테고리별 그룹 요약
    categories = {}
    for r in results:
        cat = r["analysis"]["category"]
        categories.setdefault(cat, []).append(r["analysis"])

    for cat, items in categories.items():
        tickers = "  /  ".join(
            f"{a['ticker']} {_fmt_price(a['current_price'])} ({_fmt_pct(a['return_1m'])})"
            for a in items
        )
        blocks.append(_bullet(tickers, bold_prefix=cat))

    blocks.append(_divider())
    blocks.append(_heading2("📈 종목별 상세 분석"))
    return blocks


# ── 페이지 생성 (분할 append) ─────────────────────────────────

def _append_in_chunks(notion, page_id, blocks, chunk_size=50):
    for i in range(0, len(blocks), chunk_size):
        notion.blocks.children.append(
            block_id=page_id,
            children=blocks[i : i + chunk_size],
        )
        time.sleep(0.4)  # Rate limit 대응 (초당 3회 제한)


# [개선] has_more / next_cursor 페이지네이션으로 전체 하위 페이지 순회
def _iter_child_pages(notion, parent_id):
    """parent_id의 모든 하위 child_page 블록을 순회해 반환한다."""
    cursor = None
    while True:
        kwargs = {"block_id": parent_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            if block.get("type") == "child_page":
                yield block
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")


def write_report_to_notion(results):
    """
    💼 투자 포트폴리오 하위에 '📡 포트폴리오 분석 리포트 (날짜)' 페이지를 생성한다.
    같은 날짜의 기존 리포트가 있으면 아카이브 후 새로 생성한다.
    """
    notion = _get_client()
    today = datetime.today().strftime("%Y-%m-%d")
    page_title = f"📡 포트폴리오 분석 리포트 ({today})"

    # [개선] 페이지네이션으로 전체 하위 페이지를 순회해 당일 중복 리포트 아카이브
    for block in _iter_child_pages(notion, NOTION_PORTFOLIO_PAGE_ID):
        if today in block["child_page"].get("title", ""):
            notion.pages.update(block["id"], archived=True)
            print(f"  기존 리포트 아카이브: {block['child_page']['title']} (ID: {block['id']})")

    # 새 페이지 생성 (제목만, 내용은 이후 append)
    new_page = notion.pages.create(
        parent={"type": "page_id", "page_id": NOTION_PORTFOLIO_PAGE_ID},
        properties={
            "title": [{"type": "text", "text": {"content": page_title}}]
        },
    )
    page_id = new_page["id"]

    # 요약 섹션 추가
    summary_blocks = _build_summary_blocks(results, today)
    _append_in_chunks(notion, page_id, summary_blocks)

    # 종목별 섹션 추가
    for result in results:
        ticker_blocks = _build_ticker_blocks(result)
        _append_in_chunks(notion, page_id, ticker_blocks)

    page_url = new_page["url"]
    print(f"  노션 리포트 생성 완료: {page_url}")
    return page_url
