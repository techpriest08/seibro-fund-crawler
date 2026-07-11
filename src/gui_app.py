"""
SEIBro 펀드 분배금/AUM 조회 GUI.

exe로 더블클릭 실행하면 새 창이 뜨는 형태를 목표로 만든 Tkinter 프론트엔드.
크롤링 로직 자체는 seibro_fund_distribution.py 그대로 재사용한다.

동작 흐름 (첫 결과 자동 선택 방식에서 변경):
1. 펀드명 키워드 입력 → [펀드 검색] → 검색 결과 "전체 목록"을 왼쪽에 표시
2. 목록에서 원하는 펀드를 골라 [선택한 펀드 조회] (또는 더블클릭) → 크롤링 시작
3. 조회가 끝난 결과는 %LOCALAPPDATA%/SeibroFundViewer/history 에 자동 저장되고,
   왼쪽 "최근 검색 결과" 목록에서 더블클릭하면 크롤링 없이 바로 다시 볼 수 있다
"""
from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import pandas as pd

from seibro_fund_distribution import (
    KOREAN_DIVIDEND_TAX_RATE,
    FundQuery,
    crawl_fund_distribution,
    crawl_fund_nav_history,
    search_funds,
    summarize_aum_change_on_distribution,
    summarize_aum_vs_distribution,
    summarize_distribution_yield,
    summarize_price_change,
)

# 조회 결과 저장 위치. exe/스크립트 어느 쪽으로 실행해도 같은 곳을 보도록
# 사용자 프로필 하위 고정 경로를 쓴다 (Playwright 브라우저 경로와 같은 방식).
HISTORY_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SeibroFundViewer" / "history"
HISTORY_LIMIT = 30  # 이 개수를 넘으면 오래된 결과부터 삭제


def _load_history() -> list[dict]:
    """저장된 조회 결과 목록을 최신순으로 반환. 깨진 파일은 조용히 건너뛴다."""
    if not HISTORY_DIR.exists():
        return []
    items: list[dict] = []
    for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        try:
            items.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return items


def _save_history_entry(name: str, isin: str, text: str) -> None:
    """조회 결과 1건을 저장하고, HISTORY_LIMIT 초과분은 오래된 것부터 지운다."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now()
    entry = {
        "name": name,
        "isin": isin,
        "queried_at": f"{ts:%Y-%m-%d %H:%M}",
        "text": text,
    }
    (HISTORY_DIR / f"{ts:%Y%m%d_%H%M%S_%f}.json").write_text(
        json.dumps(entry, ensure_ascii=False), encoding="utf-8"
    )
    for old in sorted(HISTORY_DIR.glob("*.json"), reverse=True)[HISTORY_LIMIT:]:
        try:
            old.unlink()
        except OSError:
            pass


def _condense_table(df: pd.DataFrame, head: int = 5, tail: int = 5) -> str:
    """
    긴 표는 앞/뒤 몇 줄만 보여주고 중간은 생략한다. 컬럼 폭이 head/tail 을 따로
    to_string() 하면 서로 어긋날 수 있어서, 전체를 한 번에 문자열로 만든 뒤
    줄 단위로 잘라낸다(그래야 컬럼 정렬이 유지됨).
    """
    if df.empty:
        return "(데이터 없음)"
    full_str = df.to_string(index=False)
    lines = full_str.split("\n")
    header, data_lines = lines[0], lines[1:]
    if len(data_lines) <= head + tail:
        return full_str
    omitted = len(data_lines) - head - tail
    return "\n".join([header, *data_lines[:head], f"... ({omitted}행 생략) ...", *data_lines[-tail:]])


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("세이브로 펀드 분배금 조회")
        self.geometry("1250x700")

        # --- 상단: 검색어 입력 ---
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="펀드명:").pack(side="left")
        self.name_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.name_var, width=45)
        entry.pack(side="left", padx=5)
        entry.bind("<Return>", lambda _e: self.on_search())
        self.search_btn = ttk.Button(top, text="펀드 검색", command=self.on_search)
        self.search_btn.pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="펀드명을 입력하고 [펀드 검색]을 누르세요.")
        ttk.Label(self, textvariable=self.status_var, padding=(10, 0)).pack(anchor="w")

        # --- 본문: 왼쪽 목록 패널 + 오른쪽 결과 텍스트 ---
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        left = ttk.Frame(body, width=400)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        left.rowconfigure(0, weight=3)
        left.rowconfigure(1, weight=2)
        left.columnconfigure(0, weight=1)

        # 검색 결과 전체 목록 (여기서 골라서 조회)
        search_box = ttk.Labelframe(left, text="펀드 검색 결과 (더블클릭으로 조회)", padding=5)
        search_box.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        search_box.rowconfigure(0, weight=1)
        search_box.columnconfigure(0, weight=1)

        self.search_list = tk.Listbox(search_box, exportselection=False)
        s_scroll = ttk.Scrollbar(search_box, orient="vertical", command=self.search_list.yview)
        self.search_list.configure(yscrollcommand=s_scroll.set)
        self.search_list.grid(row=0, column=0, sticky="nsew")
        s_scroll.grid(row=0, column=1, sticky="ns")
        self.search_list.bind("<Double-Button-1>", lambda _e: self.on_fetch())
        self.fetch_btn = ttk.Button(search_box, text="선택한 펀드 조회", command=self.on_fetch)
        self.fetch_btn.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        # 최근 검색 결과 (저장본 다시 보기 - 크롤링 안 함)
        history_box = ttk.Labelframe(left, text="최근 검색 결과 (더블클릭으로 다시 보기)", padding=5)
        history_box.grid(row=1, column=0, sticky="nsew")
        history_box.rowconfigure(0, weight=1)
        history_box.columnconfigure(0, weight=1)

        self.history_list = tk.Listbox(history_box, exportselection=False)
        h_scroll = ttk.Scrollbar(history_box, orient="vertical", command=self.history_list.yview)
        self.history_list.configure(yscrollcommand=h_scroll.set)
        self.history_list.grid(row=0, column=0, sticky="nsew")
        h_scroll.grid(row=0, column=1, sticky="ns")
        self.history_list.bind("<Double-Button-1>", lambda _e: self.on_show_history())

        # 결과 표가 넓고 길어서 창을 키워도 다 안 보일 수 있음 - 세로/가로 스크롤 둘 다 추가
        text_frame = ttk.Frame(body)
        text_frame.grid(row=0, column=1, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.text = tk.Text(text_frame, wrap="none", font=("Consolas", 10))
        y_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        x_scroll = ttk.Scrollbar(text_frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        self._search_results: list[dict] = []   # [{"isin", "name"}, ...]
        self._history: list[dict] = []
        self._result_queue: queue.Queue = queue.Queue()
        self._refresh_history_list()
        self.after(200, self._poll_queue)

    # ----- 검색 (전체 목록 가져오기) -----

    def on_search(self) -> None:
        keyword = self.name_var.get().strip()
        if not keyword:
            messagebox.showwarning("입력 필요", "펀드명을 입력하세요.")
            return
        self._set_busy(True)
        self.status_var.set(f"'{keyword}' 검색 중... (10초 정도 걸립니다)")
        threading.Thread(target=self._run_search, args=(keyword,), daemon=True).start()

    def _run_search(self, keyword: str) -> None:
        try:
            results = search_funds(keyword, headless=True)
            self._result_queue.put(("search_ok", keyword, results))
        except Exception as e:  # noqa: BLE001 - 백그라운드 스레드 예외를 GUI로 전달
            self._result_queue.put(("error", str(e)))

    # ----- 조회 (목록에서 고른 펀드 크롤링) -----

    def on_fetch(self) -> None:
        selection = self.search_list.curselection()
        if not selection:
            messagebox.showwarning("선택 필요", "검색 결과 목록에서 펀드를 먼저 선택하세요.")
            return
        target = self._search_results[selection[0]]
        # Tkinter 위젯은 메인 스레드에서만 만져야 함("main thread is not in main
        # loop" 오류 실측) - 키워드를 여기서 읽어서 워커 스레드에 값으로 넘긴다
        keyword = self.name_var.get().strip() or target["name"]
        self._set_busy(True)
        self.status_var.set(
            f"'{target['name']}' 조회 중... (AUM 1년치까지 모으느라 1~2분 걸릴 수 있습니다)"
        )
        self.text.delete("1.0", "end")
        threading.Thread(target=self._run_query, args=(target, keyword), daemon=True).start()

    def _run_query(self, target: dict, keyword: str) -> None:
        try:
            # 검색은 사용자가 입력한 키워드로 하되, 선택은 ISIN 으로 정확히 특정
            fund = FundQuery(name=keyword, isin=target["isin"])
            dist_df = crawl_fund_distribution(fund, period="1년", headless=True)
            yield_summary = summarize_distribution_yield(dist_df)
            nav_df = crawl_fund_nav_history(fund, period="1년", headless=True)
            aum_summary = summarize_aum_change_on_distribution(nav_df)
            vs_dist_summary = summarize_aum_vs_distribution(dist_df, aum_summary)
            price_summary = summarize_price_change(nav_df)
            self._result_queue.put(
                ("ok", target, dist_df, yield_summary, nav_df, aum_summary, vs_dist_summary, price_summary)
            )
        except Exception as e:  # noqa: BLE001 - 백그라운드 스레드 예외를 GUI로 전달
            self._result_queue.put(("error", str(e)))

    # ----- 최근 검색 결과 다시 보기 -----

    def on_show_history(self) -> None:
        selection = self.history_list.curselection()
        if not selection:
            return
        entry = self._history[selection[0]]
        header = f"[최근 검색 결과] {entry['name']} — {entry['queried_at']} 조회 (저장본)"
        self.text.delete("1.0", "end")
        self.text.insert("1.0", f"{header}\n{'=' * len(header)}\n\n{entry['text']}")
        self.status_var.set(f"저장된 결과 표시: {entry['name']} ({entry['queried_at']})")

    def _refresh_history_list(self) -> None:
        self._history = _load_history()
        self.history_list.delete(0, "end")
        for entry in self._history:
            self.history_list.insert("end", f"[{entry['queried_at']}] {entry['name']}")

    # ----- 공통 -----

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.search_btn.config(state=state)
        self.fetch_btn.config(state=state)

    def _poll_queue(self) -> None:
        try:
            item = self._result_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self._set_busy(False)
            kind = item[0]
            if kind == "error":
                self.status_var.set("오류 발생")
                messagebox.showerror("오류", item[1])
            elif kind == "search_ok":
                _, keyword, results = item
                self._search_results = results
                self.search_list.delete(0, "end")
                for r in results:
                    self.search_list.insert("end", r["name"])
                if results:
                    self.status_var.set(
                        f"'{keyword}' 검색 결과 {len(results)}건 (ETF 제외) — 목록에서 펀드를 선택해 조회하세요."
                    )
                else:
                    self.status_var.set(f"'{keyword}' 검색 결과가 없습니다. 다른 키워드로 검색해보세요.")
            else:  # "ok" - 조회 완료
                _, target, dist_df, yield_summary, nav_df, aum_summary, vs_dist_summary, price_summary = item
                matched_name = self._extract_matched_name(dist_df, nav_df) or target["name"]
                result_text = self._build_result_text(
                    dist_df, yield_summary, nav_df, aum_summary, vs_dist_summary, price_summary, matched_name
                )
                self.text.delete("1.0", "end")
                self.text.insert("1.0", result_text)
                self.status_var.set(f"조회 완료: {matched_name} (결과가 '최근 검색 결과'에 저장됨)")
                _save_history_entry(matched_name, target["isin"], result_text)
                self._refresh_history_list()
        self.after(200, self._poll_queue)

    @staticmethod
    def _extract_matched_name(dist_df: pd.DataFrame, nav_df: pd.DataFrame) -> str:
        """crawl 함수들이 결과 맨 앞에 넣어주는 "조회된펀드명" 컬럼에서 실제 펀드명을 뽑는다."""
        for df in (dist_df, nav_df):
            if not df.empty and "조회된펀드명" in df.columns:
                return str(df["조회된펀드명"].iloc[0])
        return ""

    @staticmethod
    def _build_result_text(
        dist_df: pd.DataFrame,
        yield_summary: dict,
        nav_df: pd.DataFrame,
        aum_summary: dict,
        vs_dist_summary: dict,
        price_summary: dict,
        matched_name: str,
    ) -> str:
        # 표 안에도 "조회된펀드명" 컬럼이 매 행마다 반복되면 지저분하니, 맨 위
        # 한 줄에만 펀드명을 남기고 표에서는 그 컬럼을 뺀다.
        dist_display = dist_df.drop(columns=["조회된펀드명"], errors="ignore")
        nav_display = nav_df.drop(columns=["조회된펀드명"], errors="ignore")
        events_df = aum_summary["events"]

        lines: list[str] = []
        if matched_name:
            lines.append(f"조회된 펀드: {matched_name}")
            lines.append("")

        lines.append("=== 1년간 분배율 (세전/세후) ===")
        lines.append(f"분배 횟수: {yield_summary['count']}회")
        lines.append(f"평균 기준가(1,000좌 기준): {yield_summary['avg_price']:,.2f}원")
        lines.append(
            f"1,000좌당 분배금 합계: 세전 {yield_summary['total_dist_per_1000_pretax']:,.2f}원"
            f" / 세후 {yield_summary['total_dist_per_1000_posttax']:,.2f}원"
            f" (배당소득세 {KOREAN_DIVIDEND_TAX_RATE * 100:.1f}% 가정)"
        )
        lines.append(
            f"분배율: 세전 {yield_summary['ratio_pct_pretax']:.4f}%"
            f" / 세후 {yield_summary['ratio_pct_posttax']:.4f}%"
        )
        start_price = price_summary["start_price"]
        end_price = price_summary["end_price"]
        if start_price is not None:
            lines.append(
                f"1년간 기준가 변화: {start_price:,.2f}원 → {end_price:,.2f}원"
                f" ({price_summary['change']:+,.2f}원, {price_summary['change_pct']:+.4f}%)"
            )
        lines.append("")
        lines.append("--- 분배 이력 상세 ---")
        lines.append(dist_display.to_string(index=False) if not dist_display.empty else "(분배 이력 없음)")
        lines.append("")

        # 설정액(최초 모집금액, 고정값)과 순자산(현재 시가총액, 매일 변동)은 다른
        # 개념이라 헷갈리면 안 됨 - 아래 AUM 비교는 전부 "순자산" 기준.
        lines.append("=== 순자산(AUM) 1년 전 vs 지금 비교 ===")
        lines.append("(주의: '설정액'은 펀드 최초 모집금액으로 고정값 - 아래는 전부 '순자산' 기준)")
        start = aum_summary["period_start_aum_억원"]
        end = aum_summary["period_end_aum_억원"]
        if start is not None:
            lines.append(f"1년 전 순자산: {start:,.2f}억원")
            lines.append(f"현재 순자산: {end:,.2f}억원")
            lines.append(
                f"순자산 증감: {aum_summary['period_aum_change_억원']:+,.2f}억원"
                f" ({aum_summary['period_aum_change_pct']:+.4f}%)"
            )
            lines.append(f"그 중 분배로 빠져나간 금액(총분배유출액): {vs_dist_summary['total_distributed_억원']:,.2f}억원")
            excl = vs_dist_summary["aum_change_excl_distribution_억원"]
            excl_pct = vs_dist_summary["aum_change_excl_distribution_pct"]
            if excl is not None:
                sign = "플러스(+)" if excl >= 0 else "마이너스(-)"
                lines.append(
                    f"분배 제외 순수 운용손익: {excl:+,.2f}억원 ({excl_pct:+.4f}%) — {sign}"
                )
        else:
            lines.append("(AUM 데이터 없음)")
        lines.append("")
        lines.append("--- 분배일별 AUM 변화 상세 (조회기간 전체) ---")
        lines.append(
            events_df.to_string(index=False)
            if not events_df.empty
            else "(조회 범위 내 분배 이벤트 없음)"
        )
        lines.append("")

        # 1년치 일별 원자료는 250행 가까이 되니 다 나열하지 않고 앞/뒤 일부만 보여줌
        lines.append("--- 기준가 / 순자산 / 설정액 일별 원자료 (앞뒤 일부만 표시) ---")
        lines.append(_condense_table(nav_display, head=5, tail=5))

        return "\n".join(lines)


if __name__ == "__main__":
    App().mainloop()
