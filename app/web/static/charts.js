// ECharts - bon quy tac bat buoc (docs/09-api-ui.md muc 9.7):
//   1. Gia tri am luon to khac mau.
//   2. Co mau luon hien trong tooltip.
//   3. Khoang tin cay ve thanh sai so (o cac chart ty le vay lai/CLV).
//   4. Truc tien te rut gon, tooltip hien so day du.

function renderRomiChart(elId, rows) {
  const el = document.getElementById(elId);
  if (!el || !window.echarts) return;
  const chart = echarts.init(el);
  const sorted = [...rows].sort((a, b) => a.romi - b.romi);
  chart.setOption({
    grid: { left: 140, right: 20, top: 10, bottom: 10 },
    tooltip: {
      trigger: "axis", axisPointer: { type: "shadow" },
      formatter: (params) => {
        const p = params[0];
        const row = sorted[p.dataIndex];
        return `${row.campaign_name}<br/>ROMI: ${fmtRatio(row.romi)}<br/>` +
               `Lợi nhuận: ${fmtVnd(row.net_profit)}<br/>Cỡ mẫu: ${fmtCount(row._n_rows)}`;
      },
    },
    xAxis: { type: "value" },
    yAxis: { type: "category", data: sorted.map((r) => r.campaign_name) },
    series: [{
      type: "bar",
      data: sorted.map((r) => ({
        value: r.romi,
        itemStyle: { color: r.romi < 0 ? "#dc2626" : "#059669" },
      })),
    }],
  });
  return chart;
}

function renderFunnelChart(elId, stages) {
  const el = document.getElementById(elId);
  if (!el || !window.echarts) return;
  const chart = echarts.init(el);
  chart.setOption({
    tooltip: { formatter: (p) => `${p.name}: ${fmtCount(p.value)}` },
    series: [{
      type: "funnel",
      left: "10%", width: "80%",
      label: { formatter: (p) => `${p.name}\n${fmtCount(p.value)}` },
      data: stages.map((s) => ({ name: s.name, value: s.count })),
    }],
  });
  return chart;
}

function renderTrendChart(elId, rows) {
  const el = document.getElementById(elId);
  if (!el || !window.echarts) return;
  const chart = echarts.init(el);
  chart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["Hồ sơ", "Lợi nhuận ròng"] },
    xAxis: { type: "category", data: rows.map((r) => r.create_date) },
    yAxis: [
      { type: "value", name: "Hồ sơ" },
      { type: "value", name: "VND", position: "right" },
    ],
    series: [
      { name: "Hồ sơ", type: "bar", data: rows.map((r) => r.applications) },
      { name: "Lợi nhuận ròng", type: "line", yAxisIndex: 1,
        data: rows.map((r) => r.net_profit) },
    ],
  });
  return chart;
}
