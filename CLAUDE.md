# SEIBro 펀드 분배금 크롤러

## 사용자 컨텍스트
- 엔지니어 배경의 개인 투자자
- 주력 언어: 한국어 반말, 간결/직접적 소통 선호
- 답변 시 이름 부르지 말 것
- 되묻지 말고 바로 진행. 애매하면 가정을 명시하고 진행
- **수정 작업이 완료되면 묻지 말고 무조건 커밋 + GitHub 푸시** (사용자가 집/
  다른 컴퓨터 두 대를 오가며 작업하므로 푸시 누락 시 이어서 작업 불가)

## 프로젝트 목적
한국 판매 월지급식 채권 펀드 (뱅크론, 하이일드 위주) 리서치용
분배금 이력 데이터 수집. 최종적으로 다음과 연동:

- 보유 중인 월지급식 펀드 여러 개를 비교하는 엑셀 파일
- 고배율(10%+) 분배 펀드가 원금을 갉아먹으면서 분배하는 건 아닌지 구조 파악
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
- `src/seibro_fund_distribution.py`: 크롤링 + 계산 로직 전체 (Playwright 기반).
  CLI로 직접 실행 가능 (`python src/seibro_fund_distribution.py`)
- `src/gui_app.py`: Tkinter GUI 프론트엔드. 위 모듈의 함수를 그대로 재사용하고
  펀드명 입력창 + 조회 버튼 + 결과 표시만 담당. PyInstaller로 exe 패키징 대상
- (미착수) XML POST 직접 호출 방식 — DevTools Network 캡처로 payload 확보 후
  Playwright 없이 순수 HTTP로 재현하는 것이 목표 (아래 TODO 참고)

## 진행 상황
- [x] 접근 전략 결정 (Playwright 우선, XML 이차)
- [x] 초기 스켈레톤 코드 작성 (src/seibro_fund_distribution.py)
- [x] 실제 페이지 열어서 셀렉터 확정
- [x] 팝업 검색창 처리 로직 완성 (검색 → 결과 선택 → 메인 페이지 반영까지 확인)
- [x] 결과 테이블 파싱 및 컬럼명 확정 (그리드 id `gridFundExerList`, col_id 기반 파싱)
- [x] "1년간 1,000좌 금액 대비 1,000좌당 분배금 비율" — 세전/세후 비교까지 포함
      (`summarize_distribution_yield()`). 세이브로 제공 `주(좌)당배당율` 컬럼은
      스케일 버그(1,000배 차이)로 못 쓰고, `(주당배당액*1000)/결산기준가*100` 직접
      계산으로 전환. **2026-07-07 추가 개선**: 회차별 비율을 합산하던 방식에서
      "평균 기준가 대비 총분배금" 방식으로 변경, 배당소득세 15.4%(가정) 적용한
      세후 수치도 같이 계산. 실측(AB 월지급 글로벌 고수익): 평균기준가 629.31,
      1,000좌당 분배금 세전 40.0원/세후 33.84원, 분배율 세전 6.36%/세후 5.38%
- [x] **콘솔 한글 깨짐 수정** — Windows 콘솔 cp949 vs UTF-8 불일치로 로그가 깨져
      보이던 문제. 스크립트 시작 시 `SetConsoleOutputCP(65001)` + stdout/stderr
      `.reconfigure(encoding="utf-8")` 로 해결
- [x] **펀드 총자산(AUM) 변화 추적 - 1년 전체 페이지네이션 완성** — 데이터 소스:
      펀드종합정보(`BIP_CNTS05011V.xml&menuNo=155`) > "기준가/분배금" 탭.
      `crawl_fund_nav_history()` + `_iterate_all_nav_pages()` 로 그리드
      페이지네이션(`#gridPaging_page_N`, DOM에서 현재 선택된 링크 다음 것을 계속
      클릭하는 방식)을 끝까지 순회해서 1년치(약 250영업일) 전체를 모음.
      `summarize_aum_change_on_distribution()` 이 분배 이벤트별 상세 + 조회기간
      전체 합계(시작/종료 AUM, 증감액/율)를 dict로 반환하도록 확장. 실측(AB
      월지급 글로벌 고수익): 1년간 순자산 4,773→2,665억원 (-44.17%) — 상당한
      원금 잠식이 실제로 확인됨
- [x] **PyInstaller exe 패키징 (프로토타입)** — `src/gui_app.py` (Tkinter, 펀드명
      입력창 + 조회 버튼 + 스크롤 가능한 결과 텍스트 영역) 작성 후
      `python -m PyInstaller --onefile --windowed --name SeibroFundViewer src/gui_app.py`
      로 빌드 성공. `dist/SeibroFundViewer.exe` (약 74MB) 더블클릭 시 창 뜨는 것까지
      확인함. **한계**: Chromium 브라우저 바이너리는 exe에 번들 안 됨 — 실행
      컴퓨터에 `playwright install chromium` 이 미리 되어 있어야 함. 완전
      독립형(다른 PC에 exe만 복사해서 실행)으로 만들려면 Chromium 폴더까지 같이
      묶는 작업 추가 필요 (다음 과제)
- [x] **조회된 실제 펀드명 표시** — "월지급"처럼 부분 검색어를 넣으면 결과 중
      첫 번째가 자동 선택되는데, 실제로 어떤 펀드가 조회됐는지 결과 맨 위 한 줄에
      표시 (`_get_selected_fund_name()`, "조회된펀드명" 컬럼은 표에서는 빼고
      맨 위에만 표시)
- [x] **설정액 vs 순자산 구분 + 분배 제외 순수 운용손익** — 설정액(펀드 최초
      모집금액, 고정값)과 순자산(현재 시가총액, 매일 변동)을 혼동하면 안 된다는
      피드백 반영. `summarize_aum_vs_distribution()` 추가: 1년 전 순자산 vs
      현재 순자산 비교에서, 그 중 실제로 분배로 빠져나간 금액(총분배유출액,
      dist_df의 "총분배금" 합계)을 분리하고, 그걸 제외했을 때 펀드 자체
      운용손익이 플러스/마이너스 몇 %인지 계산. 실측(AB 월지급 글로벌 고수익):
      순자산 -44.17%(4,773→2,665억원) 중 분배유출 237.4억원 제외하면 순수
      운용손익 -1,870.6억원(-39.19%, 마이너스) — 감소분 대부분이 분배가 아니라
      운용손실이라는 게 드러남
- [x] **기준가 변화율 + 결과 표 축약** — 분배율 섹션 바로 아래에 "1년간 기준가
      변화"(시작가→종료가, 변화액/율) 추가 (`summarize_price_change()`). 실측:
      637.49원→616.74원 (-20.75원, -3.26%). 또한 1년치 일별 원자료(약 250행)를
      GUI에 다 나열하지 않고 앞/뒤 5행만 보여주도록 축약(`_condense_table()`,
      컬럼 정렬 깨지지 않게 전체를 한 번에 to_string() 한 뒤 줄 단위로 자름).
      분배일별 AUM 변화 상세는 (짧아서) 계속 전체 표시
- [x] **setup.exe 설치 프로그램 (완전 독립형 배포 해결)** — Inno Setup 6 기반
      `installer/SeibroFundViewer.iss` 작성. `dist/SeibroFundViewer_Setup.exe`
      (약 153MB) 하나만 받아 실행하면 ① 프로그램 본체(`%LOCALAPPDATA%\Programs\
      SeibroFundViewer`, 관리자 권한 불필요) ② Playwright Chromium까지 전부
      설치됨. **핵심 발견**: GUI는 headless=True 로만 브라우저를 쓰므로 전체
      Chromium(415MB) 대신 chromium_headless_shell(269MB)+winldd 만 번들해도
      동작함 (격리 폴더에 headless shell만 두고 PLAYWRIGHT_BROWSERS_PATH 지정
      후 실제 페이지 로드까지 실측 확인). 무인 설치(/VERYSILENT) → 설치된 exe
      실행 → 창 뜨는 것까지 검증 완료. 빌드법은 iss 파일 상단 주석 참고
      (ISCC.exe 는 winget install JRSoftware.InnoSetup 로 설치)
- [x] **검색 결과 전체 목록 표시 + 사용자 선택 조회** — 기존 "첫 번째 결과
      자동 선택" 방식을 폐기. `search_funds(keyword)` 신설: 검색 팝업에서
      ul#isinList 의 a[id$='_ISIN_ROW'] href(javascript:SelectedValueReturn
      ('ISIN','펀드명'))를 클릭 없이 파싱해 전체 목록 [{isin, name}] 반환
      (실측: "월지급" → 153건). `_search_fund_in_popup()` 에 target_isin
      파라미터 추가 — 검색은 키워드로 하되 선택은 `a[href*='{isin}']` 클릭으로
      정확히 특정 (팝업 검색창에 ISIN 직접 입력은 미검증이라 안 씀). GUI는
      왼쪽에 검색 결과 Listbox 를 두고 더블클릭/버튼으로 조회 시작
- [x] **최근 검색 결과 저장/다시 보기** — 조회 완료 시 결과 텍스트를
      `%LOCALAPPDATA%\SeibroFundViewer\history\*.json` (name/isin/queried_at/
      text, 최신 30건 유지)으로 자동 저장. GUI 왼쪽 "최근 검색 결과" Listbox
      에서 더블클릭하면 크롤링 없이 저장본을 "[최근 검색 결과] 펀드명 — 시각
      조회 (저장본)" 헤더와 함께 바로 표시. GUI e2e (검색→2번째 항목 선택
      조회→저장→다시 보기) 스크립트 구동으로 검증
- [x] **크롤링 안정화 - 간헐 실패 3종 해결** (2026-07-11 밤 실측, "AB는 되는데
      다른 펀드는 안 된다" 증상의 실제 원인들. 펀드 종류와 무관한 타이밍 문제였음):
      ① 돋보기 아이콘(#fn_group4) 물리 클릭을 검색 드롭다운 레이어(dd#fn_group2)가
      간헐적으로 가로챔 → `_js_click()` (DOM click() 직접 호출)으로 교체.
      나브 페이지 돋보기도 동일 적용.
      ② 세이브로가 시간대에 따라 "Error 안내 - 요청하신 페이지를 표시할 수
      없습니다" 페이지를 반환 (22시경 빈발 실측) → `_goto_with_retry()`:
      준비 요소 없으면 3회 재접속, 최종 실패 시 한국어 안내 RuntimeError.
      실측: 2회 오류 페이지 후 3회째 성공한 사례 확인.
      ③ 사이트 느릴 때 networkidle 15초 초과로 조회가 통째로 죽음 →
      `_wait_websquare()` 가 타임아웃 시 경고만 남기고 진행하도록 완화.
      또한 크롤 함수들이 PWTimeout 을 빈 DataFrame 으로 삼키던 것을
      "분배 이력 없는 펀드"와 구분 안 되는 문제 때문에 명시적 RuntimeError
      (한국어 안내)로 변경 — GUI 오류 팝업으로 사용자에게 전달됨
- [x] **브라우저 자동 설치 (exe 완전 독립형 완성)** — setup.exe 없이
      SeibroFundViewer.exe 만 복사해 간 컴퓨터에서 "BrowserType.launch:
      Executable doesn't exist" 오류가 나던 문제의 근본 해결.
      `_launch_chromium()`: launch 실패가 "Executable doesn't exist" 면
      `_install_chromium()` 으로 자동 다운로드 후 1회 재시도. 설치는 exe 에
      번들된 playwright 드라이버(node.exe + cli.js, pyi-archive_viewer 로 번들
      확인)를 subprocess 로 호출 (`node cli.js install chromium --only-shell`,
      CREATE_NO_WINDOW 로 콘솔 번쩍임 방지, headless=False 개발용이면 전체
      chromium). 실측: 빈 PLAYWRIGHT_BROWSERS_PATH 에서 34초 만에 자동 설치
      후 검색 23건 성공. 실패 시 "인터넷 연결 확인" 한국어 RuntimeError
- [x] **ETF 필터 + 대량 검색 결과 안정화** — "미래에셋 펀드만 안 뜬다" 신고의
      원인: 검색 팝업에 ETF 도 같이 나오는데(실측: "미래에셋" 2,240건 중 287건이
      TIGER ETF) ETF 는 분배내역 메뉴에 데이터가 없어 골라도 빈 결과만 나옴.
      `_is_etf()` 판별(이름에 "상장지수"/"ETF", 또는 ISIN 이 KR7 시작 - 일반
      공모펀드는 KRZ5 시작)로 `search_funds(exclude_etf=True 기본)` 에서 제외.
      추가 안정화: ① 검색 후 고정 sleep(1초)만으로는 결과 수천 건일 때 로딩
      전에 빈 목록을 읽는 경우 실측(같은 검색어로 2,240건/0건 왔다갔다) →
      첫 결과 행(a[id$='_ISIN_ROW']) attached 를 명시적으로 대기(10초).
      ② 팝업 결과 선택도 물리 클릭 → DOM click() 직접 호출로 변경, 대기
      15초로 확대. 검증: 미래에셋 1,953건 중 맨 마지막 항목 선택 조회 성공
- [x] **최근 검색 결과 영구 보관 + 요약 엑셀 자동 관리 + 목록 가로 스크롤** —
      ① 히스토리를 "최신 30건 삭제" 방식에서 "펀드(ISIN)당 파일 1개, 개수
      제한 없음"으로 변경: 파일명을 ISIN 으로 써서 같은 펀드 재조회 시 그
      저장본만 갱신되고, 나머지는 사용자가 다시 조회할 때까지 계속 남음.
      로드 시 ISIN 중복 제거 + 저장 시 예전 시각 기반 파일명 잔재 정리.
      ② 조회할 때마다 핵심 수치(분배횟수/분배율 세전·세후/기준가·순자산
      변화/분배제외 운용손익 등 15개 컬럼)를 `%LOCALAPPDATA%\SeibroFundViewer\
      펀드조회요약.xlsx` 로 자동 재생성 (pandas to_excel, 펀드당 1행 - 여러
      월지급식 펀드 비교용). GUI [요약 엑셀 열기] 버튼으로 바로 열기.
      엑셀에서 열어둔 채면 PermissionError → 상태줄 안내만 하고 다음 조회 때
      재갱신. 수치는 history JSON 의 summary 필드에도 같이 저장.
      ③ 검색 결과/최근 검색 결과 Listbox 에 가로 스크롤바 추가 (긴 펀드명)
- [x] **순자산 미제공 클래스 + 운용종료 펀드 처리** — "미래에셋만 내용이 안
      뜬다" 2차 신고의 실제 원인: 미래에셋 일부 클래스(실측: 배당과인컴30
      성과보수 A-e)는 기준가는 매일 정상인데 세이브로가 설정액·순자산을 전
      기간 0 으로만 제공 → "순자산 0.00억원 → 0.00억원" 같은 거짓 표시가 됐음
      (같은 운용사 다른 펀드는 정상. 운용 종료 아님). 처리:
      ① `summarize_aum_change_on_distribution()` 에서 순자산이 전부 0/결측이면
      "데이터 없음"(None) 반환, GUI 는 "세이브로가 이 클래스의 순자산을 제공하지
      않음, 다른 클래스 조회 권장" 안내 표시 (기준가·분배 분석은 정상 표시)
      ② 분배내역·기준가가 모두 없는 펀드(진짜 운용종료/청산 추정)는 안내
      메시지만 띄우고 최근 검색 결과/요약 엑셀에 저장하지 않음.
      참고: 검색 팝업에는 운용상태 정보가 전혀 없어서(li 에 ISIN+펀드명뿐,
      드롭다운은 유형/지역/테마·운용사/판매사 검색 분류) 목록 단계에서
      청산 펀드를 미리 걸러내는 건 불가 - 조회 시점에 판별해 안내하는 방식 채택
- [ ] XML POST endpoint 및 payload 리버스 (DevTools Network 캡처)
- [ ] 다수 펀드 배치 조회 (batch_crawl 함수는 있으나 여러 펀드로 실측 안 함)
- [ ] 엑셀 연동 (기존 월지급식 펀드 비교 파일과 결합)

### 다음 세션 TODO
- [ ] **월평균 기준가 대비 분배율** — 조회기간이 1년 미만인 신생 펀드는
      1년 데이터가 없으니, 보유 기간의 월평균 기준가 대비 분배율로 대체
      계산하는 로직 추가
- [ ] **AUM 1년 조회가 오래 걸림** — 페이지네이션 250개 행 모으는 데 30초
      정도 걸림(GUI에서는 분배내역 조회까지 합쳐 1~2분). 매 페이지 전환마다
      `time.sleep` 대기가 있어서 그런데, 더 짧게 줄일 수 있는지 확인 필요
- [ ] **GUI 실사용 테스트** — 스크립트로 구동하는 e2e (검색→선택 조회→결과
      표시→저장)는 통과했지만, 사람이 직접 exe 를 눌러보는 확인은 아직 안 함
- [ ] **시각화** — 지금 GUI는 결과를 텍스트(표 형태 문자열)로만 보여줌. 분배
      이력 + AUM 변화 + 분배율을 그래프(예: matplotlib) 로 보여주는 것까지
      포함. 세부 UI는 착수 전 확인

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
- **페이지네이션 (해결됨)**: 페이지 링크 id `#gridPaging_page_N` 은 절대 페이지
  번호가 아니라 화면에 보이는 슬라이딩 윈도우 상의 상대 위치. `#gridPaging_next_btn`
  은 "그룹 이동"이 아니라 "다음 페이지"(1칸 전진) 버튼이었음 (alt 텍스트 확인:
  첫 페이지/이전 페이지/다음 페이지/마지막 페이지 조합). 그래서 매번 DOM에서
  `class*="label_selected"` 인 현재 선택 링크를 찾아 그 다음 링크를 클릭하고,
  이미 마지막 링크면 `#gridPaging_next_btn` 을 눌러 한 칸 전진하는 방식으로
  전체 순회 (`_iterate_all_nav_pages()`). 1년 기준 약 25페이지(250행) 순회 확인

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
