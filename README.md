# SEIBro 펀드 분배금 크롤러

한국예탁결제원 세이브로(SEIBro)에서 공모펀드의 **분배금 지급 이력**과 **기준가/순자산(AUM)
변화**를 자동으로 조회해서, 분배율(세전/세후)과 원금 잠식 여부를 계산해주는 도구입니다.

월지급식 채권 펀드(뱅크론, 하이일드 등)처럼 정기적으로 분배금을 주는 펀드가 실제로는
수익이 아니라 원금을 갉아먹으면서 분배하고 있는 건 아닌지 확인하려는 목적으로 만들었습니다.

> ⚠️ **투자 조언이 아닙니다.** 이 도구가 계산하는 수치(분배율, 세율, 순자산 변화 등)는
> 참고용이며 실제 투자 판단의 근거로 쓰기 전에 반드시 원본 데이터를 직접 확인하세요.
> 세후 분배율은 배당소득세 15.4%(일반과세 기준)를 가정한 근사치이고, 계좌 종류나
> 과세 방식에 따라 실제 세율은 다를 수 있습니다.

## 주요 기능

- 펀드명(부분 검색)이나 표준코드(ISIN)로 펀드를 찾아 최근 1년간 분배금 지급 내역 조회
- 분배율을 **세전/세후**로, 평균 기준가·1,000좌당 분배금 합계와 함께 계산
- 1년치 일별 기준가·순자산(AUM) 데이터를 페이지네이션까지 순회해서 전부 수집
- **설정액**(펀드 최초 모집금액, 고정값)과 **순자산**(현재 시가총액, 매일 변동)을
  구분해서, 순자산 감소분 중 실제 분배로 나간 금액과 순수 운용손익을 분리해서 보여줌
- CLI 스크립트 또는 Tkinter GUI(더블클릭 실행용 exe로 패키징 가능)로 사용 가능

## 폴더 구조

```
seibro-fund-crawler/
├── README.md
├── LICENSE
├── CLAUDE.md                       # Claude Code로 이어서 개발할 때 참고하는 컨텍스트 문서
├── requirements.txt
├── SeibroFundViewer.spec           # PyInstaller 빌드 설정
└── src/
    ├── seibro_fund_distribution.py # 크롤링 + 계산 로직 (CLI로 직접 실행 가능)
    └── gui_app.py                  # Tkinter GUI 프론트엔드 (exe 패키징 대상)
```

## 설치

### 요구 사항

- Python 3.11 이상
- Windows (현재까지 Windows 기준으로만 개발/검증됨 — 다른 OS는 `src/seibro_fund_distribution.py`
  상단의 Windows 전용 처리(콘솔 인코딩, exe 브라우저 경로 지정) 부분만 빼면 동작할 가능성이
  높지만 확인은 안 됨)
- 인터넷 연결 (seibro.or.kr 접속 필요)

### 설치 단계

```bash
git clone https://github.com/techpriest08/seibro-fund-crawler.git
cd seibro-fund-crawler

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

`playwright install chromium` 은 필수입니다 — Playwright 파이썬 패키지만 설치해서는
실제 브라우저 바이너리가 따로 없어서 동작하지 않습니다.

## 사용법

### 1) CLI로 실행

```bash
python src/seibro_fund_distribution.py
```

`src/seibro_fund_distribution.py` 맨 아래 `__main__` 블록의 `test_fund = FundQuery(name="...")`
부분을 원하는 펀드명으로 바꾸면 됩니다. 기본적으로 브라우저 창이 뜨는 채로(`headless=False`)
동작해서 실제로 어떤 페이지를 조회하는지 눈으로 볼 수 있습니다. 결과는 `test_result.csv`,
`test_nav_result.csv` 로 저장됩니다.

### 2) GUI로 실행 (개발 모드)

```bash
python src/gui_app.py
```

펀드명 입력창 + 조회 버튼이 있는 창이 뜹니다. 브라우저는 백그라운드(headless)로 동작해서
따로 안 보입니다. AUM 1년치를 페이지네이션으로 전부 모으기 때문에 조회에 1~2분 정도 걸릴
수 있습니다.

### 3) exe로 패키징해서 더블클릭 실행

터미널 명령어 없이 쓰고 싶으면 exe로 빌드합니다.

```bash
python -m PyInstaller --noconfirm --onefile --windowed --name SeibroFundViewer src/gui_app.py
```

`dist/SeibroFundViewer.exe` 가 생성됩니다.

**주의**: 이 exe는 Playwright 파이썬 코드만 포함하고 Chromium 브라우저 바이너리는 번들하지
않습니다. exe를 실행할 컴퓨터에 `playwright install chromium` 이 미리 되어 있어야 합니다
(즉 지금은 이 저장소를 처음부터 클론해서 설치를 마친 컴퓨터에서만 exe가 동작하고, exe
파일 하나만 다른 컴퓨터로 복사해서 실행할 수는 없습니다). 완전 독립 배포는 `CLAUDE.md`의
TODO 항목으로 남아 있습니다.

## 데이터 소스

- [세이브로 펀드별분배금지급내역](https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/fund/BIP_CNTS05008V.xml&menuNo=152)
- [세이브로 펀드종합정보 (기준가/분배금 탭)](https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/fund/BIP_CNTS05011V.xml&menuNo=155)

세이브로는 WebSquare 기반 SPA라 셀렉터가 자동생성 ID를 많이 씁니다. 실측으로 확정한
셀렉터와 그 근거는 `CLAUDE.md`에 상세히 기록되어 있습니다.

## 개발 배경 / 더 자세한 내용

이 프로젝트는 [Claude Code](https://claude.com/claude-code)와 함께 개발했습니다.
셀렉터를 어떻게 찾았는지, 어떤 시행착오가 있었는지, 다음에 뭘 할 계획인지는 전부
`CLAUDE.md`에 기록되어 있습니다 — Claude Code로 이어서 작업하고 싶다면 그 파일을
먼저 읽게 하면 됩니다.

## 라이선스

[MIT](LICENSE)
