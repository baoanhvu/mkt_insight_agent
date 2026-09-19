"""Semantic layer: catalog chi so + compiler MetricRequest -> SQL.

Day la lop quan trong nhat de chong hallucination (xem docs/05-semantic-layer.md).
LLM khong bao gio viet SQL - no chon chi so tu `config/semantic/metrics.yml` va
`entities.yml`, phat ra mot MetricRequest, roi compiler o day sinh SQL da kiem
chung tu do.

QUY TAC RANH GIOI (ep boi import-linter, xem pyproject.toml):
  - Module nay KHONG duoc import app.llm hay app.agent.
  - Duoc phep import app.data (T04) de tu kiem chung catalog voi DB that
    (Catalog.validate_against_db), nhung KHONG bat buoc co DB moi dung duoc -
    catalog/compiler la ham thuan, chi validate_against_db moi can I/O.
"""
