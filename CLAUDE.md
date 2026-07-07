# SEIBro 펀드 분배금 크롤러

## 사용자 컨텍스트
- 두원전자 개발팀 엔지니어 (모터 컨트롤러, 수가열 히터 담당)
- 주력 언어: 한국어 반말, 간결/직접적 소통 선호
- 답변 시 이름 부르지 말 것
- 되묻지 말고 바로 진행. 애매하면 가정을 명시하고 진행

## 프로젝트 목적
한국 판매 월지급식 채권 펀드 (뱅크론, 하이일드 위주) 리서치용
분배금 이력 데이터 수집. 최종적으로 다음과 연동:

- 이미 작성된 월지급식 펀드 31개 비교 엑셀 파일
- 지인 추천 부동산 담보 대출 펀드 (10%+ 분배율) 정체 파악
- 향후 백테스트/수익률 계산

## 목표 산출물
1. 세이브로 (SEIBro) `펀드별분배금지급내역` 페이지에서
   특정 펀드의 분배금 이력을 자동으로 뽑아 CSV / DataFrame 으로 저장
2. 펀드 표준코드 (ISIN, KR로 시작) 또는 펀드명으로 조회 가능
3. 다수 펀드 배치 조회 지원 (엑셀 시트에 있는 31개 펀드 일괄)

## 데이터 소스
### 1순위: 세이브로 (SEIBro)
- URL: https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/fund/BIP_CNTS05008V.xml&menuNo=152
- 메뉴 경로: 펀드 → 권리행사정보 → 펀드별분배금지급내역
- 프레임워크: WebSquare (SAMSUNG SDS)
- 특성:
  - JavaScript 기반 SPA. `requests` 로 GET 해도 빈 페이지
  - 실제 데이터는 POST 요청으로 XML body 보내면 XML 응답
  - Endpoint 패턴: `https://seibro.or.kr/websquare/engine/proxy/xml/{name}.xml`
  - Content-Type: `application/xml; charset=UTF-8`
  - `submissionid` 헤더로 어떤 서비스 호출인지 구분
  - 파라미터에 EUC-KR 인코딩 이슈 있을 수 있음
- 공식 오픈 API (openplatform.seibro.or.kr) 는 법인 대상, 펀드 분배내역 항목 없음

### 대체 소스
- 금투협 종합통계 (dis.kofia.or.kr) — XHR 재현 방식으로 크롤링 가능
- 각 자산운용사 공시 페이지 — 소스 갈려서 유지보수 지옥
- KIS Developers — 국내 펀드 분배금 이력은 미제공

## 기술 스택
- Python 3.11+
- Playwright (Chromium) — 1차 접근. 셀렉터 조정 필요
- requests + lxml — 2차 접근. DevTools Network 캡처로 payload 확보 후 재현
- pandas — 데이터 정리 및 CSV 출력
- 개발 환경: Windows

## 아키텍처 결정
- `scraper/playwright_scraper.py`: UI 자동화 기반. 초기 개발 및 셀렉터 확보용
- `scraper/xml_scraper.py`: 순수 XML POST 방식. 프로덕션용 (빠름, 안정적)
- `scraper/common.py`: 공통 유틸 (날짜, 로깅, CSV 저장)
- `main.py`: 엔트리포인트. 엑셀 파일에서 펀드 리스트 읽어서 배치 처리

## 진행 상황
- [x] 접근 전략 결정 (Playwright 우선, XML 이차)
- [x] 초기 스켈레톤 코드 작성 (seibro_fund_distribution.py)
- [x] 실제 페이지 열어서 셀렉터 확정
- [x] 팝업 검색창 처리 로직 완성 (검색 → 결과 선택 → 메인 페이지 반영까지 확인)
- [x] 결과 테이블 파싱 및 컬럼명 확정 (그리드 id `gridFundExerList`, col_id 기반 파싱)
- [x] "1년간 1,000좌 금액 대비 1,000좌당 분배금 비율" 프로토타입
      (`summarize_distribution_yield()`) — 세이브로가 이미 `주(좌)당배당율`
      컬럼으로 계산해서 제공하길래 그걸 조회기간 내 합산하는 방식으로 구현했었으나
      **실측 정정(2026-07-07)**: 실제 월지급식 펀드로 돌려보니 이 컬럼이 항상 0으로
      나옴 — `결산기준가`(1,000좌 기준 관례)와 `주당배당액`(1좌 기준, 컬럼명 그대로)
      사이에 1,000배 스케일 차이가 있어서 세이브로 제공값을 그대로 못 씀. 이제는
      `(주당배당액 * 1000) / 결산기준가 * 100` 을 직접 계산 (월지급 펀드로 검증:
      10개월 분배 합산 6.36% — 합리적인 수치)
- [x] **콘솔 한글 깨짐 수정** — Windows 콘솔 cp949 vs UTF-8 불일치로 로그가 깨져
      보이던 문제. 스크립트 시작 시 `SetConsoleOutputCP(65001)` + stdout/stderr
      `.reconfigure(encoding="utf-8")` 로 해결
- [x] **펀드 총자산(AUM) 변화 추적 기능 (프로토타입)** — 데이터 소스 찾음:
      펀드종합정보(`BIP_CNTS05011V.xml&menuNo=155`) > "기준가/분배금" 탭에 일별
      기준가·순자산(억원)·비고가 같이 있음. `crawl_fund_nav_history()` +
      `summarize_aum_change_on_distribution()` 로 분배일 전일 대비 순자산
      증감액/증감율 계산 성공 (검증: 2026/06/30 분배일에 순자산 2,693→2,691억원,
      -0.0743%). **한계**: 그리드가 페이지당 10행 페이지네이션이라 지금은 최신
      페이지 1개(최근 영업일 ~10일)만 가져옴 — 1년 전체 이력 보려면 페이지네이션
      순회 구현 필요 (다음 과제, 아래 참고)
- [ ] XML POST endpoint 및 payload 리버스 (DevTools Network 캡처)
- [ ] 다수 펀드 배치 조회 (batch_crawl 함수는 있으나 여러 펀드로 실측 안 함)
- [ ] 엑셀 연동 (기존 월지급식 펀드 비교 파일과 결합)

### 다음 세션 TODO
- [ ] **AUM 페이지네이션 순회** — `crawl_fund_nav_history()`가 지금은 첫 페이지
      (최근 10영업일)만 가져옴. 페이지 링크 id는 `#gridPaging_page_N` 인데,
      화면에 한 번에 보이는 페이지 번호 그룹(예: 1~7)을 넘어가는 "다음 그룹"
      버튼 셀렉터를 아직 못 찾음 — 이거 찾아서 1년치 전체 순회하도록 개선하면
      분배 이벤트 전체에 대한 AUM 변화를 다 볼 수 있음
- [ ] **월평균 기준가 대비 분배율** — 조회기간이 1년 미만인 신생 펀드는
      1년 데이터가 없으니, 보유 기간의 월평균 기준가 대비 분배율로 대체
      계산하는 로직 추가
- [ ] **PyInstaller exe 패키징** — 더블클릭하면 새 창이 뜨는 형태로.
      Playwright+Chromium 번들 때문에 용량/복잡도 있을 수 있음을 먼저
      설명하고 진행. GUI(펀드명 입력창 + 조회 버튼)가 필요한지 착수 전 확인
- [ ] **시각화** — 위 exe 안에서 분배 이력 + AUM 변화 + 분배율을 표/그래프로
      보여주는 것까지 포함. 세부 UI는 착수 전 확인

### 확정된 셀렉터 (2026-07-06 headless=False 실측, 실제 조회 성공까지 검증)
- 펀드 검색 아이콘: `#fn_group4` — 클릭해도 **새 브라우저 팝업이 뜨지 않음**.
  같은 페이지 안의 레이어 팝업 `div#Lpopup_wrap` 이 표시되고, 그 안의
  `iframe#iframeFnMn` 에 실제 검색 UI 로드됨
  (src=`/IPORTAL/user/etc/BIP_CMUC01044P.xml&ret_code=KOR_SECN_CD&ret_code_nm=KOR_SECN_NM`)
  - `#Lpopup_wrap` 을 `wait_for_selector(state="visible")` 로 기다리면 실제로는
    보이는 상태인데도 타임아웃나는 경우가 있어서, 클릭 후 짧은 sleep 다음
    바로 `#iframeFnMn` 을 기다리는 방식으로 우회함
- iframe 내부 검색창: `input#search_string`, 검색 버튼: `a#group149`
- **검색 결과 리스트**: `ul#isinList` 안에 `li > a[id$='_ISIN_ROW']`.
  href 가 `javascript:SelectedValueReturn(ISIN, 펀드명)` 형태라서 이 시점에
  이미 ISIN 코드를 알 수 있음. 클릭하면 메인 페이지 `input#KOR_SECN_NM` /
  `input#KOR_SECN_CD` 에 자동으로 채워지고 팝업이 닫힘
- 조회기간: `input#startDt_input`/`input#endDt_input` 직접 fill 은 위젯이
  자체 검증 후 기본값(1년)으로 되돌리는 현상이 있어서, 대신 프리셋
  드롭다운 `select#sd1_selectbox1_input_0` (옵션: 1주/1개월/3개월/6개월/
  연초이후/1년/2년/3년) 를 `select_option(label=...)` 으로 선택하는 방식
  채택
- 조회 버튼: `a.btn_seach` / `#group64` (href=`javascript:searchPList();`).
  단, `page.click()` 은 상단 GNB 드롭다운(`ul.col_inner_ul`)이 항상 DOM
  상 겹쳐 있어서 "intercepts pointer events" 로 계속 실패함 →
  `page.evaluate("searchPList()")` 로 함수를 직접 호출하는 방식으로 우회
- 결과 그리드: id **`gridFundExerList`** (초기 추정했던 `gridDRConvList`는
  틀렸음). 레코드 1건이 `<tr>` 2개에 걸쳐 rowspan/colspan 으로 표시되는데,
  각 `<td>` 의 `col_id` 속성(`RGT_STD_DT`, `CASH_ALOC_AMT`,
  `CASH_ALOC_RATIO`, `SETACC_STDPRC` 등)으로 의미가 명확히 구분됨. 또한
  가상 스크롤용 빈 버퍼 행도 같이 렌더링되므로 기준일자(RGT_STD_DT)가
  빈 레코드는 걸러내야 함
- **정정**: "주(좌)당배당율" (CASH_ALOC_RATIO) 을 그대로 쓰면 항상 0 이 나옴
  (스케일 불일치, 위 진행 상황 참고). `(주당배당액*1000)/결산기준가*100` 직접 계산 사용

### 확정된 셀렉터 - 펀드종합정보 > 기준가/분배금 탭 (2026-07-07 실측, AUM 데이터 소스)
- URL: `BIP_CNTS05011V.xml&menuNo=155` (분배내역 페이지와 다른 URL)
- 검색 아이콘: `img[alt*='검색']` (분배내역 페이지는 alt="검색하기", 여긴 "검색"
  이라 다름). 팝업 구조(iframe#iframeFnMn, ul#isinList)는 분배내역 페이지와 동일
  해서 `_search_fund_in_popup()` 재사용 가능
- 탭 전환: `page.click("text=기준가/분배금")`
- 조회기간 프리셋: `select#selectbox1_input_0` (분배내역 페이지의
  `sd1_selectbox1_input_0`와 다른 id, 옵션은 동일)
- 조회 버튼: `a#group269` (href="#", 클릭 이벤트가 JS로 바인딩돼서 그냥 클릭하면 됨.
  분배내역 페이지처럼 evaluate 우회 필요 없었음)
- 그리드: id **`grid5`**. 레코드 1건 = `<tr>` 1개로 분배내역 그리드보다 단순
  (rowspan 없음). col_id: `ANYTM_REPTG_DT`(기준일), `NAV_AMT`(기준가),
  `FUND_NETASST_TOTAMT`(순자산, 억원 단위), `TOT_DIV_PAY_AMT`(분배금, 원 단위
  - 실측상 대부분 빈 값), `RGT_RACD`(비고, 분배 있었던 날 "배당/분배" 라벨 붙음)
- **분배일 판별은 "분배금" 컬럼이 아니라 "비고"="배당/분배" 로 해야 함** — 분배금
  컬럼이 이 그리드에서는 거의 항상 비어 있어서(결산일과 반영일이 달라서 그런 듯)
  비고 라벨로 판별하는 게 훨씬 안정적
- 페이지네이션: 페이지 링크 id `#gridPaging_page_N`. 화면에 보이는 페이지 번호
  그룹(예: 1~7)을 넘어가는 "다음 그룹" 버튼은 아직 셀렉터 못 찾음 (다음 세션 TODO)

## 개발 시 유의사항
- 세이브로 페이지는 로드 후 WebSquare 초기화에 시간 걸림. `wait_for_load_state("networkidle")` 후에도 `time.sleep(1-2)` 필요
- 펀드 검색은 새 브라우저 팝업이 아니라 같은 페이지 안의 레이어 팝업 + iframe 으로 열림. `page.wait_for_event("popup")` 은 안 걸림 — `iframe#iframeFnMn` 을 기다렸다가 `content_frame()` 으로 접근
- 첫 실행은 `headless=False` 로 두고 실제 흐름 확인. 셀렉터 자동생성 ID (예: `_wq_uuid_...`) 는 매번 다를 수 있으니 `id*=` 부분매칭 또는 label/text 기반 셀렉터 우선
- 조회 기간은 날짜 직접입력 대신 프리셋 드롭다운(1주~3년) 사용. 기본값 1년.
  3년보다 오래된 데이터는 프리셋에 없어서 필요하면 별도 확인 필요

## 참고 링크
- 세이브로 펀드별분배금지급내역: https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/fund/BIP_CNTS05008V.xml&menuNo=152
- 세이브로 펀드찾기 상세검색: https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/fund/BIP_CNTS05017V.xml&menuNo=163
- Playwright Python 문서: https://playwright.dev/python/

## 커밋 컨벤션
- `feat:` 새 기능
- `fix:` 버그 수정
- `refactor:` 리팩터링
- `docs:` 문서
- `chore:` 설정, 의존성 등
