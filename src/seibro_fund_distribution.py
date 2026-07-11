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
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# PyInstaller로 묶은 exe 안에서는 Playwright가 브라우저 위치를 실행 시 임시로
# 압축 해제되는 폴더(_MEIxxxxx) 기준으로 찾으려다 실패한다
# ("BrowserType.launch: Executable doesn't exist at ..._MEIxxxxx\playwright\..."
# 오류로 실측 확인). `playwright install chromium` 으로 실제 설치되는 위치인
# 사용자 전역 캐시(%LOCALAPPDATA%\ms-playwright) 를 명시적으로 지정해서 우회한다.
# playwright.sync_api를 import 하기 전에 설정해야 적용된다.
if sys.platform == "win32":
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH",
        os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright"),
    )

import pandas as pd
from playwright.sync_api import (
    Error as PWError,
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

# Windows 콘솔은 기본 코드페이지가 cp949라서, UTF-8 로그 문자열을 그대로 찍으면
# 한글이 깨져 보인다("1�Ⱓ �й�..." 식). 콘솔 출력 코드페이지와 stdout/stderr
# 인코딩을 UTF-8로 강제해서 어떤 터미널(cmd/PowerShell/Windows Terminal)에서
# 실행하든 한글이 정상적으로 보이게 한다.
if sys.platform == "win32":
    import ctypes

    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

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

# 펀드종합정보 > 기준가/분배금 탭. 일별 기준가·순자산(AUM)·분배금을 같이 제공함.
FUND_NAV_URL = (
    "https://seibro.or.kr/websquare/control.jsp"
    "?w2xPath=/IPORTAL/user/fund/BIP_CNTS05011V.xml&menuNo=155"
)


@dataclass
class FundQuery:
    """조회 대상 펀드."""
    name: str                       # 펀드명 부분 검색어. 예: "이스트스프링 뱅크론"
    isin: str | None = None         # 표준코드 (KR로 시작). 있으면 검색 결과 중 이 펀드를 정확히 선택.


def _wait_websquare(page: Page, extra_sleep: float = 2.0) -> None:
    """
    WebSquare 초기화 대기. networkidle 만으로는 부족한 경우가 많음.

    실측(뱅크론 조회): 사이트가 느린 시간대에는 networkidle 이 15초 안에 안
    와서 여기서 조회 전체가 죽는 경우가 있었다. networkidle 미도달이 곧
    "페이지를 못 쓴다"는 뜻은 아니므로(백그라운드 요청이 계속 도는 것뿐일 수
    있음) 타임아웃이면 경고만 남기고 여유 시간을 더 준 뒤 그대로 진행한다.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        log.warning("networkidle 15초 초과 - 3초 더 기다린 후 그대로 진행")
        time.sleep(3)
    time.sleep(extra_sleep)


def _install_chromium(only_shell: bool = True) -> None:
    """
    크롤링용 Chromium 이 없을 때 최초 1회 자동 다운로드.

    playwright 드라이버(node.exe + cli.js)는 PyInstaller exe 안에도 같이
    번들되므로, exe 만 복사해 간 컴퓨터에서도 이 함수로 브라우저를 받아올 수
    있다 ("Executable doesn't exist" 오류의 근본 해결). headless=True 만 쓰는
    GUI 기준으로는 headless shell 만 있으면 되므로 --only-shell 로 용량을
    아낀다 (~120MB). 다운로드 위치는 PLAYWRIGHT_BROWSERS_PATH.
    """
    import subprocess

    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    env = get_driver_env()
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH",
        os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright"),
    )
    args = [node, cli, "install", "chromium"]
    if only_shell:
        args.append("--only-shell")
    log.warning("크롤링용 브라우저가 없어 자동 다운로드를 시작합니다 (~120MB, 몇 분 소요)")
    # GUI(windowed) exe 에서 콘솔 창이 번쩍 뜨지 않게
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        subprocess.run(args, env=env, check=True, creationflags=creationflags, timeout=1800)
    except Exception as e:  # noqa: BLE001 - 원인 불문 사용자 안내로 변환
        raise RuntimeError(
            "크롤링용 브라우저 자동 설치에 실패했습니다. 인터넷 연결을 확인한 뒤 "
            "다시 시도해주세요."
        ) from e
    log.info("브라우저 자동 설치 완료")


def _launch_chromium(p, headless: bool):
    """
    chromium 실행. 브라우저 미설치("Executable doesn't exist")면 자동 설치 후
    1회 재시도한다. headless=False (개발용)면 전체 Chromium 을 받는다.
    """
    try:
        return p.chromium.launch(headless=headless)
    except PWError as e:
        if "Executable doesn't exist" not in str(e):
            raise
        _install_chromium(only_shell=headless)
        return p.chromium.launch(headless=headless)


def _goto_with_retry(page: Page, url: str, ready_selector: str, retries: int = 2) -> None:
    """
    세이브로 페이지 접속 + 오류 페이지 감지 시 재시도.

    실측(2026-07-11 22시경): 세이브로가 간헐적으로/시간대에 따라
    "한국예탁결제원 홈페이지 Error 안내 - 요청하신 페이지를 표시할 수 없습니다"
    페이지를 반환한다. 이때 조용히 빈 결과를 내면 사용자는 "펀드에 데이터가
    없나 보다"로 오해하므로, 준비 요소(ready_selector)가 없으면 재시도 후
    그래도 안 되면 명확한 한국어 메시지로 실패시킨다.
    """
    for attempt in range(retries + 1):
        page.goto(url, wait_until="domcontentloaded")
        try:
            _wait_websquare(page)
        except PWTimeout:
            pass  # 오류 페이지는 networkidle 이 늦을 수 있음 - 아래 존재 체크로 판단
        if page.query_selector(ready_selector):
            return
        log.warning(
            "세이브로 오류 페이지 감지 (title=%r), 재시도 %d/%d",
            page.title(), attempt + 1, retries,
        )
        time.sleep(3)
    raise RuntimeError(
        "세이브로 사이트가 현재 페이지를 표시하지 못합니다 (사이트 점검 또는 일시 오류).\n"
        "잠시 후 다시 시도해주세요. 계속되면 seibro.or.kr 을 브라우저로 열어 상태를 확인해보세요."
    )


def _js_click(page: Page, selector: str) -> None:
    """
    물리 클릭 대신 DOM click() 직접 호출.

    세이브로 페이지는 GNB 드롭다운(ul.col_inner_ul)이나 검색 드롭다운 레이어
    (dd#fn_group2.search_dd) 같은 요소가 클릭 대상 위에 겹쳐 있어서
    page.click() 이 "intercepts pointer events" 로 실패하는 경우가 잦다
    (조회 버튼에서 먼저 실측했고, 돋보기 아이콘 #fn_group4 도 같은 증상 실측).
    겹침 여부는 그때그때 달라서 간헐적으로만 실패하는 게 함정 — 물리 클릭
    대신 JS click() 을 쓰면 레이어 겹침과 무관하게 항상 동작한다.
    """
    page.wait_for_selector(selector, state="attached", timeout=8000)
    page.eval_on_selector(selector, "el => el.click()")


def _open_fund_search_popup(page: Page):
    """
    펀드 검색 팝업 열기.

    실측 결과, 돋보기 아이콘(#fn_group4)을 클릭해도 새 브라우저 창(popup)은 뜨지
    않는다. 대신 같은 페이지 안에서 레이어 팝업(div#Lpopup_wrap)이 표시되고,
    그 안의 iframe#iframeFnMn 에 실제 검색 UI가 로드된다.
    (iframe src: /IPORTAL/user/etc/BIP_CMUC01044P.xml, ret_code=KOR_SECN_CD,
     ret_code_nm=KOR_SECN_NM → 선택 시 이 값들이 메인 페이지 입력창에 채워짐)
    따라서 page.expect_popup() 대신 iframe 을 기다렸다가 그 frame 을 반환한다.
    """
    # 참고: #Lpopup_wrap 은 wait_for_selector(state="visible") 로 기다리면
    # Playwright 가 "hidden"으로 오판하는 경우가 있어(실측: aria-hidden="false"인
    # 상태에서도 타임아웃 발생) state 체크 대신 짧은 sleep 후 iframe 을 바로 기다린다.
    # 물리 클릭은 검색 드롭다운 레이어(dd#fn_group2)가 간헐적으로 가로채므로 JS 클릭 사용.
    _js_click(page, "#fn_group4")
    time.sleep(1.5)
    iframe_el = page.wait_for_selector("#iframeFnMn", timeout=8000)
    frame = iframe_el.content_frame()
    frame.wait_for_load_state("networkidle", timeout=10000)
    return frame


def _search_fund_in_popup(frame, keyword: str, target_isin: str | None = None) -> None:
    """
    검색 팝업 iframe 내부에서 펀드명 검색 후 결과 선택.

    확정된 구조:
    - 검색창: input#search_string, 검색 버튼: a#group149
    - 검색 결과 리스트: ul#isinList 안에 li > a[id$='_ISIN_ROW'] 로 각 펀드
      한 건씩 나열됨. href="javascript:SelectedValueReturn(ISIN, 펀드명)" 이라서
      ISIN 코드까지 이 시점에 이미 알 수 있음.
    - 클릭하면 메인 페이지의 input#KOR_SECN_NM / input#KOR_SECN_CD 에 값이
      채워지고 팝업이 자동으로 닫힘 ("뱅크론" 검색 → 23건 → 첫 결과 클릭 →
      KOR_SECN_CD=KRZ501889310 로 채워짐을 실측 확인).

    target_isin 이 주어지면 첫 번째 결과 대신 href 에 해당 ISIN 이 들어 있는
    결과를 클릭한다 (GUI에서 검색 결과 목록 중 사용자가 고른 펀드를 정확히
    선택하기 위함). 팝업 검색창에 ISIN 을 직접 넣는 방식은 동작이 검증된 적이
    없어서, 검색은 항상 펀드명 키워드로 하고 선택만 ISIN 으로 특정한다.
    """
    frame.fill("#search_string", keyword)
    frame.click("#group149", timeout=5000)
    time.sleep(1.0)

    # 검색 결과가 수천 건이면(예: "미래에셋" 2,240건) 물리 클릭은 스크롤/겹침
    # 문제가 생길 수 있어 DOM click() 을 직접 호출한다 (href 가
    # javascript:SelectedValueReturn(...) 이라 click() 만으로 선택이 실행됨)
    if target_isin:
        sel = f"ul#isinList a[href*='{target_isin}']"
    else:
        sel = "ul#isinList li:first-child a"
    # 결과가 수천 건이면 목록 로딩이 몇 초 걸릴 수 있어 넉넉히 기다린다
    frame.wait_for_selector(sel, state="attached", timeout=15000)
    frame.eval_on_selector(sel, "el => el.click()")
    time.sleep(1)


def _is_etf(isin: str, name: str) -> bool:
    """
    검색 결과가 ETF 인지 판별.

    세이브로 펀드 검색 팝업에는 ETF(상장지수펀드)도 같이 나온다 (실측:
    "미래에셋" 2,240건 중 285건이 TIGER ETF). ETF 는 이 분배내역 메뉴에
    데이터가 없어 조회해도 빈 결과만 나오므로 목록에서 걸러낸다. 판별 기준:
    - 이름에 "상장지수" (한국 ETF 의 법정 명칭 "…증권상장지수투자신탁")
    - 이름에 "ETF"
    - ISIN 이 KR7 로 시작 (상장 증권. 일반 공모펀드는 KRZ5 로 시작 - 실측)
    """
    compact = name.upper().replace(" ", "")
    return "상장지수" in compact or "ETF" in compact or isin.startswith("KR7")


def search_funds(keyword: str, headless: bool = True, exclude_etf: bool = True) -> list[dict]:
    """
    검색 팝업에서 keyword 로 펀드를 검색하고, 아무것도 선택하지 않은 채
    전체 결과 목록을 [{"isin": ..., "name": ...}, ...] 로 반환한다.

    GUI에서 "첫 번째 결과 자동 선택" 대신 사용자가 목록을 보고 직접 고르게
    하기 위한 함수. 결과 각 항목의 href 가
    javascript:SelectedValueReturn('ISIN','펀드명') 형태라서 클릭 없이도
    ISIN 을 뽑을 수 있고, 표시용 펀드명은 innerText 를 쓴다.

    exclude_etf=True (기본) 면 ETF 는 목록에서 제외한다 (_is_etf 참고).
    """
    log.info("펀드 검색 목록 조회: %s", keyword)
    with sync_playwright() as p:
        browser = _launch_chromium(p, headless)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()
        try:
            _goto_with_retry(page, SEIBRO_URL, "#fn_group4")

            frame = _open_fund_search_popup(page)
            frame.fill("#search_string", keyword)
            frame.click("#group149", timeout=5000)
            # 고정 sleep 만으로는 결과가 많을 때(예: "미래에셋" 2,240건) 로딩이
            # 끝나기 전에 빈 목록을 읽는 경우가 있음(실측: 같은 검색어로 2,240건
            # /0건 왔다갔다) - 첫 결과 행이 나타날 때까지 명시적으로 기다린다
            try:
                frame.wait_for_selector(
                    "ul#isinList li > a[id$='_ISIN_ROW']", state="attached", timeout=10000
                )
            except PWTimeout:
                log.info("검색 결과 행이 10초 내 나타나지 않음 - 결과 0건으로 처리")
            time.sleep(0.5)

            results = frame.eval_on_selector_all(
                "ul#isinList li > a[id$='_ISIN_ROW']",
                "els => els.map(el => {"
                "  const href = el.getAttribute('href') || '';"
                "  const m = href.match(/SelectedValueReturn\\(\\s*['\\\"]([^'\\\"]*)['\\\"]/);"
                "  return {isin: m ? m[1] : '', name: (el.innerText || '').trim()};"
                "})",
            )
        finally:
            browser.close()

    results = [r for r in results if r["name"]]
    if exclude_etf:
        before = len(results)
        results = [r for r in results if not _is_etf(r["isin"], r["name"])]
        if before != len(results):
            log.info("ETF %d건 제외", before - len(results))
    log.info("검색 결과 %d건", len(results))
    return results


def _get_selected_fund_name(page: Page) -> str:
    """
    검색 팝업에서 선택된 실제 펀드명을 메인 페이지에서 읽어온다.

    검색어("월지급" 등)는 부분 매칭이라 결과가 여러 건 나올 수 있고, 코드는
    항상 첫 번째 결과를 선택한다. 검색어와 실제로 선택된 펀드가 다를 수 있으니
    input#KOR_SECN_NM 에 채워진 값을 읽어서 어떤 펀드가 조회됐는지 명확히 남긴다.
    """
    try:
        return page.input_value("#KOR_SECN_NM")
    except PWTimeout:
        return ""


def _set_period(page: Page, period: str = "1년") -> None:
    """
    조회기간 프리셋 선택.

    확정: select#sd1_selectbox1_input_0 (옵션: 1주/1개월/3개월/6개월/연초이후/
    1년/2년/3년). input#startDt_input 에 직접 fill() 하면 위젯이 자체 검증 후
    기본값(1년)으로 되돌리는 현상이 있어, 텍스트 직접 입력 대신 이 프리셋
    드롭다운을 쓰는 쪽이 안정적이다.
    """
    page.select_option("#sd1_selectbox1_input_0", label=period)


def _click_inquire(page: Page) -> None:
    """
    조회 버튼 클릭.

    확정: a.btn_seach (href="javascript:searchPList();"), 내부 img#image2
    alt="조회". 텍스트 라벨이 아니라 이미지라서 has-text 셀렉터로는 못 잡는다.

    실측: page.click() 으로는 상단 GNB 드롭다운(ul.col_inner_ul)이 항상 DOM 상
    겹쳐 있어서 "intercepts pointer events" 로 클릭이 계속 실패했다. href 가
    이미 JS 함수 호출(searchPList())이라는 걸 알고 있으니 클릭 대신 그 함수를
    직접 evaluate 로 호출하는 쪽이 훨씬 안정적이다.
    """
    page.evaluate("searchPList()")
    _wait_websquare(page, extra_sleep=2.0)


_GRID_ID = "gridFundExerList"

# col_id 속성 → 한글 컬럼명. "뱅크론" 조회 결과 실측으로 확정.
_COLUMN_LABELS = {
    "RGT_STD_DT": "기준일자",
    "RGT_RSN_DTAIL_SORT_NM": "배당구분",
    "FIX_TPNM": "배당확정여부",
    "ALOC_WHNM": "현금배당방법",
    "CLERDIV_VAL": "청산상환분배금기준",
    "PAY_TERM": "지급기간",
    "SETACC_STDPRC": "결산기준가",
    "SETACC_TAXSTD": "결산과표기준가",
    "CASH_ALOC_AMT": "주당배당액",
    "CASH_ALOC_RATIO": "주당배당율",
    "TOT_DIV_PAY_AMT": "총분배금",
    "TAX_TPNM": "세금구분",
    "CLER_NOS": "청산차수",
}


def _parse_result_table(page: Page) -> pd.DataFrame:
    """
    결과 테이블 파싱.

    실측 확정: 결과 그리드 id는 "gridFundExerList" (초기 추정했던
    gridDRConvList는 틀렸음). 레코드 1건은 물리적으로 <tr> 2개에 걸쳐
    표시되지만(rowspan/colspan 사용), 각 <td>는 col_id 속성으로 의미가
    명확히 구분된다. "기준일자"(col_id=RGT_STD_DT, rowspan=2)가 다시
    나타나는 시점을 새 레코드의 시작으로 판단해서 병합한다.
    """
    no_result = page.query_selector(f"div[id$='{_GRID_ID}_noresult']")
    if no_result and no_result.is_visible():
        return pd.DataFrame(columns=list(_COLUMN_LABELS.values()))

    cells = page.eval_on_selector_all(
        f"#{_GRID_ID}_body_tbody td[col_id]",
        "els => els.map(el => ({col_id: el.getAttribute('col_id'), "
        "text: el.innerText.trim()}))",
    )

    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for cell in cells:
        col_id = cell["col_id"]
        if col_id == "RGT_STD_DT" and current:
            records.append(current)
            current = {}
        current[col_id] = cell["text"]
    if current:
        records.append(current)

    # w2grid 는 부드러운 스크롤을 위해 빈 버퍼 행도 같이 렌더링한다(실측: "뱅크론"
    # 첫 결과는 실제 데이터 1건인데 tbody에는 15개 tr이 잡힘). 기준일자가 빈
    # 레코드는 버퍼 행이므로 제외.
    records = [rec for rec in records if rec.get("RGT_STD_DT", "").strip()]

    rows = [{_COLUMN_LABELS.get(k, k): v for k, v in rec.items()} for rec in records]
    return pd.DataFrame(rows, columns=list(_COLUMN_LABELS.values()))


# 배당소득세 14% + 지방소득세 1.4% (일반과세 개인투자자 기준). 실제로는 계좌
# 종류(연금저축/ISA 등)나 금융소득종합과세 해당 여부에 따라 달라질 수 있어서
# 세후 수치는 참고용 근사치다.
KOREAN_DIVIDEND_TAX_RATE = 0.154


def summarize_distribution_yield(df: pd.DataFrame) -> dict:
    """
    조회 기간 내 분배 요약: 평균 기준가, 1,000좌당 분배금 합계, 세전/세후 분배율.

    실측 정정: 세이브로가 주는 "주당배당율"(CASH_ALOC_RATIO) 컬럼은 실제
    월지급식 펀드로 테스트해보니 스케일이 안 맞아서 항상 0으로 나옴 - 원인은
    "결산기준가"(SETACC_STDPRC)는 한국 펀드 관례상 1,000좌당 가격인데
    "주당배당액"(CASH_ALOC_AMT)은 컬럼명 그대로 1좌당 금액이라 1,000배 스케일
    차이가 있어서다. 그래서 세이브로 제공값 대신 직접 계산한다.

    비율만 보여주면 감이 잘 안 와서, 비교 기준이 되는 두 숫자(평균 기준가,
    1,000좌당 분배금 합계)를 같이 보여주고 그걸로 비율을 계산하는 방식으로 변경
    (기존에는 회차별 비율을 각각 구해서 합산했는데, 이제는 총분배금/평균기준가
    방식). "주당배당액"은 원천징수 전 세전 금액으로 보고, 배당소득세
    15.4%(세전액*0.154)를 뺀 세후 금액도 같이 계산한다.
    """
    empty = {
        "count": 0,
        "avg_price": 0.0,
        "total_dist_per_1000_pretax": 0.0,
        "total_dist_per_1000_posttax": 0.0,
        "ratio_pct_pretax": 0.0,
        "ratio_pct_posttax": 0.0,
    }
    if df.empty:
        return empty

    amt = pd.to_numeric(df["주당배당액"].astype(str).str.replace(",", ""), errors="coerce").fillna(0.0)
    price = pd.to_numeric(df["결산기준가"].astype(str).str.replace(",", ""), errors="coerce")

    avg_price = float(price.mean())
    total_pretax = float((amt * 1000).sum())
    total_posttax = total_pretax * (1 - KOREAN_DIVIDEND_TAX_RATE)

    ratio_pretax = round(total_pretax / avg_price * 100, 4) if avg_price else 0.0
    ratio_posttax = round(total_posttax / avg_price * 100, 4) if avg_price else 0.0

    return {
        "count": len(df),
        "avg_price": round(avg_price, 2),
        "total_dist_per_1000_pretax": round(total_pretax, 2),
        "total_dist_per_1000_posttax": round(total_posttax, 2),
        "ratio_pct_pretax": ratio_pretax,
        "ratio_pct_posttax": ratio_posttax,
    }


def crawl_fund_distribution(
    fund: FundQuery,
    period: str = "1년",
    headless: bool = False,
    screenshot_dir: Path | None = None,
) -> pd.DataFrame:
    """
    특정 펀드의 분배금 지급 내역을 세이브로에서 크롤링.

    Args:
        fund: 조회 대상 펀드 (FundQuery)
        period: 조회기간 프리셋. "1주"/"1개월"/"3개월"/"6개월"/"연초이후"/
                "1년"/"2년"/"3년" 중 하나. 기본 1년.
        headless:   True면 백그라운드. 개발 중엔 False 권장
        screenshot_dir: 디버깅용 스크린샷 저장 폴더. None이면 저장 안 함.

    Returns:
        분배금 이력 DataFrame
    """
    log.info("펀드 조회 시작: %s (조회기간: %s)", fund.name, period)

    with sync_playwright() as p:
        browser = _launch_chromium(p, headless)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()

        try:
            # 1) 페이지 접속 (오류 페이지면 재시도)
            _goto_with_retry(page, SEIBRO_URL, "#fn_group4")
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "01_landing.png")

            # 2) 펀드 검색 팝업 열고 선택 (isin 이 있으면 그 펀드를 정확히 선택)
            popup = _open_fund_search_popup(page)
            _search_fund_in_popup(popup, fund.name, target_isin=fund.isin)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "02_after_select.png")

            matched_name = _get_selected_fund_name(page)
            log.info("검색어 '%s' → 실제 조회된 펀드: %s", fund.name, matched_name)

            # 3) 조회 기간 설정
            _set_period(page, period)

            # 4) 조회
            _click_inquire(page)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "03_result.png")

            # 5) 결과 파싱
            df = _parse_result_table(page)
            if not df.empty:
                df.insert(0, "조회된펀드명", matched_name)
            log.info("파싱된 행 개수: %d", len(df))

        except PWTimeout as e:
            log.error("타임아웃: %s", e)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "error.png")
            # 빈 결과를 돌려주면 "분배 이력이 없는 펀드"와 구분이 안 돼 오해를
            # 부르므로(실측 피드백), 명확한 오류로 올린다
            raise RuntimeError(
                "세이브로 분배내역 조회 중 응답 시간 초과. 사이트가 느리거나 "
                "일시 오류일 수 있으니 잠시 후 다시 시도해주세요."
            ) from e
        finally:
            browser.close()

    return df


_NAV_GRID_ID = "grid5"

# col_id 속성 → 한글 컬럼명. 펀드종합정보 > 기준가/분배금 탭 실측으로 확정.
_NAV_COLUMN_LABELS = {
    "ANYTM_REPTG_DT": "기준일",
    "NAV_AMT": "기준가",
    "STDPRC_INCDEC_AMT": "전일대비",
    "DD1_PRATE": "등락율",
    "TAXSTD": "과표기준가",
    "FUND_SETUP_ORCP_AMT": "설정액",
    "FUND_NETASST_TOTAMT": "순자산",
    "TOT_DIV_PAY_AMT": "분배금",
    "RGT_RACD": "비고",
}


def _open_nav_search_popup(page: Page):
    """
    펀드종합정보 페이지의 검색 팝업 열기.

    분배내역 페이지와 동일하게 iframe#iframeFnMn 레이어 팝업 구조지만, 검색
    아이콘의 alt 텍스트가 "검색"으로 다르다(분배내역 페이지는 "검색하기").
    """
    # 분배내역 페이지 돋보기와 같은 간헐적 클릭 가로채기 문제가 있어 JS 클릭 사용
    _js_click(page, "img[alt*='검색'], a:has(img[alt*='검색'])")
    time.sleep(1.5)
    iframe_el = page.wait_for_selector("#iframeFnMn", timeout=8000)
    frame = iframe_el.content_frame()
    frame.wait_for_load_state("networkidle", timeout=10000)
    return frame


def _set_nav_period(page: Page, period: str = "1년") -> None:
    """조회기간 프리셋 선택. 확정: select#selectbox1_input_0 (분배내역 페이지와 다른 id)."""
    page.select_option("#selectbox1_input_0", label=period)


def _click_nav_search(page: Page) -> None:
    """조회 버튼 클릭. 확정: a#group269 (href="#", 클릭 이벤트가 JS로 바인딩됨)."""
    page.click("#group269", timeout=5000)
    _wait_websquare(page, extra_sleep=1.5)


def _parse_nav_grid(page: Page) -> pd.DataFrame:
    """
    기준가/분배금 그리드에서 현재 화면에 보이는 페이지 1개만 파싱.

    실측 확정: 그리드 id는 "grid5". 분배내역 그리드와 달리 레코드 1건이 <tr> 1개로
    끝나는 단순 구조라 rowspan 병합이 필요 없음. 페이지당 10행씩 페이지네이션됨
    (페이지 링크 id: gridPaging_page_N) - 여러 페이지 순회는 _iterate_all_nav_pages 참고.
    """
    rows = page.eval_on_selector_all(
        f"#{_NAV_GRID_ID}_body_tbody tr.grid_body_row",
        "trs => trs.map(tr => { const obj = {}; "
        "tr.querySelectorAll('td[col_id]').forEach(td => { "
        "obj[td.getAttribute('col_id')] = td.innerText.trim(); }); return obj; })",
    )
    rows = [r for r in rows if r.get("ANYTM_REPTG_DT", "").strip()]
    mapped = [{_NAV_COLUMN_LABELS.get(k, k): v for k, v in r.items()} for r in rows]
    return pd.DataFrame(mapped, columns=list(_NAV_COLUMN_LABELS.values()))


def _click_next_nav_page(page: Page) -> bool:
    """
    기준가/분배금 그리드의 다음 페이지로 이동.

    처음엔 #gridPaging_next_btn 이 "다음 페이지 그룹(10개씩)" 이동 버튼인 줄
    알았는데, 실제 alt 텍스트는 "다음 페이지"(1페이지씩 전진)였다 - "첫 페이지"
    (prevPage_btn) / "이전 페이지"(prev_btn) / "다음 페이지"(next_btn) /
    "마지막 페이지"(nextPage_btn) 조합. 페이지 번호 링크 목록(#gridPaging_page_1
    ~ _10)은 절대 페이지가 아니라 화면에 보이는 슬라이딩 윈도우라서, 그때그때
    DOM에서 현재 선택된 링크(class="...label_selected")를 찾아 그 다음 링크를
    클릭하고, 이미 마지막 링크면 "다음 페이지" 버튼으로 한 칸 전진한다.
    """
    page_links = page.query_selector_all("a[id^='gridPaging_page_']")
    selected_idx = None
    for i, el in enumerate(page_links):
        cls = el.get_attribute("class") or ""
        if "label_selected" in cls:
            selected_idx = i
            break

    if selected_idx is not None and selected_idx + 1 < len(page_links):
        page_links[selected_idx + 1].click()
        return True

    next_btn = page.query_selector("#gridPaging_next_btn a")
    if next_btn is None:
        return False
    next_btn.click()
    return True


def _iterate_all_nav_pages(page: Page, max_pages: int = 30) -> pd.DataFrame:
    """
    기준가/분배금 그리드를 끝까지(또는 max_pages 까지) 페이지네이션 순회해서
    조회기간 전체 데이터를 모은다. 페이지당 10행이므로 max_pages=30 이면 최대
    300영업일(약 1년 남짓) 커버 가능. 새로 가져온 페이지에 이미 본 기준일자만
    있으면(더 넘어갈 페이지가 없다는 뜻) 중단한다.
    """
    all_dfs: list[pd.DataFrame] = []
    seen_dates: set[str] = set()

    for _ in range(max_pages):
        df_page = _parse_nav_grid(page)
        if df_page.empty:
            break
        new_dates = set(df_page["기준일"]) - seen_dates
        if not new_dates:
            break
        seen_dates.update(df_page["기준일"])
        all_dfs.append(df_page)

        if len(df_page) < 10:
            break  # 마지막 페이지로 추정 (그리드가 10행 미만이면 더 없음)
        if not _click_next_nav_page(page):
            break
        _wait_websquare(page, extra_sleep=1.0)

    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()


def crawl_fund_nav_history(
    fund: FundQuery,
    period: str = "1년",
    headless: bool = False,
    screenshot_dir: Path | None = None,
) -> pd.DataFrame:
    """
    펀드종합정보 > 기준가/분배금 탭에서 일별 기준가·순자산(AUM, 억원)·분배금
    이력을 가져온다. AUM 변화 추적의 데이터 소스. 그리드가 페이지당 10행씩
    페이지네이션되는데 _iterate_all_nav_pages() 로 조회기간 전체를 순회해서 모은다
    (1년 기준 최대 약 25페이지, 페이지 전환마다 대기 시간이 있어서 몇십 초 걸림).
    """
    log.info("펀드 기준가/AUM 조회 시작: %s (조회기간: %s)", fund.name, period)

    with sync_playwright() as p:
        browser = _launch_chromium(p, headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ko-KR")
        page = context.new_page()

        try:
            _goto_with_retry(page, FUND_NAV_URL, "img[alt*='검색']")

            frame = _open_nav_search_popup(page)
            _search_fund_in_popup(frame, fund.name, target_isin=fund.isin)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "nav_01_selected.png")

            matched_name = _get_selected_fund_name(page)
            log.info("검색어 '%s' → 실제 조회된 펀드: %s", fund.name, matched_name)

            page.click("text=기준가/분배금", timeout=5000)
            _wait_websquare(page, extra_sleep=1.0)

            _set_nav_period(page, period)
            _click_nav_search(page)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "nav_02_result.png")

            df = _iterate_all_nav_pages(page)
            if not df.empty:
                df.insert(0, "조회된펀드명", matched_name)
            log.info("기준가/AUM 파싱된 행 개수: %d (페이지네이션 전체 순회)", len(df))
        except PWTimeout as e:
            log.error("타임아웃: %s", e)
            if screenshot_dir:
                page.screenshot(path=screenshot_dir / "nav_error.png")
            raise RuntimeError(
                "세이브로 기준가/순자산 조회 중 응답 시간 초과. 사이트가 느리거나 "
                "일시 오류일 수 있으니 잠시 후 다시 시도해주세요."
            ) from e
        finally:
            browser.close()

    return df


def summarize_aum_change_on_distribution(nav_df: pd.DataFrame) -> dict:
    """
    분배 지급일의 펀드 총자산(AUM) 변화를 계산하고, 조회 기간 전체 합계도 낸다.

    실측 정정: "분배금"(TOT_DIV_PAY_AMT) 컬럼은 이 그리드에서는 대부분 빈 값으로
    나오고, 대신 "비고"(RGT_RACD) 컬럼에 "배당/분배" 라벨이 붙는 방식으로 분배일을
    표시함(결산일과 실제 기준가 반영일이 달라서 그런 것으로 추정 - 분배내역 페이지의
    "기준일자"와 날짜가 다를 수 있음). 그래서 "비고"에 값이 있는 행을 분배 이벤트로
    잡아서 전일 대비 순자산(억원) 증감액/증감율을 계산한다.

    반환값:
    - events: 분배 이벤트별 상세 내역 (기준일, 순자산, 전일 대비 증감 등)
    - total_events_aum_change_억원: 조회 기간 내 분배 이벤트들에서의 순자산 증감 합계
    - period_start_aum_억원 / period_end_aum_억원: 조회 기간 처음/마지막 날 순자산
    - period_aum_change_억원 / period_aum_change_pct: 조회 기간 전체 순자산 증감액/율
      (분배뿐 아니라 운용손익 등 다른 요인도 섞인 총 변화라서 위 분배 이벤트 합계와는 다름)
    """
    empty = {
        "events": pd.DataFrame(),
        "total_events_aum_change_억원": 0.0,
        "period_start_aum_억원": None,
        "period_end_aum_억원": None,
        "period_aum_change_억원": None,
        "period_aum_change_pct": None,
    }
    if nav_df.empty:
        return empty

    df = nav_df.copy()
    df["기준일"] = pd.to_datetime(df["기준일"], format="%Y/%m/%d")
    df = df.sort_values("기준일").reset_index(drop=True)
    df["순자산_억원"] = pd.to_numeric(df["순자산"].str.replace(",", ""), errors="coerce")

    # 실측(미래에셋 배당과인컴30 성과보수 클래스): 기준가는 매일 정상 갱신되는데
    # 설정액·순자산이 전 기간 0 으로만 나오는 펀드(클래스)가 있다 - 세이브로가
    # 해당 클래스의 순자산을 제공하지 않는 경우. 0 을 실제 값처럼 쓰면
    # "순자산 0.00억원 → 0.00억원" 같은 거짓 결과가 나오므로 "데이터 없음"으로 처리
    if not df["순자산_억원"].fillna(0).any():
        return empty
    df["분배금_원"] = pd.to_numeric(df["분배금"].astype(str).str.replace(",", ""), errors="coerce")
    df["전일순자산_억원"] = df["순자산_억원"].shift(1)
    df["순자산증감_억원"] = df["순자산_억원"] - df["전일순자산_억원"]
    df["순자산증감율(%)"] = (df["순자산증감_억원"] / df["전일순자산_억원"] * 100).round(4)

    events = df[df["비고"].str.strip() != ""].copy()
    events["분배금_억원"] = events["분배금_원"] / 1e8
    events["분배금_전일순자산비율(%)"] = (
        events["분배금_억원"] / events["전일순자산_억원"] * 100
    ).round(4)
    events = events[[
        "기준일", "비고", "순자산_억원", "전일순자산_억원", "순자산증감_억원",
        "순자산증감율(%)", "분배금_억원", "분배금_전일순자산비율(%)",
    ]].reset_index(drop=True)

    start_aum = float(df["순자산_억원"].iloc[0])
    end_aum = float(df["순자산_억원"].iloc[-1])
    period_change = end_aum - start_aum

    return {
        "events": events,
        "total_events_aum_change_억원": round(float(events["순자산증감_억원"].sum()), 2)
        if not events.empty else 0.0,
        "period_start_aum_억원": round(start_aum, 2),
        "period_end_aum_억원": round(end_aum, 2),
        "period_aum_change_억원": round(period_change, 2),
        "period_aum_change_pct": round(period_change / start_aum * 100, 4) if start_aum else None,
    }


def summarize_price_change(nav_df: pd.DataFrame) -> dict:
    """
    조회기간 동안 기준가(NAV, 1,000좌 기준) 변화. 순자산(AUM)과는 별개로,
    "펀드 가격 자체"가 얼마에서 얼마로 바뀌었는지를 본다.
    """
    empty = {"start_price": None, "end_price": None, "change": None, "change_pct": None}
    if nav_df.empty:
        return empty

    df = nav_df.copy()
    df["기준일"] = pd.to_datetime(df["기준일"], format="%Y/%m/%d")
    df = df.sort_values("기준일")
    price = pd.to_numeric(df["기준가"].astype(str).str.replace(",", ""), errors="coerce")

    start_price = float(price.iloc[0])
    end_price = float(price.iloc[-1])
    change = end_price - start_price

    return {
        "start_price": round(start_price, 2),
        "end_price": round(end_price, 2),
        "change": round(change, 2),
        "change_pct": round(change / start_price * 100, 4) if start_price else None,
    }


def summarize_aum_vs_distribution(dist_df: pd.DataFrame, aum_summary: dict) -> dict:
    """
    순자산 증감을 "분배로 빠져나간 것"과 "펀드 자체 운용손익"으로 나눠서 본다.

    주의: "설정액"(FUND_SETUP_ORCP_AMT, 펀드 최초 모집 시 금액 - 고정값)과
    "순자산"(FUND_NETASST_TOTAMT, 현재 시가 기준 총자산 - 매일 변동)은 다른
    개념이다. AUM 추적은 항상 순자산 기준으로 하고, 설정액은 원자료 조회에서만
    참고용으로 보여준다.

    조회기간 동안 실제로 분배된 총 현금(총분배금 합계, dist_df의 "총분배금"
    컬럼)만큼은 순자산이 줄어드는 게 당연하다(분배락). 그 효과를 되돌려서
    ("순자산증감액" + "총분배유출액") 계산하면, 분배와 무관하게 펀드 자체
    투자자산 가치가 늘었는지 줄었는지(순수 운용손익)를 따로 볼 수 있다.
    """
    total_distributed_원 = (
        pd.to_numeric(dist_df["총분배금"].astype(str).str.replace(",", ""), errors="coerce").sum()
        if not dist_df.empty else 0.0
    )
    total_distributed_억원 = round(float(total_distributed_원) / 1e8, 2)

    start = aum_summary.get("period_start_aum_억원")
    aum_change = aum_summary.get("period_aum_change_억원")
    if start is None or aum_change is None:
        return {
            "total_distributed_억원": total_distributed_억원,
            "aum_change_excl_distribution_억원": None,
            "aum_change_excl_distribution_pct": None,
        }

    excl_distribution = round(aum_change + total_distributed_억원, 2)
    excl_distribution_pct = round(excl_distribution / start * 100, 4) if start else None

    return {
        "total_distributed_억원": total_distributed_억원,
        "aum_change_excl_distribution_억원": excl_distribution,
        "aum_change_excl_distribution_pct": excl_distribution_pct,
    }


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

    test_fund = FundQuery(name="월지급")  # 검색어만 넣으면 팝업에서 첫 결과 선택
    df = crawl_fund_distribution(
        fund=test_fund,
        period="1년",
        headless=False,
        screenshot_dir=Path("debug_screenshots"),
    )
    print(df)
    df.to_csv("test_result.csv", index=False, encoding="utf-8-sig")

    summary = summarize_distribution_yield(df)
    log.info(
        "1년간 분배 %d회, 평균 기준가 %.2f, 1,000좌당 분배금 합계 세전 %.2f원"
        " / 세후 %.2f원, 분배율 세전 %.4f%% / 세후 %.4f%%",
        summary["count"], summary["avg_price"],
        summary["total_dist_per_1000_pretax"], summary["total_dist_per_1000_posttax"],
        summary["ratio_pct_pretax"], summary["ratio_pct_posttax"],
    )

    nav_df = crawl_fund_nav_history(
        fund=test_fund,
        period="1년",
        headless=False,
        screenshot_dir=Path("debug_screenshots"),
    )
    print(nav_df)
    nav_df.to_csv("test_nav_result.csv", index=False, encoding="utf-8-sig")

    aum_change = summarize_aum_change_on_distribution(nav_df)
    print(aum_change["events"])
    log.info(
        "분배 이벤트 순자산증감 합계 %.2f억원 | 조회기간 전체 순자산 %.2f→%.2f억원 (%.4f%%)",
        aum_change["total_events_aum_change_억원"],
        aum_change["period_start_aum_억원"] or 0.0, aum_change["period_end_aum_억원"] or 0.0,
        aum_change["period_aum_change_pct"] or 0.0,
    )

    vs_dist = summarize_aum_vs_distribution(df, aum_change)
    log.info(
        "조회기간 총분배유출액 %.2f억원 | 분배 제외 순수 운용손익 %.2f억원 (%.4f%%)",
        vs_dist["total_distributed_억원"],
        vs_dist["aum_change_excl_distribution_억원"] or 0.0,
        vs_dist["aum_change_excl_distribution_pct"] or 0.0,
    )

    price_change = summarize_price_change(nav_df)
    log.info(
        "1년간 기준가 변화: %.2f원 → %.2f원 (%+.2f원, %+.4f%%)",
        price_change["start_price"] or 0.0, price_change["end_price"] or 0.0,
        price_change["change"] or 0.0, price_change["change_pct"] or 0.0,
    )
