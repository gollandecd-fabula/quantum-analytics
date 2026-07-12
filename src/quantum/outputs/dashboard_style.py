from __future__ import annotations

DASHBOARD_CSS = r"""
:root {
  --bg: #edf2f7;
  --panel: #ffffff;
  --panel-soft: #f7f9fc;
  --text: #172033;
  --muted: #667085;
  --border: #d8e0ea;
  --navy: #172554;
  --navy-2: #263a73;
  --teal: #0f766e;
  --teal-soft: #dff7f1;
  --blue: #175cd3;
  --blue-soft: #e2edff;
  --amber: #b54708;
  --amber-soft: #fff0dc;
  --red: #b42318;
  --red-soft: #fee9e7;
  --green: #067647;
  --green-soft: #dcfce7;
  --violet: #6941c6;
  --violet-soft: #eee9ff;
  --cyan: #087e8b;
  --slate-soft: #e7ebf0;
  --chart-1: #175cd3;
  --chart-2: #0f766e;
  --chart-3: #b54708;
  --chart-4: #6941c6;
  --chart-5: #087e8b;
  --chart-6: #b42318;
  --chart-7: #475467;
  --chart-8: #397a2f;
  --chart-9: #9b5c13;
  --focus: rgba(23,92,211,.32);
  --shadow: 0 1px 2px rgba(16,24,40,.05), 0 10px 28px rgba(16,24,40,.07);
  --radius: 16px;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-width: 320px;
  background:
    radial-gradient(circle at 8% 3%, rgba(23,92,211,.08), transparent 25rem),
    radial-gradient(circle at 92% 12%, rgba(15,118,110,.08), transparent 28rem),
    var(--bg);
  color: var(--text);
  font-family: Inter, "Segoe UI", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.45;
}
button, input, select { font: inherit; }
button { cursor: pointer; }
button:focus-visible, input:focus-visible, select:focus-visible, [tabindex]:focus-visible {
  outline: 3px solid var(--focus);
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
  background: linear-gradient(125deg, #0b1224 0%, var(--navy) 58%, #164e63 100%);
  color: #fff; box-shadow: 0 5px 22px rgba(15,23,42,.24);
}
.topbar-inner { max-width: 1560px; margin: 0 auto; padding: 18px 24px 0; }
.brand-row { display: flex; gap: 18px; align-items: flex-start; justify-content: space-between; }
.brand { min-width: 0; }
.eyebrow, .section-kicker, .panel-kicker {
  margin: 0 0 5px; font-size: 10px; font-weight: 850; letter-spacing: .12em; text-transform: uppercase;
}
.eyebrow { color: #9dc5ff; }
.section-kicker { color: var(--blue); }
.panel-kicker { color: var(--violet); }
h1 { margin: 0; font-size: clamp(22px, 2.3vw, 32px); line-height: 1.1; }
.brand-meta { display: flex; flex-wrap: wrap; gap: 7px 14px; margin-top: 8px; color: #cbd5e1; font-size: 12px; }
.brand-meta span { min-width: 0; overflow-wrap: anywhere; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; align-items: center; }
.header-state { border: 1px solid rgba(255,255,255,.25); border-radius: 999px; padding: 7px 10px; background: rgba(255,255,255,.12); font-size: 11px; font-weight: 800; }
.header-state.state-critical { background: rgba(180,35,24,.48); }
.header-state.state-warning { background: rgba(181,71,8,.48); }
.header-state.state-good { background: rgba(6,118,71,.48); }
.button {
  border: 1px solid transparent; border-radius: 10px; padding: 9px 13px;
  font-weight: 750; line-height: 1.2; transition: transform .12s ease, background .12s ease, box-shadow .12s ease;
}
.button:hover { transform: translateY(-1px); box-shadow: 0 4px 10px rgba(16,24,40,.09); }
.button-primary { color: #fff; background: var(--blue); }
.button-secondary { color: #fff; background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.24); }
.button-light { color: var(--navy); background: #fff; border-color: rgba(255,255,255,.45); }
.button-quiet { color: #344054; background: var(--panel-soft); border-color: var(--border); }
.button-danger { color: var(--red); background: var(--red-soft); border-color: #fecdca; }
.button-small { padding: 6px 9px; font-size: 12px; }
.nav-tabs { display: flex; gap: 6px; margin-top: 16px; overflow-x: auto; scrollbar-width: thin; }
.nav-tab {
  flex: 0 0 auto; border: 0; border-radius: 10px 10px 0 0; padding: 11px 14px;
  background: transparent; color: #cbd5e1; font-weight: 750;
}
.nav-tab:hover { background: rgba(255,255,255,.08); color: #fff; }
.nav-tab[aria-selected="true"] { background: var(--bg); color: var(--navy); }
.nav-count { display: inline-flex; min-width: 20px; height: 20px; align-items: center; justify-content: center; margin-left: 5px; padding: 0 5px; border-radius: 999px; background: rgba(148,163,184,.22); font-size: 11px; }
.nav-tab[aria-selected="true"] .nav-count { background: var(--blue-soft); color: var(--blue); }
main { max-width: 1560px; margin: 0 auto; padding: 24px 24px 52px; }
.view[hidden] { display: none !important; }
.view-header { display: flex; gap: 16px; justify-content: space-between; align-items: flex-end; margin-bottom: 14px; }
.view-header h2 { margin: 0; font-size: clamp(22px, 2vw, 30px); }
.view-header p { margin: 5px 0 0; color: var(--muted); max-width: 920px; }
.panel {
  background: rgba(255,255,255,.97); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 18px; margin-bottom: 16px;
}
.panel-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 14px; }
.panel-header h3 { margin: 0; font-size: 17px; }
.panel-header p { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
.grid { display: grid; gap: 14px; }
.kpi-grid { grid-template-columns: repeat(4, minmax(180px, 1fr)); margin: 16px 0; }
.summary-grid { grid-template-columns: minmax(0, 1.5fr) minmax(330px, .8fr); align-items: stretch; }
.insight-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; }
.chart-panel-wide { grid-column: 1 / -1; }
.status-grid { grid-template-columns: repeat(3, minmax(150px, 1fr)); }
.decision-banner {
  display: flex; justify-content: space-between; align-items: center; gap: 20px;
  min-height: 158px; padding: 22px 24px; border: 1px solid #b8c7df; border-radius: 18px;
  background: linear-gradient(120deg, #102354 0%, #1f4d88 60%, #0f766e 125%); color: #fff;
  box-shadow: 0 16px 34px rgba(23,37,84,.18); overflow: hidden; position: relative;
}
.decision-banner::after { content: ""; position: absolute; width: 260px; height: 260px; right: -80px; bottom: -160px; border: 45px solid rgba(255,255,255,.08); border-radius: 50%; pointer-events: none; }
.decision-banner.state-critical { background: linear-gradient(120deg, #5f1714 0%, #a32a20 55%, #7c2d12 120%); border-color: #e7a8a2; }
.decision-banner.state-warning { background: linear-gradient(120deg, #6a310c 0%, #a54b0b 55%, #6941c6 135%); border-color: #e7b889; }
.decision-banner.state-good { background: linear-gradient(120deg, #064e3b 0%, #087f5b 58%, #175cd3 130%); border-color: #90d2bc; }
.decision-banner-copy { position: relative; z-index: 1; max-width: 940px; }
.decision-banner h3 { margin: 0; font-size: clamp(20px, 2vw, 29px); line-height: 1.18; }
.decision-banner p { margin: 8px 0 0; color: rgba(255,255,255,.82); }
.decision-banner-badges { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
.decision-banner .badge { border: 1px solid rgba(255,255,255,.25); background: rgba(255,255,255,.14); color: #fff; }
.decision-banner > .button { position: relative; z-index: 1; flex: 0 0 auto; }
.kpi-card, .status-card, .hash-card {
  border: 1px solid var(--border); border-radius: 14px; background: var(--panel); padding: 15px;
}
.kpi-card { min-height: 122px; position: relative; overflow: hidden; }
.kpi-card::after { content: ""; position: absolute; inset: auto -30px -42px auto; width: 105px; height: 105px; border-radius: 50%; background: rgba(148,163,184,.12); }
.kpi-card::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: var(--navy); }
.kpi-positive::before { background: var(--green); }
.kpi-negative::before { background: var(--red); }
.kpi-label, .status-label, .hash-label { color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: .055em; text-transform: uppercase; }
.kpi-value { margin-top: 10px; font-size: clamp(24px, 2.2vw, 34px); font-weight: 850; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.kpi-note { margin-top: 7px; color: var(--muted); font-size: 12px; }
.kpi-negative { border-color: #f0b4ae; background: linear-gradient(145deg,#fff 0%,#fff4f3 100%); }
.kpi-negative .kpi-value { color: var(--red); }
.kpi-positive { border-color: #a3dfbf; background: linear-gradient(145deg,#fff 0%,#f0fcf5 100%); }
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
.priority-panel, .readiness-panel { height: calc(100% - 16px); }
.rec-summary { display: grid; gap: 9px; }
.rec-summary-row { display: grid; grid-template-columns: auto minmax(0,1fr) auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid #edf0f4; }
.rec-summary-row:last-child { border-bottom: 0; }
.rec-rank { color: var(--muted); font-weight: 850; font-variant-numeric: tabular-nums; }
.rec-summary-button { border: 0; background: none; padding: 0; color: var(--blue); font-weight: 750; text-align: left; overflow-wrap: anywhere; }
.decision-readiness { display: grid; grid-template-columns: 132px minmax(0,1fr); gap: 18px; align-items: center; min-height: 196px; }
.readiness-ring { width: 126px; height: 126px; border-radius: 50%; display: grid; place-content: center; text-align: center; background: conic-gradient(var(--green) var(--readiness,0%), #e6ebf1 0); position: relative; }
.readiness-ring::after { content: ""; position: absolute; inset: 13px; border-radius: 50%; background: #fff; }
.readiness-ring strong, .readiness-ring span { position: relative; z-index: 1; }
.readiness-ring strong { font-size: 27px; color: var(--navy); }
.readiness-ring span { color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; }
.readiness-copy { min-width: 0; }
#decision-readiness-label { font-weight: 800; color: var(--navy); }
.progress-track { height: 9px; border-radius: 999px; background: #e7ecf2; overflow: hidden; margin: 9px 0 12px; }
.progress-fill { height: 100%; width: 0; background: linear-gradient(90deg,var(--blue),var(--green)); border-radius: inherit; }
.readiness-checks { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; color: var(--muted); font-size: 12px; }
.readiness-checks li { display: flex; gap: 7px; align-items: flex-start; }
.readiness-checks li::before { content: "○"; color: var(--amber); font-weight: 900; }
.readiness-checks li.check-pass::before { content: "✓"; color: var(--green); }
.chart-list { display: grid; gap: 9px; }
.diverging-scale { display: grid; grid-template-columns: 1fr auto 1fr; color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; margin: 0 130px 7px 190px; }
.diverging-scale span:first-child { text-align: left; }
.diverging-scale span:last-child { text-align: right; }
.chart-row { display: grid; grid-template-columns: minmax(160px, .9fr) minmax(260px, 3fr) minmax(125px, .7fr); gap: 12px; align-items: center; min-height: 31px; }
.chart-label { font-size: 12px; color: #344054; overflow-wrap: anywhere; }
.chart-track { position: relative; height: 22px; border-radius: 7px; background: linear-gradient(90deg,#f6e9e7 0 49.8%,#d7dee8 49.8% 50.2%,#e6f2f4 50.2% 100%); overflow: hidden; }
.chart-zero { position: absolute; top: 0; bottom: 0; left: 50%; width: 2px; background: #98a2b3; z-index: 2; }
.chart-fill { position: absolute; top: 3px; bottom: 3px; min-width: 2px; border-radius: 4px; }
.chart-fill-negative { right: 50%; }
.chart-fill-positive { left: 50%; }
.chart-income { background: var(--teal); }
.chart-expense { background: var(--amber); }
.chart-result-positive { background: var(--green); }
.chart-result-negative { background: var(--red); }
.chart-value { text-align: right; font-weight: 800; font-variant-numeric: tabular-nums; white-space: nowrap; }
.text-negative { color: var(--red); }
.text-positive { color: var(--green); }
.chart-legend { display: flex; gap: 14px; flex-wrap: wrap; margin: 13px 0 0; color: var(--muted); font-size: 11px; }
.legend-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 5px; }
.donut-layout { display: grid; grid-template-columns: minmax(150px,.75fr) minmax(210px,1.25fr); gap: 18px; align-items: center; min-height: 260px; }
.donut { width: min(220px,100%); aspect-ratio: 1; border-radius: 50%; margin: auto; position: relative; box-shadow: inset 0 0 0 1px rgba(16,24,40,.08); }
.donut::after { content: ""; position: absolute; inset: 24%; background: #fff; border-radius: 50%; box-shadow: 0 0 0 1px var(--border); }
.donut-center { position: absolute; inset: 30%; z-index: 1; display: grid; place-content: center; text-align: center; }
.donut-center strong { font-size: clamp(16px,2vw,24px); color: var(--navy); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.donut-center span { color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; }
.donut-legend { display: grid; gap: 7px; }
.donut-row { display: grid; grid-template-columns: 10px minmax(0,1fr) auto; gap: 8px; align-items: center; font-size: 12px; }
.donut-dot { width: 10px; height: 10px; border-radius: 3px; }
.donut-label { overflow-wrap: anywhere; color: #344054; }
.donut-value { text-align: right; font-weight: 800; font-variant-numeric: tabular-nums; white-space: nowrap; }
.cost-color-0 { background: var(--chart-1); }.cost-color-1 { background: var(--chart-2); }.cost-color-2 { background: var(--chart-3); }.cost-color-3 { background: var(--chart-4); }.cost-color-4 { background: var(--chart-5); }.cost-color-5 { background: var(--chart-6); }.cost-color-6 { background: var(--chart-7); }.cost-color-7 { background: var(--chart-8); }.cost-color-8 { background: var(--chart-9); }
.priority-chart { display: grid; gap: 13px; min-height: 220px; align-content: center; }
.priority-bar-row { display: grid; grid-template-columns: minmax(130px,.8fr) minmax(150px,2fr) 44px; gap: 10px; align-items: center; }
.priority-bar-label { font-size: 12px; font-weight: 750; color: #344054; }
.priority-bar-track { height: 18px; border-radius: 999px; background: #edf1f5; overflow: hidden; }
.priority-bar-fill { height: 100%; min-width: 3px; border-radius: inherit; }
.priority-profit { background: var(--blue); }.priority-growth { background: var(--teal); }.priority-turnover { background: var(--violet); }
.priority-bar-value { text-align: right; font-weight: 850; }
.history-chart { min-height: 220px; display: grid; align-items: stretch; }
.history-empty { display: grid; place-content: center; text-align: center; min-height: 220px; padding: 24px; border: 1px dashed #b8c2cf; border-radius: 13px; background: linear-gradient(145deg,#f9fbfd,#f3f6fa); }
.history-empty strong { color: var(--navy); font-size: 16px; }
.history-empty p { margin: 7px auto 0; color: var(--muted); max-width: 420px; }
.history-code { display: inline-flex; justify-self: center; margin-top: 10px; padding: 4px 8px; border-radius: 999px; background: var(--amber-soft); color: var(--amber); font-size: 10px; font-weight: 850; }
.history-svg { width: 100%; min-height: 220px; }
.history-grid-line { stroke: #d8e0e8; stroke-width: 1; }
.history-zero-line { stroke: #98a2b3; stroke-width: 1.5; stroke-dasharray: 5 4; }
.history-line { fill: none; stroke: var(--blue); stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; }
.history-point { fill: #fff; stroke: var(--blue); stroke-width: 3; }
.history-axis-label { fill: #667085; font-size: 11px; }
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
  display: grid; gap: 12px; border: 1px solid var(--border); border-left-width: 5px; border-radius: 13px; background: #fff; padding: 15px;
}
.recommendation-card.rec-critical { border-left-color: var(--red); }.recommendation-card.rec-high { border-left-color: var(--amber); }.recommendation-card.rec-medium { border-left-color: var(--blue); }.recommendation-card.rec-low { border-left-color: #98a2b3; }
.recommendation-card:hover { border-color: #b8c6da; border-left-color: inherit; box-shadow: 0 7px 18px rgba(16,24,40,.06); }
.rec-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.rec-badges { display: flex; flex-wrap: wrap; gap: 6px; }
.rec-title { margin: 0; font-size: 16px; line-height: 1.3; overflow-wrap: anywhere; }
.rec-reason { color: #475467; min-height: 42px; overflow-wrap: anywhere; }
.effect-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; }
.effect-cell { border-radius: 9px; background: var(--panel-soft); border: 1px solid #e6eaf0; padding: 9px; min-width: 0; }
.effect-label { display: block; color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; }
.effect-value { display: block; margin-top: 5px; font-weight: 800; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.rec-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: var(--muted); font-size: 12px; flex-wrap: wrap; }
.empty-state { border: 1px dashed #b8c2cf; border-radius: 12px; padding: 28px; text-align: center; color: var(--muted); background: var(--panel-soft); overflow-wrap: anywhere; }
.table-wrap { overflow: auto; border: 1px solid var(--border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; min-width: 900px; }
th, td { padding: 10px 11px; border-bottom: 1px solid #e9edf2; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
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
.drawer-header h2 { margin: 0; font-size: 19px; overflow-wrap: anywhere; }
.drawer-body { overflow-y: auto; padding: 20px; }
.drawer-section { margin-bottom: 20px; }
.drawer-section h3 { margin: 0 0 8px; font-size: 14px; color: var(--navy); }
.drawer-code { font-family: Consolas, "Courier New", monospace; font-size: 12px; word-break: break-all; padding: 10px; background: #f4f6f8; border-radius: 8px; white-space: pre-wrap; }
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
  .diverging-scale { margin-left: 170px; margin-right: 120px; }
}
@media (max-width: 760px) {
  .topbar-inner { padding: 14px 12px 0; }
  .brand-row { display: grid; }
  .header-actions { justify-content: flex-start; }
  main { padding: 14px 10px 36px; }
  .nav-tab { padding: 10px 11px; }
  .view-header { align-items: flex-start; }
  .decision-banner { display: grid; padding: 18px; }
  .decision-banner > .button { justify-self: start; }
  .kpi-grid, .status-grid, .quality-grid, .hash-grid, .insight-grid { grid-template-columns: 1fr 1fr; }
  .chart-panel-wide { grid-column: 1 / -1; }
  .kpi-card { min-height: 104px; }
  .filters { grid-template-columns: 1fr 1fr; }
  .filter-field:first-child { grid-column: 1 / -1; }
  .filter-actions { grid-column: 1 / -1; }
  .chart-row { grid-template-columns: 1fr minmax(150px,1.7fr); }
  .chart-value { grid-column: 2; }
  .diverging-scale { display: none; }
  .donut-layout { grid-template-columns: 1fr; }
  .donut { max-width: 190px; }
  .effect-grid { grid-template-columns: 1fr; }
  .panel { padding: 13px; border-radius: 12px; }
  .recommendation-card { padding: 13px; }
  .definition-list { grid-template-columns: 1fr; }
  .definition-list dt { padding-bottom: 2px; border-bottom: 0; }
  .definition-list dd { padding-top: 2px; }
}
@media (max-width: 520px) {
  .kpi-grid, .status-grid, .quality-grid, .hash-grid, .insight-grid { grid-template-columns: 1fr; }
  .filters { grid-template-columns: 1fr; }
  .filter-field:first-child, .filter-actions { grid-column: 1; }
  .button { padding: 8px 10px; }
  .brand-meta { display: grid; gap: 4px; }
  .decision-readiness { grid-template-columns: 1fr; justify-items: center; text-align: center; }
  .readiness-copy { width: 100%; text-align: left; }
  .chart-row { grid-template-columns: 1fr; gap: 5px; }
  .chart-value { grid-column: 1; text-align: left; }
  .priority-bar-row { grid-template-columns: 1fr 40px; }
  .priority-bar-track { grid-column: 1 / -1; grid-row: 2; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
@media (prefers-contrast: more) {
  :root { --border: #667085; --muted: #344054; }
  .panel, .kpi-card, .status-card, .recommendation-card, .hash-card { border-width: 2px; }
  .chart-zero { background: #000; }
}
@media print {
  :root { --bg: #fff; }
  body { background: #fff; }
  .topbar { position: static; background: #fff; color: #000; box-shadow: none; border-bottom: 2px solid #000; }
  .eyebrow, .brand-meta { color: #333; }
  .header-actions, .nav-tabs, .filters, .button, .drawer, .drawer-overlay, .toast { display: none !important; }
  main { max-width: none; padding: 12px; }
  .view[hidden] { display: block !important; page-break-before: always; }
  .panel, .kpi-card, .status-card, .recommendation-card, .decision-banner { box-shadow: none; break-inside: avoid; }
  .decision-banner { color: #000; background: #fff; border: 2px solid #000; }
  .recommendation-grid { grid-template-columns: 1fr; }
}
"""
