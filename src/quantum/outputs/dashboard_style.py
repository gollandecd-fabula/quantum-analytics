from __future__ import annotations

DASHBOARD_CSS = r"""
:root {
  --bg: #eef2f6;
  --panel: #ffffff;
  --panel-soft: #f8fafc;
  --text: #17202a;
  --muted: #667085;
  --border: #d9e0e8;
  --navy: #172554;
  --navy-2: #25346b;
  --teal: #0f766e;
  --teal-soft: #dcfce7;
  --blue: #175cd3;
  --blue-soft: #dbeafe;
  --amber: #b54708;
  --amber-soft: #ffead5;
  --red: #b42318;
  --red-soft: #fee4e2;
  --green: #067647;
  --green-soft: #dcfce7;
  --slate-soft: #e4e7ec;
  --shadow: 0 1px 2px rgba(16,24,40,.05), 0 8px 24px rgba(16,24,40,.06);
  --radius: 14px;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-width: 320px;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, "Segoe UI", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.45;
}
button, input, select { font: inherit; }
button { cursor: pointer; }
button:focus-visible, input:focus-visible, select:focus-visible, [tabindex]:focus-visible {
  outline: 3px solid rgba(23,92,211,.28);
  outline-offset: 2px;
}
.skip-link {
  position: fixed; left: 12px; top: -60px; z-index: 120;
  padding: 10px 14px; border-radius: 8px; background: #fff; color: var(--navy);
  box-shadow: var(--shadow);
}
.skip-link:focus { top: 12px; }
.topbar {
  position: sticky; top: 0; z-index: 50;
  background: linear-gradient(135deg, #0f172a 0%, var(--navy) 70%, #1e3a5f 100%);
  color: #fff; box-shadow: 0 4px 18px rgba(15,23,42,.22);
}
.topbar-inner { max-width: 1560px; margin: 0 auto; padding: 18px 24px 0; }
.brand-row { display: flex; gap: 18px; align-items: flex-start; justify-content: space-between; }
.brand { min-width: 0; }
.eyebrow { margin: 0 0 5px; color: #93c5fd; font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
h1 { margin: 0; font-size: clamp(22px, 2.3vw, 32px); line-height: 1.1; }
.brand-meta { display: flex; flex-wrap: wrap; gap: 7px 14px; margin-top: 8px; color: #cbd5e1; font-size: 12px; }
.brand-meta span { min-width: 0; overflow-wrap: anywhere; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.button {
  border: 1px solid transparent; border-radius: 9px; padding: 8px 12px;
  font-weight: 700; line-height: 1.2; transition: transform .12s ease, background .12s ease;
}
.button:hover { transform: translateY(-1px); }
.button-primary { color: #fff; background: var(--blue); }
.button-secondary { color: #fff; background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.24); }
.button-light { color: var(--navy); background: #fff; border-color: var(--border); }
.button-quiet { color: #344054; background: var(--panel-soft); border-color: var(--border); }
.button-danger { color: var(--red); background: var(--red-soft); border-color: #fecdca; }
.button-small { padding: 6px 9px; font-size: 12px; }
.nav-tabs { display: flex; gap: 6px; margin-top: 16px; overflow-x: auto; scrollbar-width: thin; }
.nav-tab {
  flex: 0 0 auto; border: 0; border-radius: 9px 9px 0 0; padding: 11px 14px;
  background: transparent; color: #cbd5e1; font-weight: 700;
}
.nav-tab:hover { background: rgba(255,255,255,.08); color: #fff; }
.nav-tab[aria-selected="true"] { background: var(--bg); color: var(--navy); }
.nav-count { display: inline-flex; min-width: 20px; height: 20px; align-items: center; justify-content: center; margin-left: 5px; padding: 0 5px; border-radius: 999px; background: rgba(148,163,184,.22); font-size: 11px; }
.nav-tab[aria-selected="true"] .nav-count { background: var(--blue-soft); color: var(--blue); }
main { max-width: 1560px; margin: 0 auto; padding: 22px 24px 48px; }
.view[hidden] { display: none !important; }
.view-header { display: flex; gap: 16px; justify-content: space-between; align-items: flex-end; margin-bottom: 14px; }
.view-header h2 { margin: 0; font-size: 22px; }
.view-header p { margin: 4px 0 0; color: var(--muted); }
.panel {
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 18px; margin-bottom: 16px;
}
.panel-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 14px; }
.panel-header h3 { margin: 0; font-size: 17px; }
.panel-header p { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
.grid { display: grid; gap: 12px; }
.kpi-grid { grid-template-columns: repeat(4, minmax(180px, 1fr)); }
.summary-grid { grid-template-columns: minmax(0, 1.55fr) minmax(310px, .85fr); align-items: start; }
.status-grid { grid-template-columns: repeat(3, minmax(150px, 1fr)); }
.kpi-card, .status-card, .hash-card {
  border: 1px solid var(--border); border-radius: 12px; background: var(--panel); padding: 15px;
}
.kpi-card { min-height: 116px; position: relative; overflow: hidden; }
.kpi-card::after { content: ""; position: absolute; inset: auto -30px -42px auto; width: 100px; height: 100px; border-radius: 50%; background: rgba(148,163,184,.12); }
.kpi-label, .status-label, .hash-label { color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: .055em; text-transform: uppercase; }
.kpi-value { margin-top: 10px; font-size: clamp(24px, 2.2vw, 34px); font-weight: 800; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.kpi-note { margin-top: 7px; color: var(--muted); font-size: 12px; }
.kpi-negative { border-color: #fecdca; background: linear-gradient(145deg,#fff 0%,#fff5f4 100%); }
.kpi-negative .kpi-value { color: var(--red); }
.kpi-positive { border-color: #abefc6; background: linear-gradient(145deg,#fff 0%,#f0fdf4 100%); }
.kpi-positive .kpi-value { color: var(--green); }
.kpi-neutral .kpi-value { color: var(--navy); }
.status-value { margin-top: 8px; font-weight: 800; overflow-wrap: anywhere; }
.badge {
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
  border-radius: 999px; padding: 4px 8px; font-size: 11px; font-weight: 800; line-height: 1.15;
}
.badge-critical, .badge-bad { color: var(--red); background: var(--red-soft); }
.badge-high, .badge-warn { color: var(--amber); background: var(--amber-soft); }
.badge-medium, .badge-info { color: var(--blue); background: var(--blue-soft); }
.badge-low, .badge-neutral { color: #475467; background: var(--slate-soft); }
.badge-good { color: var(--green); background: var(--green-soft); }
.chart-list { display: grid; gap: 9px; }
.chart-row { display: grid; grid-template-columns: minmax(150px, 1fr) minmax(220px, 3fr) minmax(115px, .7fr); gap: 10px; align-items: center; }
.chart-label { font-size: 12px; color: #344054; }
.chart-track { height: 18px; border-radius: 999px; background: #edf1f5; overflow: hidden; }
.chart-fill { height: 100%; min-width: 2px; border-radius: 999px; }
.chart-income { background: var(--teal); }
.chart-expense { background: var(--amber); }
.chart-result-positive { background: var(--green); }
.chart-result-negative { background: var(--red); }
.chart-value { text-align: right; font-weight: 800; font-variant-numeric: tabular-nums; }
.text-negative { color: var(--red); }
.text-positive { color: var(--green); }
.chart-legend { display: flex; gap: 14px; flex-wrap: wrap; margin: 12px 0 0; color: var(--muted); font-size: 11px; }
.legend-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 5px; }
.rec-summary { display: grid; gap: 10px; }
.rec-summary-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 0; border-bottom: 1px solid #edf0f4; }
.rec-summary-row:last-child { border-bottom: 0; }
.rec-summary-button { border: 0; background: none; padding: 0; color: var(--blue); font-weight: 700; text-align: left; }
.filters {
  display: grid; grid-template-columns: minmax(210px, 1.5fr) repeat(4, minmax(145px, .7fr)) auto;
  gap: 10px; align-items: end;
}
.filter-field { display: grid; gap: 5px; }
.filter-field label { color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }
.filter-field input, .filter-field select {
  width: 100%; min-height: 39px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 9px; background: #fff; color: var(--text);
}
.filter-actions { display: flex; gap: 7px; align-items: center; }
.result-meta { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; justify-content: space-between; margin: 12px 0; color: var(--muted); font-size: 12px; }
.recommendation-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.recommendation-card {
  display: grid; gap: 12px; border: 1px solid var(--border); border-radius: 13px; background: #fff; padding: 15px;
}
.recommendation-card:hover { border-color: #b8c6da; box-shadow: 0 7px 18px rgba(16,24,40,.06); }
.rec-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.rec-badges { display: flex; flex-wrap: wrap; gap: 6px; }
.rec-title { margin: 0; font-size: 16px; line-height: 1.3; }
.rec-reason { color: #475467; min-height: 42px; }
.effect-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; }
.effect-cell { border-radius: 9px; background: var(--panel-soft); border: 1px solid #e6eaf0; padding: 9px; }
.effect-label { display: block; color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; }
.effect-value { display: block; margin-top: 5px; font-weight: 800; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.rec-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: var(--muted); font-size: 12px; }
.empty-state { border: 1px dashed #b8c2cf; border-radius: 12px; padding: 28px; text-align: center; color: var(--muted); background: var(--panel-soft); }
.table-wrap { overflow: auto; border: 1px solid var(--border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; min-width: 900px; }
th, td { padding: 10px 11px; border-bottom: 1px solid #e9edf2; text-align: left; vertical-align: top; }
th { position: sticky; top: 0; z-index: 2; background: #f4f7fa; color: #344054; font-size: 11px; text-transform: uppercase; letter-spacing: .035em; }
tbody tr:hover { background: #f8fafc; }
.metric-id { font-family: Consolas, "Courier New", monospace; font-size: 12px; }
.numeric { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.row-action { border: 0; background: transparent; color: var(--blue); font-weight: 700; padding: 0; }
.quality-grid { grid-template-columns: repeat(4, minmax(190px, 1fr)); }
.hash-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.hash-value { margin-top: 7px; font-family: Consolas, "Courier New", monospace; font-size: 12px; word-break: break-all; }
.hash-actions { margin-top: 9px; }
.list-clean { margin: 0; padding-left: 18px; }
.list-clean li { margin: 5px 0; overflow-wrap: anywhere; }
.definition-list { display: grid; grid-template-columns: minmax(180px,.6fr) 1fr; gap: 0; margin: 0; }
.definition-list dt, .definition-list dd { margin: 0; padding: 10px 0; border-bottom: 1px solid #edf0f4; }
.definition-list dt { color: var(--muted); font-weight: 700; }
.definition-list dd { overflow-wrap: anywhere; }
.drawer-overlay { position: fixed; inset: 0; z-index: 80; background: rgba(15,23,42,.46); opacity: 0; pointer-events: none; transition: opacity .18s ease; }
.drawer {
  position: fixed; z-index: 90; inset: 0 0 0 auto; width: min(620px, 94vw); background: #fff;
  transform: translateX(102%); transition: transform .2s ease; box-shadow: -12px 0 32px rgba(15,23,42,.2);
  display: grid; grid-template-rows: auto 1fr; overflow: hidden;
}
body.drawer-open { overflow: hidden; }
body.drawer-open .drawer-overlay { opacity: 1; pointer-events: auto; }
body.drawer-open .drawer { transform: translateX(0); }
.drawer-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 18px 20px; border-bottom: 1px solid var(--border); background: var(--panel-soft); }
.drawer-header h2 { margin: 0; font-size: 19px; }
.drawer-body { overflow-y: auto; padding: 20px; }
.drawer-section { margin-bottom: 20px; }
.drawer-section h3 { margin: 0 0 8px; font-size: 14px; color: var(--navy); }
.drawer-code { font-family: Consolas, "Courier New", monospace; font-size: 12px; word-break: break-all; padding: 10px; background: #f4f6f8; border-radius: 8px; }
.toast { position: fixed; z-index: 110; right: 20px; bottom: 20px; max-width: min(380px,calc(100vw - 40px)); padding: 11px 14px; border-radius: 10px; background: #101828; color: #fff; box-shadow: var(--shadow); opacity: 0; transform: translateY(10px); pointer-events: none; transition: .18s ease; }
.toast.show { opacity: 1; transform: translateY(0); }
.screen-reader { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 1100px) {
  .kpi-grid { grid-template-columns: repeat(2, minmax(180px,1fr)); }
  .summary-grid { grid-template-columns: 1fr; }
  .filters { grid-template-columns: repeat(3, minmax(150px,1fr)); }
  .filter-field:first-child { grid-column: span 2; }
  .recommendation-grid { grid-template-columns: 1fr; }
  .quality-grid { grid-template-columns: repeat(2,minmax(180px,1fr)); }
}
@media (max-width: 700px) {
  .topbar-inner { padding: 14px 12px 0; }
  .brand-row { display: grid; }
  .header-actions { justify-content: flex-start; }
  main { padding: 14px 10px 36px; }
  .nav-tab { padding: 10px 11px; }
  .view-header { align-items: flex-start; }
  .kpi-grid, .status-grid, .quality-grid, .hash-grid { grid-template-columns: 1fr 1fr; }
  .kpi-card { min-height: 100px; }
  .filters { grid-template-columns: 1fr 1fr; }
  .filter-field:first-child { grid-column: 1 / -1; }
  .filter-actions { grid-column: 1 / -1; }
  .chart-row { grid-template-columns: 1fr minmax(120px,1.7fr); }
  .chart-value { grid-column: 2; }
  .effect-grid { grid-template-columns: 1fr; }
  .panel { padding: 13px; border-radius: 11px; }
  .recommendation-card { padding: 13px; }
  .definition-list { grid-template-columns: 1fr; }
  .definition-list dt { padding-bottom: 2px; border-bottom: 0; }
  .definition-list dd { padding-top: 2px; }
}
@media (max-width: 430px) {
  .kpi-grid, .status-grid, .quality-grid, .hash-grid { grid-template-columns: 1fr; }
  .filters { grid-template-columns: 1fr; }
  .filter-field:first-child, .filter-actions { grid-column: 1; }
  .button { padding: 8px 10px; }
  .brand-meta { display: grid; gap: 4px; }
}
@media print {
  :root { --bg: #fff; }
  .topbar { position: static; background: #fff; color: #000; box-shadow: none; border-bottom: 2px solid #000; }
  .eyebrow, .brand-meta { color: #333; }
  .header-actions, .nav-tabs, .filters, .button, .drawer, .drawer-overlay, .toast { display: none !important; }
  main { max-width: none; padding: 12px; }
  .view[hidden] { display: block !important; page-break-before: always; }
  .panel, .kpi-card, .status-card, .recommendation-card { box-shadow: none; break-inside: avoid; }
  .recommendation-grid { grid-template-columns: 1fr; }
}
"""
