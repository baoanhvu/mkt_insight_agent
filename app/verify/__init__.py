"""Lop kiem chung L2 (numeric grounding), L3 (entity grounding), L4 (stats
guard). Xem docs/08-anti-hallucination.md va CLAUDE.md muc R1.

QUY TAC (R3, ep boi import-linter): module nay KHONG duoc import app.data,
app.llm, app.api - PHAI THUAN, khong I/O, khong goi LLM, de test khong can
DB/mang. Ngoai le duy nhat la doc `config/verify.yaml` (file cuc bo, giong
cach app.semantic.catalog doc metrics.yml) - khong phai vi pham quy tac tren.
"""
