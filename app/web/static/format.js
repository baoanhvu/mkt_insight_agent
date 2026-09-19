// Dinh dang so vi-VN - PHAI khop tuyet doi voi app/web/formatting.py, vi bo
// kiem chung numeric grounding (docs/08 muc 8.3) so khop CHINH chuoi nguoi
// dung nhin thay. Xem docs/09-api-ui.md muc 9.8.
//
// tests/e2e/test_format_parity.py doi chieu ham nay voi formatting.py tren
// cung mot bo gia tri de tranh troi lech.

function fmtVnd(v) {
  if (v === null || v === undefined) return "—"; // em dash
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(v) + " VND";
}

function fmtVndShort(v) {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(1).replace(".", ",") + " tỷ";
  if (a >= 1e6) return (v / 1e6).toFixed(1).replace(".", ",") + " tr";
  return fmtVnd(v);
}

function fmtPct(v, d) {
  if (v === null || v === undefined) return "—";
  d = d === undefined ? 1 : d;
  return (v * 100).toFixed(d).replace(".", ",") + "%";
}

function fmtRatio(v, d) {
  if (v === null || v === undefined) return "—";
  d = d === undefined ? 2 : d;
  return Number(v).toFixed(d).replace(".", ",");
}

function fmtCount(v) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(v);
}
