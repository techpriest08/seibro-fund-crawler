# SEIBro 펀드 분배금 크롤러

한국예탁결제원 세이브로 (SEIBro) 의 `펀드별분배금지급내역` 페이지에서
공모펀드 분배금 이력을 자동 수집.

## Quick Start

```bash
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt
playwright install chromium

python seibro_fund_distribution.py
```

## Claude Code 로 이어서 작업할 때 첫 지시 예시

```
CLAUDE.md 를 먼저 읽고 프로젝트 상태를 파악해줘.

첫 작업: seibro_fund_distribution.py 를 headless=False 로 실행해서
실제 세이브로 페이지 흐름을 확인하고,
TODO 로 표시된 셀렉터들을 실제 페이지 DOM 에 맞게 조정해줘.
필요하면 debug_screenshots 폴더의 캡처를 확인해서
어떤 요소를 클릭해야 하는지 판단하고, DevTools 로 정확한 셀렉터 잡아줘.

셀렉터가 정상 작동해서 검색 결과가 나오면,
그 다음은 결과 테이블 컬럼명을 확정하고 _parse_result_table 을 정리해줘.
```

이후 XML POST 방식으로 최적화하려면:

```
이제 Playwright 로 접근이 되니까, 브라우저 DevTools 의 Network 탭 열고
'조회' 버튼 누를 때 발생하는 XHR/Fetch 요청을 캡처해서,
그걸 requests 로 재현하는 xml_scraper.py 를 만들어줘.
Playwright 없이 순수 HTTP 로 호출하는 게 목표.
```

## 폴더 구조 (예상)

```
seibro-fund-crawler/
├── CLAUDE.md                       # Claude Code 컨텍스트
├── README.md
├── requirements.txt
├── .gitignore
├── seibro_fund_distribution.py     # 현재: 단일 파일 스켈레톤
└── (앞으로 추가)
    ├── scraper/
    │   ├── __init__.py
    │   ├── playwright_scraper.py   # UI 자동화
    │   ├── xml_scraper.py          # 순수 HTTP
    │   └── common.py
    ├── main.py
    └── data/
        └── funds.xlsx              # 조회 대상 펀드 리스트
```
