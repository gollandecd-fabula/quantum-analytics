from __future__ import annotations

DASHBOARD_BODY = r"""
<a class="skip-link" href="#dashboard-main">Перейти к содержанию</a>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand-row">
      <div class="brand">
        <p class="eyebrow">HOME_LOCAL · OFFLINE</p>
        <h1>Quantum Analytics</h1>
        <div class="brand-meta">
          <span id="header-dataset"></span>
          <span id="header-generated"></span>
          <span id="header-source"></span>
          <span>Внешние библиотеки и сетевые запросы отсутствуют</span>
        </div>
      </div>
      <div class="header-actions" aria-label="Действия отчёта">
        <button class="button button-secondary" id="reload-button" type="button">Обновить</button>
        <button class="button button-secondary" id="print-button" type="button">Печать</button>
      </div>
    </div>
    <nav class="nav-tabs" aria-label="Разделы отчёта" role="tablist">
      <button class="nav-tab" role="tab" aria-selected="true" aria-controls="view-overview" id="tab-overview" data-view="overview">Обзор</button>
      <button class="nav-tab" role="tab" aria-selected="false" aria-controls="view-recommendations" id="tab-recommendations" data-view="recommendations">Рекомендации <span class="nav-count" id="nav-rec-count">0</span></button>
      <button class="nav-tab" role="tab" aria-selected="false" aria-controls="view-metrics" id="tab-metrics" data-view="metrics">Метрики <span class="nav-count" id="nav-metric-count">0</span></button>
      <button class="nav-tab" role="tab" aria-selected="false" aria-controls="view-quality" id="tab-quality" data-view="quality">Качество и контроль</button>
    </nav>
  </div>
</header>
<main id="dashboard-main" tabindex="-1">
  <section class="view" id="view-overview" role="tabpanel" aria-labelledby="tab-overview">
    <div class="view-header"><div><h2>Управленческий обзор</h2><p>Ключевые результаты, финансовая структура и приоритетные действия.</p></div></div>
    <div class="grid kpi-grid" id="kpi-grid"></div>
    <div class="grid summary-grid">
      <section class="panel" aria-labelledby="financial-title">
        <div class="panel-header"><div><h3 id="financial-title">Финансовая структура</h3><p>Суммы из source bridge и governed calculation. Расходы не интерпретируются как положительный результат.</p></div></div>
        <div class="chart-list" id="financial-chart"></div>
        <div class="chart-legend"><span><i class="legend-dot chart-income"></i>Доход</span><span><i class="legend-dot chart-expense"></i>Расход</span><span><i class="legend-dot chart-result-negative"></i>Отрицательный результат</span></div>
      </section>
      <section class="panel" aria-labelledby="priority-title">
        <div class="panel-header"><div><h3 id="priority-title">Приоритетные действия</h3><p>Наиболее срочные рекомендации текущего расчёта.</p></div><button class="button button-quiet button-small" type="button" data-go-view="recommendations">Все</button></div>
        <div class="rec-summary" id="priority-actions"></div>
      </section>
    </div>
    <section class="panel" aria-labelledby="status-title">
      <div class="panel-header"><div><h3 id="status-title">Состояние расчёта</h3><p>Admission, source bridge, reconciliation и публикационные ограничения.</p></div></div>
      <div class="grid status-grid" id="overview-status"></div>
    </section>
  </section>

  <section class="view" id="view-recommendations" role="tabpanel" aria-labelledby="tab-recommendations" hidden>
    <div class="view-header"><div><h2>Рекомендации</h2><p>Фильтрация, сортировка и детальный просмотр evidence/limitations.</p></div></div>
    <section class="panel" aria-label="Фильтры рекомендаций">
      <div class="filters">
        <div class="filter-field"><label for="rec-search">Поиск</label><input id="rec-search" type="search" autocomplete="off" placeholder="Действие, причина, evidence"></div>
        <div class="filter-field"><label for="severity">Срочность</label><select id="severity"><option value="">Все</option><option value="CRITICAL">Критическая</option><option value="HIGH">Высокая</option><option value="MEDIUM">Средняя</option><option value="LOW">Низкая</option></select></div>
        <div class="filter-field"><label for="priority">Цель</label><select id="priority"><option value="">Все</option><option value="PROFIT">Прибыль</option><option value="SUSTAINABLE_GROWTH">Устойчивый рост</option><option value="TURNOVER">Оборот</option></select></div>
        <div class="filter-field"><label for="category">Категория</label><select id="category"><option value="">Все</option></select></div>
        <div class="filter-field"><label for="rec-sort">Сортировка</label><select id="rec-sort"><option value="severity">По срочности</option><option value="priority">По цели</option><option value="category">По категории</option><option value="action">По действию</option></select></div>
        <div class="filter-actions"><button class="button button-quiet" id="rec-reset" type="button">Сбросить</button><button class="button button-light" id="rec-export" type="button">CSV</button></div>
      </div>
      <div class="result-meta"><span id="rec-result-count"></span><span>CSV защищён от spreadsheet-formula injection.</span></div>
      <div class="recommendation-grid" id="recommendation-grid"></div>
      <div class="empty-state" id="rec-empty" hidden>По текущим фильтрам рекомендации не найдены.</div>
    </section>
  </section>

  <section class="view" id="view-metrics" role="tabpanel" aria-labelledby="tab-metrics" hidden>
    <div class="view-header"><div><h2>Метрики</h2><p>Наблюдаемые и расчётные показатели без повторного вычисления.</p></div></div>
    <section class="panel" aria-label="Фильтры метрик">
      <div class="filters">
        <div class="filter-field"><label for="metric-search">Поиск</label><input id="metric-search" type="search" autocomplete="off" placeholder="ID, причина, источник"></div>
        <div class="filter-field"><label for="metric-scope">Контур</label><select id="metric-scope"><option value="">Все</option><option value="SOURCE">Источник</option><option value="CALCULATION">Расчёт</option></select></div>
        <div class="filter-field"><label for="metric-state">Состояние</label><select id="metric-state"><option value="">Все</option></select></div>
        <div class="filter-field"><label for="metric-unit">Единица</label><select id="metric-unit"><option value="">Все</option></select></div>
        <div class="filter-field"><label for="metric-sort">Сортировка</label><select id="metric-sort"><option value="id">По ID</option><option value="scope">По контуру</option><option value="state">По состоянию</option><option value="value-desc">По значению ↓</option><option value="value-asc">По значению ↑</option></select></div>
        <div class="filter-actions"><button class="button button-quiet" id="metric-reset" type="button">Сбросить</button></div>
      </div>
      <div class="result-meta"><span id="metric-result-count"></span><span>Клик по метрике открывает provenance и accounting boundary.</span></div>
      <div class="table-wrap"><table><thead><tr><th>Контур</th><th>Метрика</th><th>Состояние</th><th class="numeric">Значение</th><th>Единица</th><th>Валюта</th><th>Причина</th><th></th></tr></thead><tbody id="metric-table-body"></tbody></table></div>
      <div class="empty-state" id="metric-empty" hidden>По текущим фильтрам метрики не найдены.</div>
    </section>
  </section>

  <section class="view" id="view-quality" role="tabpanel" aria-labelledby="tab-quality" hidden>
    <div class="view-header"><div><h2>Качество, ограничения и происхождение</h2><p>Проверяемые состояния, reconciliation и SHA-256 связность результата.</p></div></div>
    <section class="panel"><div class="panel-header"><div><h3>Качество данных</h3><p>Admission и блокирующие причины.</p></div></div><div class="grid quality-grid" id="quality-grid"></div></section>
    <section class="panel"><div class="panel-header"><div><h3>Сверка</h3><p>Состояние reconciliation и зарегистрированные различия.</p></div></div><div id="reconciliation-panel"></div></section>
    <section class="panel"><div class="panel-header"><div><h3>Ограничения</h3><p>Явные ограничения текущего результата.</p></div></div><ul class="list-clean" id="limitations-list"></ul></section>
    <section class="panel"><div class="panel-header"><div><h3>Контрольные суммы</h3><p>Bundle, source, calculation и recommendation hashes.</p></div></div><div class="grid hash-grid" id="hash-grid"></div></section>
    <section class="panel"><div class="panel-header"><div><h3>Параметры и runtime</h3><p>Ссылки на профили, rounding policy и локальный runtime.</p></div></div><dl class="definition-list" id="parameters-list"></dl></section>
  </section>
</main>
<div class="drawer-overlay" id="drawer-overlay" aria-hidden="true"></div>
<aside class="drawer" id="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" aria-hidden="true">
  <div class="drawer-header"><div><p class="eyebrow">ДЕТАЛИ</p><h2 id="drawer-title">Элемент отчёта</h2></div><button class="button button-quiet" id="drawer-close" type="button" aria-label="Закрыть">Закрыть</button></div>
  <div class="drawer-body" id="drawer-body"></div>
</aside>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<noscript><div class="panel">Для интерактивного режима требуется JavaScript. Данные остаются локальными.</div></noscript>
"""
