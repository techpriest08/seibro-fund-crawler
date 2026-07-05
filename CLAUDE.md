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
- [x] 실제 페이지 열어서 셀렉터 확정 (일부 — 아래 상세)
- [ ] 팝업 검색창 처리 로직 완성 (검색 결과 행 클릭 셀렉터 미검증 — 다음 작업)
- [ ] 결과 테이블 파싱 및 컬럼명 확정
- [ ] XML POST endpoint 및 payload 리버스 (DevTools Network 캡처)
- [ ] 다수 펀드 배치 조회
- [ ] 엑셀 연동 (기존 월지급식 펀드 비교 파일과 결합)

### 확정된 셀렉터 (2026-07-05 headless=False 실측)
- 펀드 검색 아이콘: `#fn_group4` — 클릭해도 **새 브라우저 팝업이 뜨지 않음**.
  같은 페이지 안의 레이어 팝업 `div#Lpopup_wrap` 이 표시되고, 그 안의
  `iframe#iframeFnMn` 에 실제 검색 UI 로드됨
  (src=`/IPORTAL/user/etc/BIP_CMUC01044P.xml&ret_code=KOR_SECN_CD&ret_code_nm=KOR_SECN_NM`)
- iframe 내부 검색창: `input#search_string`, 검색 버튼: `a#group149`
- 조회기간: `input#startDt_input` / `input#endDt_input`
- 조회 버튼: `a.btn_seach` (href=`javascript:searchPList();`)
- 펀드명 직접입력 필드도 메인 페이지에 존재: `input#KOR_SECN_NM` (텍스트),
  `input#KOR_SECN_CD` (hidden) — 팝업 없이 이 필드에 바로 채워서 조회가
  되는지는 미검증. 되면 팝업 로직을 아예 건너뛸 수 있어 다음에 우선 확인
- 결과 그리드: id `gridDRConvList` 로 추정 (CSS 참조로만 확인, 실제 조회
  성공 후 미검증)
- **미검증**: "뱅크론" 검색 후 실제 결과 리스트 행(row) 셀렉터. 검증 도중
  작업이 중단되어 다음 세션에서 이어서 확인 필요

## 개발 시 유의사항
- 세이브로 페이지는 로드 후 WebSquare 초기화에 시간 걸림. `wait_for_load_state("networkidle")` 후에도 `time.sleep(1-2)` 필요
- 펀드 검색은 새 브라우저 팝업이 아니라 같은 페이지 안의 레이어 팝업 + iframe 으로 열림. `page.wait_for_event("popup")` 은 안 걸림 — `iframe#iframeFnMn` 을 기다렸다가 `content_frame()` 으로 접근
- 첫 실행은 `headless=False` 로 두고 실제 흐름 확인. 셀렉터 자동생성 ID (예: `_wq_uuid_...`) 는 매번 다를 수 있으니 `id*=` 부분매칭 또는 label/text 기반 셀렉터 우선
- 조회 기간 기본값 3년. 이보다 오래된 데이터가 필요하면 여러 번 나눠 조회

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
