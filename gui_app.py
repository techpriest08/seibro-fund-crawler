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
    FundQuery,
    crawl_fund_distribution,
    crawl_fund_nav_history,
    summarize_aum_change_on_distribution,
    summarize_distribution_yield,
)


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
        self.status_var.set(f"'{name}' 조회 중... (몇십 초 걸릴 수 있습니다)")
        self.text.delete("1.0", "end")
        threading.Thread(target=self._run_query, args=(name,), daemon=True).start()

    def _run_query(self, name: str) -> None:
        try:
            fund = FundQuery(name=name)
            dist_df = crawl_fund_distribution(fund, period="1년", headless=True)
            yield_summary = summarize_distribution_yield(dist_df)
            nav_df = crawl_fund_nav_history(fund, period="1개월", headless=True)
            aum_summary = summarize_aum_change_on_distribution(nav_df)
            self._result_queue.put(("ok", dist_df, yield_summary, nav_df, aum_summary))
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
                _, dist_df, yield_summary, nav_df, aum_summary = item
                matched_name = self._extract_matched_name(dist_df, nav_df)
                self.status_var.set(f"조회 완료: {matched_name}" if matched_name else "조회 완료")
                self._render_results(dist_df, yield_summary, nav_df, aum_summary, matched_name)
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
        aum_summary: pd.DataFrame,
        matched_name: str,
    ) -> None:
        # 표 안에도 "조회된펀드명" 컬럼이 매 행마다 반복되면 지저분하니, 맨 위
        # 한 줄에만 펀드명을 남기고 표에서는 그 컬럼을 뺀다.
        dist_display = dist_df.drop(columns=["조회된펀드명"], errors="ignore")
        nav_display = nav_df.drop(columns=["조회된펀드명"], errors="ignore")

        lines: list[str] = []
        if matched_name:
            lines.append(f"조회된 펀드: {matched_name}")
            lines.append("")
        lines.append(
            f"=== 1년간 분배 {yield_summary['count']}회, "
            f"1,000좌 금액 대비 분배율 합계: {yield_summary['total_ratio_pct']:.4f}% ==="
        )
        lines.append(dist_display.to_string(index=False) if not dist_display.empty else "(분배 이력 없음)")
        lines.append("")
        lines.append("=== 최근 기준가 / 순자산(AUM, 억원) ===")
        lines.append(nav_display.to_string(index=False) if not nav_display.empty else "(데이터 없음)")
        lines.append("")
        lines.append("=== 분배일 AUM 변화 (최근 조회 범위 내) ===")
        lines.append(
            aum_summary.to_string(index=False)
            if not aum_summary.empty
            else "(조회 범위 내 분배 이벤트 없음 - 조회기간을 넓혀야 할 수 있음)"
        )
        self.text.insert("1.0", "\n".join(lines))


if __name__ == "__main__":
    App().mainloop()
