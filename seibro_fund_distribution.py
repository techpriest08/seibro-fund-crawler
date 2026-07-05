"""
세이브로 (SEIBro) 펀드 분배금 크롤러 - 초기 스켈레톤
=====================================================
대상: 권리행사정보 > 펀드별분배금지급내역
URL: https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/fund/BIP_CNTS05008V.xml&menuNo=152

사전 준비:
    pip install -r requirements.txt
    playwright install chromium

사용법:
    python seibro_fund_distribution.py

주의:
- 세이브로는 WebSquare 프레임워크 사용. 자동생성 ID 라서 셀렉터 잡기 까다로움.
- 첫 실행은 headless=False 상태로 두고 실제 페이지 흐름 확인 후 셀렉터 조정 필요.
- Claude Code 안에서 이 파일 열고 실제 페이지 열어보면서 셀렉터 붙이는 걸 추천.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SEIBRO_URL = (
    "https://seibro.or.kr/websquare/control.jsp"
    "?w2xPath=/IPORTAL/user/fund/BIP_CNTS05008V.xml&menuNo=152"
)


@dataclass
class FundQuery:
    """조회 대상 펀드."""
    name: str                       # 펀드명 부분 검색어. 예: "이스트스프링 뱅크론"
    isin: str | None = None         # 표준코드 (KR로 시작하는 12자리). 있으면 우선 사용.


def _wait_websquare(page: Page, extra_sleep: float = 2.0) -> None:
    """WebSquare 초기화 대기. networkidle 만으로는 부족한 경우가 많음."""
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(extra_sleep)


def _open_fund_search_popup(page: Page) -> Page:
    """
    펀드 검색 팝업 열기.

    세이브로는 돋보기 아이콘 클릭 → 별도 팝업 창으로 검색창 오픈.
    실제 셀렉터는 페이지 열어서 확인 후 조정 필요.
    """
    # TODO: 실제 셀렉터 확인 후 아래 수정
    #   Claude Code 안에서 headless=False 로 열고 DevTools 로 확인.
    #   후보: img[id*='btn_search'], a[id*='searchPopup'], input[title*='검색']
    with page.expect_popup() as popup_info:
        page.click("img[id*='search'], a[id*='search']", timeout=5000)
    popup = popup_info.value
    popup.wait_for_load_state("networkidle")
    return popup


def _search_fund_in_popup(popup: Page, keyword: str) -> None:
    """팝업 창에서 펀드명 검색."""
    # TODO: 실제 셀렉터로 교체
    popup.fill("input[id*='searchWord'], input.wq_uuid_input", keyword)
    popup.keyboard.press("Enter")
    _wait_websquare(popup, extra_sleep=1.0)

    # 첫 검색 결과 클릭
    popup.click("table.gridTable tbody tr:first-child, "
                "div[class*='gridRow']:first-child",
                timeout=5000)
    time.sleep(1)


def _set_date_range(page: Page, start: str, end: str) -> None:
    """조회 기간 설정 (YYYYMMDD)."""
    # TODO: 실제 셀렉터로 교체
    page.fill("input[id*='StrtDt'], input[id*='startDt']", start)
    page.fill("input[id*='EndDt'], input[id*='endDt']", end)


def _click_inquire(page: Page) -> None:
    """조회 버튼 클릭."""
    # 세이브로는 '조회' 텍스트 링크나 이미지 버튼 사용
    page.click("a:has-text('조회'), button:has-text('조회'), "
               "img[alt='조회']", timeout=5000)
    _wait_websquare(page, extra_sleep=2.0)


def _parse_result_table(page: Page) -> list[list[str]]:
    """
    결과 테이블 파싱.

    세이브로 gridTable 구조는 일반 HTML table 이 아닌 div 기반일 수 있음.
    첫 실행 시 실제 구조 확인 후 파서 조정.
    """
    rows_data: list[list[str]] = []

    # 시도 1: 일반 table
    table_rows = page.query_selector_all(
        "table.gridTable tbody tr, table[id*='grid'] tbody tr"
    )
    for row in table_rows:
        cells = row.query_selector_all("td")
        if cells:
            rows_data.append([c.inner_text().strip() for c in cells])

    # 시도 2: div 기반 그리드 (WebSquare 커스텀)
    if not rows_data:
        div_rows = page.query_selector_all("div[class*='gridBodyDefault'] "
                                            "div[class*='gridRowDefault']")
        for row in div_rows:
            cells = row.query_selector_all("div[class*='gridCell']")
            if cells:
                rows_data.append([c.inner_text().strip() for c in cells])

    return rows_data


def crawl_fund_distribution(
    fund: FundQuery,
    start_date: str | None = None,
    end_date: str | None = None,
    headless: bool = False,
    screenshot_dir: Path | None = None,
) -> pd.DataFrame:
    """
    특정 펀드의 분배금 지급 내역을 세이브로에서 크롤링.

    Args:
        fund: 조회 대상 펀드 (FundQuery)
        start_date: YYYYMMDD. None이면 3년 전
        end_date:   YYYYMMDD. None이면 오늘
        headless:   True면 백그라운드. 개발 중엔 False 권장
        screenshot_dir: 디버깅용 스크린샷 저장 폴더. None이면 저장 안 함.

    Returns:
        분배금 이력 DataFrame
    """
    start_date = start_date or (datetime.now() - timedelta(days=3 * 365)).strftime("%Y%m%d")
    end_date = end_date or datetime.now().strftime("%Y%m%d")

    log.info("펀드 조회 시작: %s (%s ~ %s)", fund.name, start_date, end_date)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()

        try:
            # 1) 페이지 접속
            page.goto(SEIBRO_URL, wait_until="domcontentloaded")
            _wait_websquare(page)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "01_landing.png")

            # 2) 펀드 검색 팝업 열고 선택
            popup = _open_fund_search_popup(page)
            _search_fund_in_popup(popup, fund.isin or fund.name)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "02_after_select.png")

            # 3) 조회 기간 설정
            _set_date_range(page, start_date, end_date)

            # 4) 조회
            _click_inquire(page)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "03_result.png")

            # 5) 결과 파싱
            rows = _parse_result_table(page)
            log.info("파싱된 행 개수: %d", len(rows))

        except PWTimeout as e:
            log.error("타임아웃: %s", e)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "error.png")
            rows = []
        finally:
            browser.close()

    # 컬럼명은 실제 페이지 확인 후 조정 필요
    # 예상: [결산일, 지급일, 1좌당 분배금, 과세대상소득, 세후 분배금, ...]
    columns_guess = ["결산일", "지급일", "1좌당분배금", "과세대상소득", "세후분배금"]
    if not rows:
        return pd.DataFrame(columns=columns_guess)

    n_cols = len(rows[0])
    columns = columns_guess[:n_cols] if n_cols <= len(columns_guess) \
        else columns_guess + [f"col{i}" for i in range(n_cols - len(columns_guess))]
    return pd.DataFrame(rows, columns=columns)


def batch_crawl(funds: list[FundQuery], output_csv: str = "distributions.csv") -> pd.DataFrame:
    """여러 펀드를 순차 조회하고 하나의 CSV 로 합침."""
    all_dfs = []
    for fund in funds:
        df = crawl_fund_distribution(fund, headless=True)
        df.insert(0, "펀드명", fund.name)
        df.insert(1, "ISIN", fund.isin or "")
        all_dfs.append(df)
        time.sleep(2)  # rate limit 회피

    combined = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
    combined.to_csv(output_csv, index=False, encoding="utf-8-sig")
    log.info("저장 완료: %s (총 %d행)", output_csv, len(combined))
    return combined


if __name__ == "__main__":
    # 개발/디버깅 모드: 브라우저 열고 스크린샷 저장
    Path("debug_screenshots").mkdir(exist_ok=True)

    test_fund = FundQuery(name="뱅크론")  # 검색어만 넣으면 팝업에서 첫 결과 선택
    df = crawl_fund_distribution(
        fund=test_fund,
        start_date="20230101",
        end_date="20260630",
        headless=False,
        screenshot_dir=Path("debug_screenshots"),
    )
    print(df)
    df.to_csv("test_result.csv", index=False, encoding="utf-8-sig")
