"use strict";

(() => {
  const FEATURE_ID = "bst-booking-tax-v0.21.0.16";
  if (window.__BST_BOOKING_TAX_FEATURE_ID__ === FEATURE_ID) return;
  window.__BST_BOOKING_TAX_FEATURE_ID__ = FEATURE_ID;
  let cutoffSortDirection = "desc";

  const math = window.BSTBookingValueMath;
  if (!math) {
    console.error("BST booking/tax feature math module is missing");
    return;
  }

  const isGerman = () =>
    String(state?.lang || "de").toLowerCase().startsWith("de");

  const labels = () => isGerman() ? {
    head: "Wert heute / Entwicklung",
    today: "Wert heute",
    performance: "Seit Buchung",
    cutoff: "Stichtag (Modell)",
    cutoffHint: "Leer = normale Haltefrist. Erwerbe am oder nach dem Stichtag werden nach diesem Modell nie Langzeit/steuerfrei.",
    normal: "Normale Haltefrist",
    never: "Nie steuerfrei",
    neverLong: "Nie Langzeit",
    modelTitle: "Stichtag-Simulation",
    notSet: "Nicht gesetzt",
    modelText: "Erwerbe vor dem Stichtag folgen weiter der eingestellten Haltefrist. Erwerbe am oder nach dem Stichtag bleiben dauerhaft im steuerpflichtigen Kurzzeit-Bereich dieses Modells.",
    loading: "Offene Lots werden geladen …",
    acquired: "Erworben",
    remaining: "Offen",
    status: "Status",
    saved: "Stichtag und Haltefrist gespeichert",
  } : {
    head: "Value today / performance",
    today: "Value today",
    performance: "Since booking",
    cutoff: "Cutoff date (model)",
    cutoffHint: "Empty = normal holding rule. Acquisitions on or after the cutoff never become long-term/tax-free in this model.",
    normal: "Normal holding rule",
    never: "Never tax-free",
    neverLong: "Never long-term",
    modelTitle: "Cutoff simulation",
    notSet: "Not set",
    modelText: "Acquisitions before the cutoff keep the configured holding rule. Acquisitions on or after the cutoff permanently remain in this model's taxable short-term bucket.",
    loading: "Loading open lots …",
    acquired: "Acquired",
    remaining: "Open",
    status: "Status",
    saved: "Cutoff and holding rule saved",
  };

  function entryById(id) {
    return (state?.data?.entries || []).find(
      (entry) => String(entry?.id) === String(id)
    ) || null;
  }

  function rowEntryId(root) {
    const button = root?.querySelector?.(
      ".edit-entry[data-id], .delete-entry[data-id], [data-id]"
    );
    return button?.dataset?.id || "";
  }

  function liveMetrics(entry) {
    return math.todayMetrics(
      entry,
      state?.data?.prices || {},
      typeof currentCurrency === "function" ? currentCurrency() : ""
    );
  }

  function metricHtml(entry) {
    const l = labels();
    const result = liveMetrics(entry);
    const value =
      result.currentValue == null
        ? "–"
        : fmtFiat(result.currentValue, result.currency);
    const percent =
      result.percent == null ? "–" : signedPercent(result.percent);
    const css =
      result.percent > 0 ? "positive" : result.percent < 0 ? "negative" : "";
    return `
      <div class="bst-current-value">
        <strong>${privateHtml(value)}</strong>
        <small class="${css}">${esc(l.performance)}: ${privateHtml(percent)}</small>
      </div>`;
  }

  function openLotByEntryId(id) {
    return (state?.data?.fifo?.open_lots || []).find(
      (lot) => String(lot?.entry_id || "") === String(id)
    ) || null;
  }

  function enhanceLedger() {
    if (!state?.data || state.data.locked) return;
    const l = labels();
    const table = document.querySelector("#tab-ledger .ledger-table-wrap table");

    if (table) {
      const headCells = [...table.querySelectorAll("thead tr th")];
      const fiatIndex = headCells.findIndex(
        (cell) => cell.dataset?.i18n === "fiatTotal"
      );

      table.querySelectorAll("tbody tr.ledger-entry-row").forEach((row) => {
        const id = rowEntryId(row);
        const entry = entryById(id);
        if (!entry) return;

        const actionCell = row.lastElementChild;
        const holdingCell = actionCell?.previousElementSibling || null;

        const lot = openLotByEntryId(id);
        if (
          holdingCell &&
          lot?.tax_cutoff_blocked &&
          !holdingCell.querySelector(".bst-cutoff-reason")
        ) {
          const reason = document.createElement("small");
          reason.className = "ledger-status-reason bst-cutoff-reason";
          reason.textContent = `${l.cutoff}: ${l.neverLong}`;
          holdingCell.appendChild(reason);
        }

        // Keep the original table width: add today's value below the existing
        // historical fiat total instead of creating another column.
        if (fiatIndex >= 0) {
          const fiatCell = row.children[fiatIndex];
          if (fiatCell && !fiatCell.querySelector(".bst-inline-current")) {
            const current = document.createElement("div");
            current.className = "bst-inline-current";
            current.innerHTML = metricHtml(entry);
            fiatCell.appendChild(current);
          }
        }
      });
    }

    document.querySelectorAll("#ledgerCards > *").forEach((card) => {
      const id = rowEntryId(card);
      const entry = entryById(id);
      const dl = card.querySelector("dl");
      if (!entry || !dl) return;

      const fiatRow = [...dl.children].find(
        (item) => item.querySelector("dt")?.textContent?.trim() ===
          (isGerman() ? "Fiat-Gesamtbetrag" : "Fiat total")
      );
      if (fiatRow && !fiatRow.querySelector(".bst-inline-current")) {
        const current = document.createElement("div");
        current.className = "bst-inline-current bst-mobile-current";
        current.innerHTML = metricHtml(entry);
        fiatRow.querySelector("dd")?.appendChild(current);
      }

      const lot = openLotByEntryId(id);
      if (lot?.tax_cutoff_blocked && !card.querySelector(".bst-card-cutoff")) {
        const marker = document.createElement("p");
        marker.className = "storage-note bst-card-cutoff";
        marker.textContent = `${l.cutoff}: ${l.neverLong}`;
        card.appendChild(marker);
      }
    });
  }

  function cutoffValue() {
    return String(state?.data?.tax_settings?.tax_cutoff_date || "");
  }

  function ensureCutoffField() {
    const form = document.querySelector("#taxForm");
    if (!form || !state?.data?.tax_settings) return null;

    let wrap = form.querySelector(".bst-cutoff-wrap");
    if (!wrap) {
      wrap = document.createElement("label");
      wrap.className = "wide bst-cutoff-wrap";
      wrap.innerHTML = `
        <span class="bst-cutoff-label"></span>
        <input id="bstTaxCutoff" name="bst_tax_cutoff" type="date">
        <small class="storage-note bst-cutoff-hint"></small>`;

      const note = form.querySelector('textarea[name="tax_note"]')?.closest("label");
      if (note) form.insertBefore(wrap, note);
      else {
        const button = form.querySelector("button[type='submit']");
        if (button) form.insertBefore(wrap, button);
        else form.appendChild(wrap);
      }
    }

    const l = labels();
    wrap.querySelector(".bst-cutoff-label").textContent = l.cutoff;
    wrap.querySelector(".bst-cutoff-hint").textContent = l.cutoffHint;
    const input = wrap.querySelector("#bstTaxCutoff");
    if (document.activeElement !== input) input.value = cutoffValue();

    if (form.dataset.bstTaxSubmitHook !== "1") {
      form.dataset.bstTaxSubmitHook = "1";
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();

        const fd = new FormData(form);
        const cutoff = String(fd.get("bst_tax_cutoff") || "");
        const marker = `[BST_TAX_CUTOFF:${cutoff}]`;
        const rawNote = String(fd.get("tax_note") || "");
        const cleanNote = rawNote.replace(
          /(?:\r?\n)?\[BST_TAX_CUTOFF:(?:\d{4}-\d{2}-\d{2})?\]\s*$/,
          ""
        ).trimEnd();
        const markedNote = cleanNote ? `${cleanNote}\n${marker}` : marker;
        const submit = form.querySelector("button[type='submit']");
        if (submit) submit.disabled = true;

        try {
          await service("set_tax_settings", {
            config_entry_id: state.entryId,
            long_term_days: Number(fd.get("long_term_days")),
            tax_note: markedNote,
          });
          toast(labels().saved);
          await loadData();
        } catch (error) {
          toast(errorText(error));
        } finally {
          if (submit) submit.disabled = false;
        }
      }, true);
    }

    return input;
  }

  function blockedLots() {
    return (state?.data?.fifo?.open_lots || []).filter(
      (lot) => Boolean(lot?.tax_cutoff_blocked)
    );
  }

  function openBtc(lots) {
    return lots.reduce(
      (sum, lot) => sum + Math.max(0, Number(lot?.remaining_btc || 0)),
      0
    );
  }

  function cutoffDateLabel(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return labels().notSet;
    const [year, month, day] = value.split("-");
    return isGerman() ? `${day}.${month}.${year}` : `${year}-${month}-${day}`;
  }

  function cutoffLotTime(lot) {
    const raw = lot?.timestamp || "";
    const parsed = Date.parse(raw);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function cutoffDateDisplay(value) {
    const parsed = Date.parse(value || "");
    if (!Number.isFinite(parsed)) return "–";
    const date = new Date(parsed);
    const year = String(date.getUTCFullYear()).padStart(4, "0");
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const day = String(date.getUTCDate()).padStart(2, "0");
    return `${year} ${month} ${day}`;
  }

  function sortedBlockedLots() {
    return [...blockedLots()].sort((a, b) => {
      const delta = cutoffLotTime(a) - cutoffLotTime(b);
      return cutoffSortDirection === "asc" ? delta : -delta;
    });
  }

  function ensureTaxModelPanel() {
    const form = document.querySelector("#taxForm");
    if (!form || !state?.data?.tax_settings) return;

    let host = document.querySelector("#bstTaxModelPanel");
    if (!host) {
      host = document.createElement("section");
      host.id = "bstTaxModelPanel";
      host.className = "panel bst-tax-model-panel";
      const split = form.closest(".split");
      if (split) split.insertAdjacentElement("afterend", host);
      else form.closest("section")?.insertAdjacentElement("afterend", host);
    }

    const l = labels();
    const cutoff = cutoffValue();
    const fifo = state.data.fifo || {};
    const total = Math.max(0, Number(fifo.total_btc || 0));
    const backendBlocked = Math.max(
      0,
      Number(fifo.tax_cutoff_blocked_btc || 0)
    );

    if (!cutoff) {
      host.innerHTML = `
        <div class="panel-head">
          <div><span class="kicker">TAX CUTOFF</span><h2>${esc(l.modelTitle)}</h2></div>
          <span class="badge">${esc(l.notSet)}</span>
        </div>
        <p class="storage-note">${esc(l.cutoffHint)}</p>`;
      return;
    }

    if (!dashboardSectionLoaded("ledger")) {
      host.innerHTML = `
        <div class="panel-head">
          <div><span class="kicker">TAX CUTOFF</span><h2>${esc(l.modelTitle)}</h2></div>
          <span class="badge">${esc(cutoffDateLabel(cutoff))}</span>
        </div>
        <p class="storage-note">${esc(l.loading)}</p>`;

      if (!host.dataset.bstLedgerRequest) {
        host.dataset.bstLedgerRequest = "1";
        void ensureDashboardSection("ledger").then(() => {
          delete host.dataset.bstLedgerRequest;
          ensureTaxModelPanel();
          enhanceLedger();
        });
      }
      return;
    }

    const blocked = sortedBlockedLots();
    const blockedBtc = blocked.length ? openBtc(blocked) : backendBlocked;
    const normalBtc = Math.max(0, total - blockedBtc);
    const sortArrow = cutoffSortDirection === "asc" ? "↑" : "↓";

    const rows = blocked.map((lot) => `
      <tr>
        <td>${esc(cutoffDateDisplay(lot.timestamp || ""))}</td>
        <td><span class="badge short_term">${esc(l.neverLong)}</span></td>
        <td class="bst-amount-cell">${privateHtml(fmtStack(Number(lot.remaining_btc || 0)))}</td>
      </tr>`).join("");

    host.innerHTML = `
      <div class="panel-head">
        <div>
          <span class="kicker">TAX CUTOFF</span>
          <h2>${esc(l.modelTitle)}</h2>
        </div>
        <span class="badge">${esc(cutoffDateLabel(cutoff))}</span>
      </div>
      <p class="storage-note">${esc(l.modelText)}</p>

      <div class="bst-tax-grid">
        <article class="bst-tax-card">
          <span class="bst-tax-card-label">${esc(l.normal)}</span>
          <strong class="bst-tax-card-value">${privateHtml(fmtStack(normalBtc))}</strong>
        </article>
        <article class="bst-tax-card">
          <span class="bst-tax-card-label">${esc(l.never)}</span>
          <strong class="bst-tax-card-value">${privateHtml(fmtStack(blockedBtc))}</strong>
        </article>
      </div>

      ${rows ? `
        <div class="table-wrap bst-cutoff-table">
          <table>
            <thead>
              <tr>
                <th>
                  <button type="button" class="bst-sort-acquired" title="${esc(l.acquired)}">
                    ${esc(l.acquired)} <span aria-hidden="true">${sortArrow}</span>
                  </button>
                </th>
                <th>${esc(l.status)}</th>
                <th>${esc(l.remaining)}</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : ""}
    `;

    const sortButton = host.querySelector(".bst-sort-acquired");
    if (sortButton) {
      sortButton.addEventListener("click", () => {
        cutoffSortDirection = cutoffSortDirection === "asc" ? "desc" : "asc";
        ensureTaxModelPanel();
      });
    }
  }

  function enhanceTax() {
    if (!state?.data || state.data.locked) return;
    ensureCutoffField();
    ensureTaxModelPanel();
  }

  function wrapRenderer(name, enhancement) {
    const original = window[name];
    if (typeof original !== "function" || original.__bstBookingTaxWrapped) return;
    const wrapped = function (...args) {
      const result = original.apply(this, args);
      queueMicrotask(enhancement);
      return result;
    };
    wrapped.__bstBookingTaxWrapped = true;
    window[name] = wrapped;
  }

  wrapRenderer("renderLedger", enhanceLedger);
  wrapRenderer("renderTax", enhanceTax);

  const style = document.createElement("style");
  style.textContent = `
    .bst-inline-current{margin-top:5px;padding-top:5px;border-top:1px solid color-mix(in srgb,var(--line) 65%,transparent)}
    .bst-current-value{display:flex;flex-direction:column;gap:3px;min-width:0}
    .bst-current-value strong{font-weight:650}
    .bst-current-value small{font-size:11px;line-height:1.25;white-space:nowrap}
    .bst-mobile-current{margin-top:6px}
    .bst-cutoff-wrap small{display:block;margin-top:6px;line-height:1.4}
    .bst-cutoff-reason,.bst-card-cutoff{color:var(--orange,#f7931a)}
    .bst-tax-model-panel{margin-top:16px}
    .bst-tax-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:18px 0}
    .bst-tax-card{display:flex;flex-direction:column;gap:12px;padding:16px;border:1px solid var(--line);border-radius:14px;background:var(--panel-soft,transparent);min-width:0}
    .bst-tax-card-label{display:block;color:var(--muted);font-size:12px;line-height:1.3}
    .bst-tax-card-value{display:block;font-size:19px;line-height:1.25;overflow-wrap:anywhere}
    .bst-cutoff-table{margin-top:14px}
    .bst-cutoff-table table{width:100%}
    .bst-cutoff-table th:nth-child(1),.bst-cutoff-table td:nth-child(1){width:34%}
    .bst-cutoff-table th:nth-child(2),.bst-cutoff-table td:nth-child(2){width:33%}
    .bst-cutoff-table th:nth-child(3),.bst-cutoff-table td:nth-child(3){width:33%;text-align:right}
    .bst-sort-acquired{display:inline-flex;align-items:center;gap:6px;padding:0;border:0;background:transparent;color:inherit;font:inherit;font-weight:inherit;cursor:pointer}
    .bst-sort-acquired:hover{text-decoration:underline}
    .bst-sort-acquired:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:3px;border-radius:4px}
    .bst-amount-cell code{white-space:nowrap}
    @media(max-width:760px){
      .bst-tax-grid{grid-template-columns:1fr}
      .bst-tax-model-panel{overflow:hidden}
      .bst-current-value small{white-space:normal}
    }
  `;
  document.head.appendChild(style);

  queueMicrotask(() => {
    if (state?.activeTab === "ledger") enhanceLedger();
    if (state?.activeTab === "tax") enhanceTax();
  });

  // Intentionally no DOM MutationObserver: render hooks are sufficient and avoid
  // recursive self-triggered DOM updates after vault unlock.
  console.info("Bitcoin Stack Tracker booking/tax feature active:", FEATURE_ID);
})();
