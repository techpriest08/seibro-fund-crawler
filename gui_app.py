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

        self.text = tk.Text(self, wrap="none", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=10, pady=10)

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
                self.status_var.set("조회 완료")
                self._render_results(dist_df, yield_summary, nav_df, aum_summary)
        self.after(200, self._poll_queue)

    def _render_results(
        self,
        dist_df: pd.DataFrame,
        yield_summary: dict,
        nav_df: pd.DataFrame,
        aum_summary: pd.DataFrame,
    ) -> None:
        lines: list[str] = []
        lines.append(
            f"=== 1년간 분배 {yield_summary['count']}회, "
            f"1,000좌 금액 대비 분배율 합계: {yield_summary['total_ratio_pct']:.4f}% ==="
        )
        lines.append(dist_df.to_string(index=False) if not dist_df.empty else "(분배 이력 없음)")
        lines.append("")
        lines.append("=== 최근 기준가 / 순자산(AUM, 억원) ===")
        lines.append(nav_df.to_string(index=False) if not nav_df.empty else "(데이터 없음)")
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
