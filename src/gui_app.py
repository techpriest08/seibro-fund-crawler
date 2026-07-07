"""
SEIBro 펀드 분배금/AUM 조회 GUI.

exe로 더블클릭 실행하면 새 창이 뜨는 형태를 목표로 만든 Tkinter 프론트엔드.
크롤링 로직 자체는 seibro_fund_distribution.py 그대로 재사용하고, 여기서는
펀드명 입력창 + 조회 버튼 + 결과 표시만 담당한다. 브라우저는 headless=True 로
띄워서 사용자에게는 이 앱 창 하나만 보이게 한다.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd

from seibro_fund_distribution import (
    KOREAN_DIVIDEND_TAX_RATE,
    FundQuery,
    crawl_fund_distribution,
    crawl_fund_nav_history,
    summarize_aum_change_on_distribution,
    summarize_aum_vs_distribution,
    summarize_distribution_yield,
    summarize_price_change,
)


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
        self.geometry("950x650")

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="펀드명:").pack(side="left")
        self.name_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.name_var, width=45)
        entry.pack(side="left", padx=5)
        entry.bind("<Return>", lambda _e: self.on_query())
        self.query_btn = ttk.Button(top, text="조회", command=self.on_query)
        self.query_btn.pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="펀드명을 입력하고 조회를 누르세요.")
        ttk.Label(self, textvariable=self.status_var, padding=(10, 0)).pack(anchor="w")

        # 결과 표가 넓고 길어서 창을 키워도 다 안 보일 수 있음 - 세로/가로 스크롤 둘 다 추가
        text_frame = ttk.Frame(self, padding=10)
        text_frame.pack(fill="both", expand=True)
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.text = tk.Text(text_frame, wrap="none", font=("Consolas", 10))
        y_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        x_scroll = ttk.Scrollbar(text_frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        self._result_queue: queue.Queue = queue.Queue()
        self.after(200, self._poll_queue)

    def on_query(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("입력 필요", "펀드명을 입력하세요.")
            return
        self.query_btn.config(state="disabled")
        self.status_var.set(f"'{name}' 조회 중... (AUM 1년치까지 모으느라 1~2분 걸릴 수 있습니다)")
        self.text.delete("1.0", "end")
        threading.Thread(target=self._run_query, args=(name,), daemon=True).start()

    def _run_query(self, name: str) -> None:
        try:
            fund = FundQuery(name=name)
            dist_df = crawl_fund_distribution(fund, period="1년", headless=True)
            yield_summary = summarize_distribution_yield(dist_df)
            nav_df = crawl_fund_nav_history(fund, period="1년", headless=True)
            aum_summary = summarize_aum_change_on_distribution(nav_df)
            vs_dist_summary = summarize_aum_vs_distribution(dist_df, aum_summary)
            price_summary = summarize_price_change(nav_df)
            self._result_queue.put(
                ("ok", dist_df, yield_summary, nav_df, aum_summary, vs_dist_summary, price_summary)
            )
        except Exception as e:  # noqa: BLE001 - 백그라운드 스레드 예외를 GUI로 전달
            self._result_queue.put(("error", str(e)))

    def _poll_queue(self) -> None:
        try:
            item = self._result_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.query_btn.config(state="normal")
            if item[0] == "error":
                self.status_var.set("오류 발생")
                messagebox.showerror("오류", item[1])
            else:
                _, dist_df, yield_summary, nav_df, aum_summary, vs_dist_summary, price_summary = item
                matched_name = self._extract_matched_name(dist_df, nav_df)
                self.status_var.set(f"조회 완료: {matched_name}" if matched_name else "조회 완료")
                self._render_results(
                    dist_df, yield_summary, nav_df, aum_summary, vs_dist_summary, price_summary, matched_name
                )
        self.after(200, self._poll_queue)

    @staticmethod
    def _extract_matched_name(dist_df: pd.DataFrame, nav_df: pd.DataFrame) -> str:
        """
        펀드명은 부분 검색이라 검색어와 실제로 조회된 펀드가 다를 수 있다
        (예: "월지급"으로 검색하면 그 중 첫 번째 결과가 선택됨). crawl 함수들이
        결과 DataFrame 맨 앞에 넣어주는 "조회된펀드명" 컬럼에서 실제 펀드명을 뽑는다.
        """
        for df in (dist_df, nav_df):
            if not df.empty and "조회된펀드명" in df.columns:
                return str(df["조회된펀드명"].iloc[0])
        return ""

    def _render_results(
        self,
        dist_df: pd.DataFrame,
        yield_summary: dict,
        nav_df: pd.DataFrame,
        aum_summary: dict,
        vs_dist_summary: dict,
        price_summary: dict,
        matched_name: str,
    ) -> None:
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

        self.text.insert("1.0", "\n".join(lines))


if __name__ == "__main__":
    App().mainloop()
