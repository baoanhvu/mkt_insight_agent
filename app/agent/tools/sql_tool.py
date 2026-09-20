"""`sql_tool` - duong FREEFORM (docs/05-semantic-layer.md muc 5.6, T12).

Day la NOI DUY NHAT trong toan bo he thong LLM duoc phep sinh ra CAU TRUC
truy van (khong chi gia tri). Dieu do an toan duoc CHINH vi moi SQL sinh ra
PHAI di qua `SqlGuard.validate()` (7 cua, kiem tra tren cay cu phap) truoc
khi chay - nguyen tac "code tinh toan" van giu nguyen: con so cuoi cung luon
la ket qua cua mot truy van THAT SU da chay qua role chi-doc, khong phai do
LLM tu tinh.

CHU Y: cong cu nay da san sang va da kiem tra doc lap (xem
tests/test_sql_tool.py), nhung Orchestrator (T08/T10) VAN CHUA kich hoat
duong freeform (van tra ve FREEFORM_UNAVAILABLE) - noi day vao
`_build_evidence`/`answer()` doi hoi them tu vao ngan sach 2 luot goi LLM va
vong self-consistency (k=3, config/playbooks/freeform.yml), ngoai pham vi
cua T12 nhu mo ta trong docs/17 ("Xong khi" chi yeu cau test_sqlguard.py).
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app.contracts import ColumnSpec, Fact, LLMClient
from app.data.engines import get_engine_ro
from app.data.sqlguard import SqlGuard
from app.errors import SQLGuardError, SQLRepairExhausted
from app.prompts.loader import PromptLoader


class SqlTool:
    """`run(question, fact_id) -> Fact`. Vong sua loi toi da `max_repair_attempts`
    (config/playbooks/freeform.yml -> sql_guard.max_repair_attempts)."""

    def __init__(
        self, guard: SqlGuard, llm_client: LLMClient, prompts: PromptLoader,
        *, max_repair_attempts: int = 3,
    ) -> None:
        self.guard = guard
        self.llm_client = llm_client
        self.prompts = prompts
        self.max_repair_attempts = max_repair_attempts

    async def run(self, question: str, fact_id: str) -> Fact:
        error_feedback: str | None = None
        last_error: Exception | None = None
        rewritten_sql: str | None = None

        for _attempt in range(self.max_repair_attempts):
            sql = await self._generate_sql(question, error_feedback)
            try:
                guard_result = self.guard.validate(sql)
            except SQLGuardError as exc:
                last_error = exc
                error_feedback = str(exc)
                continue
            rewritten_sql = guard_result.sql_rewritten or sql
            break
        else:
            raise SQLRepairExhausted(
                f"không dựng được truy vấn hợp lệ sau {self.max_repair_attempts} lần thử: "
                f"{last_error}",
                question=question,
            )

        return self._execute(rewritten_sql, fact_id, question)

    async def _generate_sql(self, question: str, error_feedback: str | None) -> str:
        rendered = self.prompts.render("generate_sql", question=question)
        messages = list(rendered.messages)
        if error_feedback:
            messages.append({
                "role": "user",
                "content": f"Truy vấn trước bị chặn: {error_feedback}. Hãy sửa lại cho đúng.",
            })
        raw = await self.llm_client.complete(
            messages, temperature=rendered.params.get("temperature", 0.0),
            max_tokens=rendered.params.get("max_tokens", 400), response_format="json",
        )
        try:
            data = json.loads(raw)
            return str(data["sql"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise SQLRepairExhausted(f"LLM không trả về JSON hợp lệ: {exc}") from exc

    def _execute(self, sql: str, fact_id: str, title: str) -> Fact:
        with get_engine_ro().connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]

        for i, row in enumerate(rows, start=1):
            row["_ref"] = f"{fact_id}.r{i}"

        return Fact(
            fact_id=fact_id, title=title, query_id=f"{fact_id}-freeform", sql=sql,
            columns=[ColumnSpec(name=c, label=c, unit="text", format="") for c in columns],
            rows=rows, row_count=len(rows),
        )


__all__ = ["SqlTool"]
