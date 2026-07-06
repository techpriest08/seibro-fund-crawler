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
      컬럼으로 계산해서 제공하길래 그걸 조회기간 내 합산하는 방식으로 구현
- [ ] XML POST endpoint 및 payload 리버스 (DevTools Network 캡처)
- [ ] 다수 펀드 배치 조회 (batch_crawl 함수는 있으나 여러 펀드로 실측 안 함)
- [ ] 엑셀 연동 (기존 월지급식 펀드 비교 파일과 결합)
- [ ] (다음 세션, 지금 당장 아님) 시각화용 독립 실행 exe / 펀드 규모(AUM) 변화
      추적 기능 — 메모리에 저장된 향후 요청 참고

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
- **핵심 발견**: "1,000좌 금액 대비 1,000좌당 분배금 비율" 은 세이브로가
  이미 `주(좌)당배당율` (col_id=CASH_ALOC_RATIO) 컬럼으로 계산해서 주고
  있음 — 별도 NAV 데이터 소스를 찾아서 직접 계산할 필요 없이, 조회 기간
  내 이 컬럼 값을 합산하면 됨 (비율이라 1좌 기준이든 1,000좌 기준이든
  스케일링 불필요)

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
