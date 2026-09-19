"""Thong ke, CLV, phan khuc, pheu - HAM THUAN, khong I/O.

R3 (CLAUDE.md): module nay khong duoc import app.data, app.llm, app.api - ep
boi import-linter (pyproject.toml). Nho vay test o day khong can Postgres,
khong can mang: doc cua module la truyen vao gia tri da tinh san (danh sach
so, ty le, sample size), khong tu di truy van.

`config.py` la ngoai le duoc cho phep: doc `config/analytics.yaml` (file cuc
bo, khong phai DB/mang) de lay tham so phan khuc/CLV/hanh dong - dung nhu
`app/semantic/catalog.py` doc `config/semantic/*.yml`.
"""
