"use strict";

const BUILD_VERSION = "0.21.0.12";
const FRONTEND_BUILD = "021010";
const SATS_PER_BTC = 100_000_000;
const state = {
  lang: localStorage.getItem("bst_lang") || (String(navigator.language || "de").toLowerCase().startsWith("de") ? "de" : "en"),
  theme: localStorage.getItem("bst_theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"),
  unit: localStorage.getItem("bst_unit") || "BTC",
  chartMode: localStorage.getItem("bst_chart_mode") || "price",
  chartScaleLeft: localStorage.getItem("bst_chart_scale_left") || localStorage.getItem("bst_chart_scale") || "linear",
  chartScaleRight: localStorage.getItem("bst_chart_scale_right") || localStorage.getItem("bst_chart_scale") || "linear",
  chartCurrency: localStorage.getItem("bst_chart_currency") || "",
  overlayOpacity: Number(localStorage.getItem("bst_overlay_opacity") || 55),
  showMilestones: localStorage.getItem("bst_chart_milestones") !== "0",
  showHalvings: localStorage.getItem("bst_chart_halvings") !== "0",
  halvings: [], halvingInfo: null, halvingsEntryId: "", halvingsLoading: false, halvingsError: "",
  discreet: localStorage.getItem("bst_discreet_mode") === "1",
  portfolios: [], entryId: "", data: null,
  historyRange: (() => {
    const saved = localStorage.getItem("bst_history_range") || localStorage.getItem("bst_history_days") || "365";
    if (saved === "0" || saved === "7300") return "max";
    return ["1","week_start","7","month_start","30","90","ytd","365","1095","1825","3650","first_purchase","max"].includes(saved) ? saved : "365";
  })(),
  user: null, securityUsers: [], network: null, torRotation: null, leakTest: null,
  activeTab: localStorage.getItem("bst_active_tab") || "overview",
  ledgerPeriodFilter: localStorage.getItem("bst_ledger_period_filter") || "all",
  ledgerPage: 1, fifoPage: 1, ledgerPageSize: 25,
  csvImport: null, connectionInventory: null, connectionRefresh: null, pendingDeleteEntryId: "", editingEntryId: "",
  autoLockMinutes: (() => {
    const raw = localStorage.getItem("bst_auto_lock_minutes");
    const value = raw === null ? 15 : Number(raw);
    return [0,5,15,30,60,120].includes(value) ? value : 15;
  })(),
  lastActivityAt: Date.now(),
  dashboardSections: {summary:false,chart:false,ledger:false,fifo:false}
};
state.fiatFree = localStorage.getItem("bst_fiat_free_mode") === "1";
state.satsPerFiat = localStorage.getItem("bst_sats_per_fiat") !== "0";
state.backupHealth = null;
state.backupHealthLoading = false;
state.walletWatch = null;
state.walletWatchLoading = false;
state.walletWatchActivityPage = 1;
state.walletWatchActivityCategory = "all";
state.walletWatchActivityPageSize = (()=>{const v=Number(localStorage.getItem("bst_wallet_watch_page_size")||10);return [10,15,20,25].includes(v)?v:10;})();
state.walletWatchTxOverviews = {};
state.walletWatchOpenTxDetails = new Set();
state.walletWatchSettingsDirty = false;
state.marketAssessmentHistory = null;
state.marketAssessmentHistoryRange = localStorage.getItem("bst_market_assessment_history_range") || "3y";
state.marketAssessmentHistoryPriceOverlay = localStorage.getItem("bst_market_assessment_history_price_overlay") !== "0";
state.marketAssessmentHistoryPriceScale = localStorage.getItem("bst_market_assessment_history_price_scale") === "linear" ? "linear" : "log";
state.marketAssessmentHistoryPriceOpacity = (()=>{const value=Number(localStorage.getItem("bst_market_assessment_history_price_opacity")||55);return Number.isFinite(value)?Math.max(0,Math.min(100,value)):55;})();
state.marketAssessmentHistorySmoothing = (()=>{const value=Number(localStorage.getItem("bst_market_assessment_history_smoothing")||5);return [1,3,5,7,14,30].includes(value)?value:5;})();
state.chartMarketAssessmentHistory = null;
state.chartMarketAssessmentHistoryLoading = false;

let walletWatchStatusPollTimer = null;
let walletWatchStatusRefreshInFlight = false;
let networkPollTimer = null;
let marketAssessmentPollTimer = null;
let marketAssessmentRefreshInFlight = false;
let livePricePollTimer = null;
let livePriceRefreshInFlight = false;
let livePriceUpdatedAt = "";
let networkRefreshInFlight = false;
let connectionRefreshInFlight = false;
let intradayBootstrapInFlight = false;
let bitcoinNetworkRefreshAt = 0;
const intradayBootstrapLastAttempt = new Map();
let autoLockTimer = null;
let autoLockInFlight = false;
let coreActivitySyncTimer = null;
let coreActivitySyncAt = 0;
let viewportSettleTimer = null;
let derivedDataRevision = 0;
const derivedCache = new Map();
let sortedNumericPointCache = new WeakMap();
const chartTimestampCache = new Map();
let performanceRenderHandle = null;
let performanceRenderToken = 0;
let dashboardLoadRevision = 0;
const dashboardSectionInFlight = new Map();
let csvDuplicateCheckTimer = null;
let csvDuplicateCheckRevision = 0;

function cancelScheduledPerformanceSummary() {
  performanceRenderToken += 1;
  if (!performanceRenderHandle) return;
  const {kind,id} = performanceRenderHandle;
  performanceRenderHandle = null;
  if (kind === "idle" && typeof window.cancelIdleCallback === "function") window.cancelIdleCallback(id);
  else clearTimeout(id);
}
function invalidateDerivedCaches() {
  derivedDataRevision += 1;
  derivedCache.clear();
  sortedNumericPointCache = new WeakMap();
  cancelScheduledPerformanceSummary();
}
function derivedCacheKey(name, ...parts) {
  return `${derivedDataRevision}:${name}:${parts.map(part=>String(part ?? "")).join(":")}`;
}
function chartLedgerEntries() {
  if (Array.isArray(state.data?.chart_ledger_events)) return state.data.chart_ledger_events;
  return Array.isArray(state.data?.entries) ? state.data.entries : [];
}
function dashboardSectionLoaded(section) {
  return Boolean(state.dashboardSections?.[section]);
}
function clearLazySensitiveViews() {
  for (const selector of ["#ledgerBody", "#fifoBody"]) {
    const element=$(selector); if(element) element.innerHTML="";
  }
  for (const selector of ["#ledgerCards", "#fifoCards", "#fifoSaleSummary", "#returnAnalytics", "#dcaAnalytics", "#drawdownAnalytics", "#performanceSummary", "#stackingVelocityAnalytics", "#feeAnalytics", "#hodlBenchmarkAnalytics", "#holdingAgeDistribution"]) {
    const element=$(selector); if(element) element.innerHTML="";
  }
}
function resetDashboardSections() {
  dashboardLoadRevision += 1;
  state.dashboardSections = {summary:false,chart:false,ledger:false,fifo:false};
  cancelScheduledPerformanceSummary();
  clearLazySensitiveViews();
}
function mergeDashboardSection(section, payload) {
  if (!state.data || !payload || payload.locked) return;
  if (section === "chart") {
    state.data.chart_ledger_events = Array.isArray(payload.chart_ledger_events) ? payload.chart_ledger_events : [];
    state.data.history = {...(state.data.history || {}), ...(payload.history || {})};
  } else if (section === "ledger") {
    state.data.entries = Array.isArray(payload.entries) ? payload.entries : [];
    state.data.depot_entry_counts = payload.depot_entry_counts || state.data.depot_entry_counts || {};
    state.data.fifo = {...(state.data.fifo || {}), ...(payload.fifo || {})};
  } else if (section === "fifo") {
    state.data.fifo = {...(state.data.fifo || {}), ...(payload.fifo || {})};
  }
  state.dashboardSections[section] = true;
  invalidateDerivedCaches();
}
function renderLazyTabPlaceholder(tabName) {
  const message = tabName === "ledger" ? t("loadingLedger") : tabName === "tax" ? t("loadingFifo") : t("loadingData");
  if (tabName === "ledger") {
    const body=$("#ledgerBody"),cards=$("#ledgerCards"); if(body)body.innerHTML=""; if(cards)cards.innerHTML=`<p class="storage-note">${esc(message)}</p>`;
  } else if (tabName === "tax") {
    const body=$("#fifoBody"),cards=$("#fifoCards"); if(body)body.innerHTML=""; if(cards)cards.innerHTML=`<p class="storage-note">${esc(message)}</p>`;
  }
}
async function ensureDashboardSection(section) {
  if (!state.entryId || !state.data || state.data.locked || dashboardSectionLoaded(section)) return true;
  const requestedEntry = state.entryId;
  const requestedRevision = dashboardLoadRevision;
  const key = `${requestedRevision}:${requestedEntry}:${section}:${section === "chart" ? `${historyDaysForRange()}:${chartIntervalMinutesForRange()}` : "detail"}`;
  if (dashboardSectionInFlight.has(key)) return dashboardSectionInFlight.get(key);
  const request = (async()=>{
    try {
      let path=`api/dashboard?entry_id=${encodeURIComponent(requestedEntry)}&section=${encodeURIComponent(section)}`;
      if(section === "chart") path += `&history_days=${historyDaysForRange()}&history_interval=${chartIntervalMinutesForRange()}`;
      const payload=await api(path,{timeoutMs:section === "chart" ? 120000 : 60000});
      if(requestedEntry !== state.entryId || requestedRevision !== dashboardLoadRevision || !state.data || state.data.locked) return false;
      mergeDashboardSection(section,payload);
      if(section === "chart") void ensureIntradayHistory();
      if(state.activeTab === "overview" && section === "chart") renderOverview();
      else if(state.activeTab === "ledger" && section === "ledger") renderLedger();
      else if(state.activeTab === "tax" && dashboardSectionLoaded("fifo")) renderTax();
      else if(state.activeTab === "structure" && section === "chart") renderDepots();
      return true;
    } catch(error) {
      console.warn(`Bitcoin Stack lazy section ${section} failed`,errorText(error));
      if(requestedEntry === state.entryId) toast(`${t("loadingData")}: ${errorText(error)}`);
      return false;
    } finally {
      dashboardSectionInFlight.delete(key);
    }
  })();
  dashboardSectionInFlight.set(key,request);
  return request;
}
function ensureActiveTabData(tabName=state.activeTab) {
  if (!state.data || state.data.locked) return;
  if(tabName === "overview" || tabName === "structure") {
    void ensureDashboardSection("chart");
  } else if(tabName === "ledger") {
    if(!dashboardSectionLoaded("ledger")) renderLazyTabPlaceholder("ledger");
    void ensureDashboardSection("ledger");
  } else if(tabName === "tax") {
    if(!dashboardSectionLoaded("fifo")) renderLazyTabPlaceholder("tax");
    void ensureDashboardSection("fifo");
  }
}

function schedulePerformanceSummary(currency) {
  cancelScheduledPerformanceSummary();
  const token = performanceRenderToken;
  const run = () => {
    performanceRenderHandle = null;
    if (token !== performanceRenderToken || state.activeTab !== "overview" || !state.data || state.data.locked) return;
    renderPerformanceSummary(currency);
  };
  if (typeof window.requestIdleCallback === "function") {
    performanceRenderHandle = {kind:"idle",id:window.requestIdleCallback(run,{timeout:450})};
  } else {
    performanceRenderHandle = {kind:"timer",id:window.setTimeout(run,16)};
  }
}

function scheduleViewportSettledWork() {
  document.documentElement.classList.add("viewport-resizing");
  if (viewportSettleTimer !== null) clearTimeout(viewportSettleTimer);
  viewportSettleTimer = window.setTimeout(() => {
    viewportSettleTimer = null;
    document.documentElement.classList.remove("viewport-resizing");
    if (state.data && !state.data.locked && state.activeTab === "overview") renderChart();
    const csvModal = $("#csvImportModal");
    if (csvModal && !csvModal.classList.contains("hidden")) updateCsvHorizontalScroll();
  }, 220);
}
function scheduleChartRender() {
  scheduleViewportSettledWork();
}
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const errorText = error => {
  const candidate = error?.message ?? error?.body?.message ?? error?.body ?? error;
  if (typeof candidate === "string") return candidate;
  if (candidate && typeof candidate === "object") {
    for (const key of ["message","error","detail","text"]) {
      if (typeof candidate[key] === "string" && candidate[key]) return candidate[key];
    }
    try { return JSON.stringify(candidate); } catch {}
  }
  return String(candidate ?? "Unbekannter Fehler");
};

const I18N = {
  de: {
    overview:"Übersicht",ledger:"Buchungen",structure:"Depots & Ziele",tax:"Haltezeit",settings:"Export & Daten",security:"Zugriff & Verschlüsselung",logs:"App-Log",
    longTerm:"Langzeit",shortTerm:"Kurzzeit",unknown:"Ungeklärt",mixed:"Gemischt",nextMilestone:"Nächstes Ziel",dailyHistory:"Tageswerte",chartTitle:"Verlauf",
    chartView:"Ansicht",chartLegend:"Chart-Legende",leftAxis:"Linke Skala",rightAxis:"Rechte Skala",chartCurrency:"Chartwährung",btcPrice:"Bitcoin-Kurs",portfolioValue:"Portfoliowert",stackHistory:"Stack-Verlauf",profitLossHistory:"Gesamtgewinn/-verlust",pricePortfolioOverlay:"Kurs + Portfoliowert",priceStackOverlay:"Kurs + Stack",priceMarketAssessmentOverlay:"Kurs + Markteinschätzung",priceProfitLossOverlay:"Kurs + Gesamtgewinn/-verlust",portfolioProfitLossOverlay:"Portfoliowert + Gesamtgewinn/-verlust",costProfitLossOverlay:"Einstand + Buchgewinn/-verlust",openCostBasis:"Offener Einstand",unrealizedProfitLoss:"Buchgewinn/-verlust",period:"Zeitraum",allData:"Alle Daten",yearToDate:"Jahresanfang",weekToDate:"Seit Wochenbeginn",oneWeek:"1 Woche",monthToDate:"Seit Monatsbeginn",firstPurchaseRange:"Seit erstem Kauf",maxRange:"Max",scale:"Skala",linear:"Linear",logarithmic:"Logarithmisch",logUnavailable:"Für Gewinn-/Verlust-Ansichten ist nur die lineare Skala möglich.",marketScoreLinearOnly:"Die Markteinschätzung verwendet immer die feste lineare Skala 0–100.",overlayOpacity:"Overlay-Transparenz",today:"Heute",performance:"Performance im gewählten Zeitraum",performanceNote:"Portfoliowert wird cashflow-bereinigt: Käufe, Einnahmen, Verkäufe, Stack-Zugänge und Ausgaben werden als externe Cashflows neutralisiert; Transaktionsgebühren bleiben echte Performancekosten. Buchgewinn/-verlust bezieht sich auf den offenen Einstand. Gesamtgewinn/-verlust ist realisiert plus unrealisiert.",periodStart:"Start",periodEnd:"Ende",absoluteChange:"Absolut",percentageChange:"Prozent",bitcoinPerformance:"Bitcoin-Kurs",portfolioPerformance:"Portfoliowert",stackPerformance:"BTC-Stack",bookProfitLossPerformance:"Buchgewinn/-verlust",realizedProfitLossPerformance:"Realisierter Gewinn/Verlust",profitLossPerformance:"Gesamtgewinn/-verlust",comparisonUnavailable:"Für diesen Zeitraum sind noch nicht genug Werte vorhanden.",
    milestones:"Meilensteine",newEntry:"Neue Buchung",type:"Art",depot:"Depot",amount:"Menge",unit:"Einheit",currency:"Fiatwährung",pricePerBtc:"Preis pro BTC",fee:"Gebühr",includedFee:"Enthaltene Handelsgebühr",includedFeeEstimated:"geschätzt · im Endpreis enthalten",dateTime:"Datum / Uhrzeit",note:"Notiz",saveEntry:"Buchung speichern",date:"Datum",price:"Preis",holding:"Haltezeit",
    depots:"Depots",totalDepot:"Gesamtdepot",allDepotsCombined:"Alle Depots zusammen",totalStack:"Gesamtstack",totalValue:"Gesamtwert",rangePerformance:"Zeitraum-Performance",stackChange:"Stack-Veränderung",selectedRange:"Gewählter Zeitraum",add:"Hinzufügen",goals:"Stacking-Ziele",name:"Name",target:"Ziel",addGoal:"Ziel hinzufügen",goalStorage:"Jedes Ziel erzeugt zusätzliche lokale Verlaufswerte. Mehr Ziele bedeuten mehr Speicherbedarf.",remaining:"Fehlt",current:"Aktuell",targetValue:"Zielwert",
    overviewOnly:"Nur Übersicht",holdingDisclaimer:"Konfigurierbare Haltezeit- und FIFO-Übersicht. Abhängig vom anwendbaren Recht können Coins nach der gewählten Frist anders behandelt werden. Keine Steuerberatung und keine Steuererklärung.",holdingRule:"Haltezeit-Regel",days:"Tage bis Langzeit",customNote:"Eigene Notiz",saveRule:"Regel speichern",currentClassification:"Aktuelle Einordnung",saleOverview:"FIFO-Abgänge",sale:"Verkauf",purchase:"Kauf",income:"Einnahme",network_fee:"Transaktionsgebühr",stackEntry:"Bestand ohne Einstand",network:"Netzwerk",onchain:"On-Chain",lightning:"Lightning",holdingDays:"Haltetage",classification:"Einordnung",gain:"Realisierter Gewinn/Verlust",status:"Status",nextLong:"Nächster Langzeit-Zugang",
    historyAndExport:"Historie & Export",dailyDataCache:"TAGESDATEN-CACHE",enableHistory:"Historische Daten aktivieren",historyCacheHint:"Bereits gespeicherte Tageswerte bleiben beim Deaktivieren vollständig erhalten.",autoSync:"Täglich automatisch ergänzen",incrementalHint:"Nach dem ersten vollständigen Abruf werden nur neue Tage mit einem kleinen Überlappungsfenster geladen.",saveHistorySettings:"Historieneinstellungen speichern",torProxy:"Integrierter Tor-SOCKS5-Proxy",torProxyHint:"Tor wird mit dem Add-on installiert. Alle öffentlichen Live- und Historienabfragen laufen darüber; nur eine eigene private lokale Node wird direkt angesprochen.",torOnly:"Öffentliche Live- und Historienabfragen: nur Tor",historySettingsSaved:"Historieneinstellungen gespeichert",syncHistory:"Historische Tagesdaten synchronisieren",createExport:"CSV-/ZIP-Export erstellen",cachedValues:"Gespeicherte Tagesdatenpunkte",dataPoints:"Datenpunkte",historyCountHint:"Ein Datenpunkt entspricht einem gespeicherten Tageswert für die jeweilige Währung – nicht dem Bitcoin-Preis.",historySource:"Quelle",sourceCascade:"Quellenkette",lastSync:"Letzter Abgleich",historyDisabled:"Historie deaktiviert – lokaler Cache bleibt erhalten",historyEnabled:"Historie aktiviert",never:"Noch nie",
    salesSummary:"Verkäufe",expensesSummary:"Ausgaben",incomeSummary:"Einnahmen",networkFeesSummary:"Transaktionsgebühren",saleProceeds:"Verkaufserlöse",expenseValue:"Gegenwert der Ausgaben",incomeValue:"Wert der Einnahmen",realizedTotal:"Realisierter Gewinn gesamt",realizedCategory:"Realisierter Gewinn/Verlust",networkFeeValue:"Fiatwert der Transaktionsgebühren",networkFeeEffect:"FIFO-Effekt",historicalPriceWarning:"Ungewöhnlicher Kurs",historicalReference:"Historischer Referenzkurs",historicalReferenceUnavailable:"Historischer Referenzkurs für diesen Zeitpunkt nicht verfügbar – Plausibilitätsprüfung übersprungen.",enteredPrice:"Eingetragen",aboveReference:"über",belowReference:"unter",networkFeeAutoPrice:"Historischer BTC-Kurs für die Gebührenbewertung",support:"Unterstützen",v4vText:"Die Anwendung ist offen, lokal und Bitcoin-only. Wer einen Wert darin sieht, kann Sats zurückgeben.",stack:"Stack",expense:"Ausgabe",stackValue:"Stack-Wert",openBasis:"Offener Einstand",unrealized:"Buchgewinn/-verlust",realized:"Realisierter Gewinn/Verlust",noData:"Keine Daten vorhanden",allDepots:"Alle Depots",delete:"Löschen",deleteAllEntries:"Alle Buchungen löschen",allEntriesDeleted:"Alle Buchungen wurden gelöscht",deleteAllBackupConfirm:"Vor dem Löschen solltest du ein aktuelles verschlüsseltes Backup erstellen. Hast du ein Backup erstellt und möchtest du fortfahren?",deleteAllFinalConfirm:"LETZTE WARNUNG: Alle eingetragenen Buchungen werden dauerhaft gelöscht. Käufe, Verkäufe, Ausgaben und Stack-Einträge können danach nur aus einem Backup wiederhergestellt werden. Bist du wirklich sicher?",save:"Speichern",entrySaved:"Buchung gespeichert",ruleSaved:"Regel gespeichert",goalSaved:"Ziel gespeichert",exportCreated:"Export erstellt",syncDone:"Synchronisierung abgeschlossen",confirmDelete:"Wirklich löschen?",search:"Suchen",
    securityTitle:"Passwort-Tresor und Familienzugriff",securityIntro:"Nur ausgewählte Home-Assistant-Nutzer erhalten Zugriff. Bei Passwortverschlüsselung muss jeder freigegebene Nutzer den Tresor zusätzlich entsperren.",allowedUsers:"Erlaubte Nutzer",saveAccess:"Zugriff speichern",accessSaved:"Zugriffsliste gespeichert",entityPrivacy:"HA-Sensoren und Recorder",exposeSensors:"Sensible HA-Sensoren veröffentlichen",sensorWarning:"Unsicher: Normale HA-Nutzer können Entity-Zustände und Recorder-Historie sehen. Für Familienzugriff ausgeschaltet lassen.",saveSensorMode:"Sensormodus speichern",adminLimit:"Ein HA-Administrator mit Root- oder Dateisystemzugriff bleibt technisch vertrauenswürdig.",ownerOnly:"Nur der Portfolio-Eigentümer kann diese Einstellung ändern.",notOwner:"Du darfst das Portfolio verwenden, aber nicht seine Sicherheits- oder Historieneinstellungen ändern.",noAccess:"Für diesen Home-Assistant-Nutzer ist kein Bitcoin-Portfolio freigegeben.",sensorModeSaved:"Sensormodus gespeichert",
    vaultLocked:"Bitcoin-Tresor gesperrt",vaultSetupText:"Lege jetzt das Master-Passwort fest. Es wird nicht gespeichert.",vaultLockedText:"Dieses Portfolio ist mit einem Master-Passwort geschützt. Zusätzlich muss dein Home-Assistant-Nutzer freigegeben sein.",masterPassword:"Master-Passwort",unlockVault:"Tresor entsperren",lockVault:"Sperren",passwordLoss:"Das Passwort wird nicht gespeichert. Bei Verlust können verschlüsselte Daten und Backups nicht wiederhergestellt werden.",backupRestore:"Sicherung & Wiederherstellung",backupPassword:"Backup-Passwort",backupFile:"Backup-Datei",createBackup:"Verschlüsseltes Backup herunterladen",restoreBackup:"Backup importieren",restoreWarning:"Der Import ersetzt ausschließlich Buchungen, Depots, Ziele und lokale Historie des ausgewählten Portfolios. Installations-, Netzwerk- und Zugriffs-Einstellungen bleiben unverändert.",backupCreated:"Verschlüsseltes Backup erstellt",backupRestored:"Backup erfolgreich importiert",encryptionSettings:"Verschlüsselung",newMasterPassword:"Neues Master-Passwort",currentMasterPassword:"Aktuelles Master-Passwort",enableEncryption:"Verschlüsselung aktivieren",disableEncryption:"Verschlüsselung deaktivieren",changePassword:"Passwort ändern",encryptionChoice:"Ohne Verschlüsselung liegt das Kaufbuch lokal im Klartext. Die Nutzerfreigabe schützt dann nur innerhalb von Home Assistant.",encryptionMode:"Speichermodus",passwordProtected:"Passwortschutz",unlocked:"Entsperrt",privateMode:"Privater Sensormodus",confirmDisableEncryption:"Verschlüsselung wirklich deaktivieren? Das Kaufbuch wird danach lokal im Klartext gespeichert.",confirmRestore:"Backup wirklich importieren und die vorhandenen Portfolio-Daten ersetzen?",passwordChanged:"Master-Passwort geändert",encryptionChanged:"Verschlüsselungsmodus geändert",repeatPassword:"Passwort wiederholen",passwordMismatch:"Die Passwörter stimmen nicht überein.",
    appLog:"Technisches App-Log",refreshLogs:"Log aktualisieren",downloadLogs:"Log herunterladen",clearLogs:"Log leeren",confirmClearLogs:"App-Log wirklich leeren?",logCleared:"App-Log geleert",logPrivacy:"Das Log enthält nur technische Metadaten wie Route, Status, Laufzeit und Dienstname. Passwörter, Backups und Buchungsinhalte werden nicht protokolliert.",logLoading:"Log wird geladen …",logEmpty:"Noch keine Logeinträge vorhanden.",
    networkSecurity:"Tor-Killswitch & Leak-Test",runLeakTest:"Leak-Test starten",leakTestHint:"Der Test sendet keine direkte öffentliche Prüfverbindung. Die Zähler sind kumulativ seit dem Start: Die Integration kann verbotene Ziele bereits vor einem Socket blockieren; der Killswitch verwirft zusätzlich jedes Nicht-Tor-Paket im Gateway. Geblockt bedeutet: Es wurde nicht ungefiltert ins Internet übertragen.",onlyTorOnline:"Mit Tor verbunden",torConnecting:"Tor wird aufgebaut",torDisconnected:"Tor-Verbindung abgebrochen",torNotEstablished:"Tor noch nicht verbunden",torError:"Tor-Fehler",clearnetLeak:"Clearnet-Leak erkannt",localCacheOnly:"Nur lokale Daten und Cache verfügbar",protectionFault:"Killswitch-Schutzfehler",leakTestRunning:"Leak-Test läuft …",leakTestPassed:"Leak-Test bestanden: keine direkte Clearnet-Verbindung erkannt.",leakTestFailed:"Leak-Test fehlgeschlagen",killswitch:"Firewall-Killswitch",torVerified:"Tor-Ausgang bestätigt",torExitIp:"Tor-Exit-IP",remoteDns:"Remote-DNS / SafeSocks",blockedConnections:"Vom Killswitch geblockte Pakete",coreBlocked:"Von der Integration vor Verbindung blockiert",localConnections:"Erlaubte lokale Verbindungen",directClearnet:"Festgestellte direkte Clearnet-Sockets",noneAllowed:"0 erkannt",leakTargets:"Leak-Ziele",lastBlocked:"Letztes blockiertes Ziel",checkedAt:"Geprüft",appBuild:"App-Build",active:"Aktiv",inactive:"Inaktiv",yes:"Ja",no:"Nein",checking:"Prüfung läuft …",newTorIdentity:"Neue Tor-Verbindung",runLeakTest:"Neue Tor-IP & Leak-Test",automaticTorRotation:"Tor-Adresse automatisch wechseln",automaticTorRotationHint:"Fordert regelmäßig neue Tor-Circuits an. Eine andere Exit-IP kann nicht garantiert werden.",rotationInterval:"Wechselintervall",saveTorRotation:"Tor-Wechsel speichern",rotationSaved:"Tor-Wechsel gespeichert",rotatingTor:"Neue Tor-Verbindung wird aufgebaut …",torIdentityChanged:"Tor-Exit-IP wurde geändert",torIdentityRequested:"Neue Tor-Circuits wurden angefordert",previousExitIp:"Vorherige Tor-Exit-IP",nextRotation:"Nächster automatischer Wechsel",lastRotation:"Letzter Tor-Wechsel",ipUnchanged:"Tor verwendet weiterhin dieselbe Exit-IP",torControlNotReady:"Tor-Steuerung ist noch nicht bereit",torBootstrap:"Tor-Aufbau",discreetMode:"Diskret-Modus",hideSensitiveValues:"Finanzwerte mit •••• ausblenden",discreetModeHint:"Gilt nur für diesen Browser beziehungsweise dieses Gerät. Diagrammformen bleiben sichtbar, Zahlen werden verborgen.",chooseBackupFile:"Datei auswählen",noFileSelected:"Keine Datei ausgewählt",torProcessUnavailable:"Tor-Prozess und SOCKS5-Endpunkt sind nicht verfügbar",torStarting:"Tor wird noch aufgebaut",torLost:"Tor-SOCKS5-Verbindung wurde unterbrochen",torTimeout:"Tor-Prüfung hat zu lange gedauert"
  },
  en: {
    overview:"Overview",ledger:"Ledger",structure:"Depots & goals",tax:"Holding period",settings:"Export & data",security:"Access & encryption",logs:"App log",
    longTerm:"Long term",shortTerm:"Short term",unknown:"Unknown",mixed:"Mixed",nextMilestone:"Next goal",dailyHistory:"Daily values",chartTitle:"History",
    chartView:"View",chartLegend:"Chart legend",leftAxis:"Left scale",rightAxis:"Right scale",chartCurrency:"Chart currency",btcPrice:"Bitcoin price",portfolioValue:"Portfolio value",stackHistory:"Stack history",profitLossHistory:"Total profit/loss",pricePortfolioOverlay:"Price + portfolio",priceStackOverlay:"Price + stack",priceMarketAssessmentOverlay:"Price + market assessment",priceProfitLossOverlay:"Price + total profit/loss",portfolioProfitLossOverlay:"Portfolio + total profit/loss",costProfitLossOverlay:"Cost basis + unrealized profit/loss",openCostBasis:"Open cost basis",unrealizedProfitLoss:"Unrealized profit/loss",period:"Range",allData:"All data",yearToDate:"Year to date",weekToDate:"Since week start",oneWeek:"1 week",monthToDate:"Since month start",firstPurchaseRange:"Since first purchase",maxRange:"Max",scale:"Scale",linear:"Linear",logarithmic:"Logarithmic",logUnavailable:"Profit/loss views support the linear scale only.",marketScoreLinearOnly:"Market assessment always uses the fixed linear 0–100 scale.",overlayOpacity:"Overlay opacity",today:"Today",performance:"Performance for selected range",performanceNote:"Portfolio performance is cash-flow adjusted: purchases, income, sales, stack additions and expenses are neutralized as external cash flows; transaction fees remain real performance costs. Unrealized profit/loss is measured against open cost basis. Total profit/loss is realized plus unrealized.",periodStart:"Start",periodEnd:"End",absoluteChange:"Absolute",percentageChange:"Percent",bitcoinPerformance:"Bitcoin price",portfolioPerformance:"Portfolio value",stackPerformance:"BTC stack",bookProfitLossPerformance:"Unrealized profit/loss",realizedProfitLossPerformance:"Realized profit/loss",profitLossPerformance:"Total profit/loss",comparisonUnavailable:"Not enough values are available for this range.",
    milestones:"Milestones",newEntry:"New entry",type:"Type",depot:"Depot",amount:"Amount",unit:"Unit",currency:"Fiat currency",pricePerBtc:"Price per BTC",fee:"Fee",includedFee:"Included trading fee",includedFeeEstimated:"estimated · included in execution price",dateTime:"Date / time",note:"Note",saveEntry:"Save entry",date:"Date",price:"Price",holding:"Holding",
    depots:"Depots",totalDepot:"Total portfolio",allDepotsCombined:"All depots combined",totalStack:"Total stack",totalValue:"Total value",rangePerformance:"Range performance",stackChange:"Stack change",selectedRange:"Selected range",add:"Add",goals:"Stacking goals",name:"Name",target:"Target",addGoal:"Add goal",goalStorage:"Each goal creates additional local history values. More goals require more storage.",remaining:"Remaining",current:"Current",targetValue:"Target value",
    overviewOnly:"Overview only",holdingDisclaimer:"Configurable holding-period and FIFO overview. Depending on applicable law, coins older than the selected period may be treated differently. Not tax advice and not a tax return.",holdingRule:"Holding-period rule",days:"Days until long term",customNote:"Custom note",saveRule:"Save rule",currentClassification:"Current classification",saleOverview:"FIFO disposals",sale:"Sale",purchase:"Purchase",income:"Income",network_fee:"Transaction fee",stackEntry:"Stack without cost basis",network:"Network",onchain:"On-chain",lightning:"Lightning",holdingDays:"Holding days",classification:"Classification",gain:"Realized profit/loss",status:"Status",nextLong:"Next long-term lot",
    historyAndExport:"History & export",dailyDataCache:"DAILY DATA CACHE",enableHistory:"Enable historical data",historyCacheHint:"Previously cached daily values remain fully stored when disabled.",autoSync:"Automatically add new days",incrementalHint:"After the first complete download, only new days plus a small overlap are fetched.",saveHistorySettings:"Save history settings",torProxy:"Bundled Tor SOCKS5 proxy",torProxyHint:"Tor is installed with the app. All public live and historical requests use it; only an own private local node is contacted directly.",torOnly:"Public live and history requests: Tor only",historySettingsSaved:"History settings saved",syncHistory:"Synchronize historical daily data",createExport:"Create CSV/ZIP export",cachedValues:"Stored daily data points",dataPoints:"data points",historyCountHint:"One data point is one stored daily value for that currency – it is not the Bitcoin price.",historySource:"Source",sourceCascade:"Source cascade",lastSync:"Last synchronization",historyDisabled:"History disabled – local cache retained",historyEnabled:"History enabled",never:"Never",
    salesSummary:"Sales",expensesSummary:"Expenses",incomeSummary:"Income",networkFeesSummary:"Transaction fees",saleProceeds:"Sale proceeds",expenseValue:"Expense value",incomeValue:"Income value",realizedTotal:"Total realized profit/loss",realizedCategory:"Realized profit/loss",networkFeeValue:"Fiat value of transaction fees",networkFeeEffect:"FIFO effect",historicalPriceWarning:"Unusual price",historicalReference:"Historical reference price",historicalReferenceUnavailable:"Historical reference price is unavailable for this time – plausibility check skipped.",enteredPrice:"Entered",aboveReference:"above",belowReference:"below",networkFeeAutoPrice:"Historical BTC price used to value the fee",support:"Support",v4vText:"The app is open, local, and Bitcoin-only. Anyone who receives value can return value in sats.",stack:"Stack",expense:"Expense",stackValue:"Stack value",openBasis:"Open cost basis",unrealized:"Unrealized profit/loss",realized:"Realized profit/loss",noData:"No data available",allDepots:"All depots",delete:"Delete",deleteAllEntries:"Delete all entries",allEntriesDeleted:"All ledger entries were deleted",deleteAllBackupConfirm:"Create a current encrypted backup before deleting. Have you created a backup and do you want to continue?",deleteAllFinalConfirm:"FINAL WARNING: All entered ledger data will be permanently deleted. Purchases, sales, expenses, and stack entries can then only be restored from a backup. Are you absolutely sure?",save:"Save",entrySaved:"Entry saved",ruleSaved:"Rule saved",goalSaved:"Goal saved",exportCreated:"Export created",syncDone:"Synchronization finished",confirmDelete:"Delete this item?",search:"Search",
    securityTitle:"Password vault and family access",securityIntro:"Only selected Home Assistant users may access the portfolio. Password-protected portfolios must also be unlocked by each allowed user.",allowedUsers:"Allowed users",saveAccess:"Save access",accessSaved:"Access list saved",entityPrivacy:"HA sensors and recorder",exposeSensors:"Publish sensitive HA sensors",sensorWarning:"Unsafe: normal HA users may read entity states and recorder history. Leave this disabled for family access.",saveSensorMode:"Save sensor mode",adminLimit:"A Home Assistant administrator with root or filesystem access remains technically trusted.",ownerOnly:"Only the portfolio owner can change this setting.",notOwner:"You may use the portfolio but cannot change its security or history settings.",noAccess:"No Bitcoin portfolio is shared with this Home Assistant user.",sensorModeSaved:"Sensor mode saved",
    vaultLocked:"Bitcoin vault locked",vaultSetupText:"Set the master password now. It will not be stored.",vaultLockedText:"This portfolio is protected by a master password. Your Home Assistant user must also be allowed.",masterPassword:"Master password",unlockVault:"Unlock vault",lockVault:"Lock",passwordLoss:"The password is never stored. Lost passwords make encrypted data and backups unrecoverable.",backupRestore:"Backup & restore",backupPassword:"Backup password",backupFile:"Backup file",createBackup:"Download encrypted backup",restoreBackup:"Import backup",restoreWarning:"Import replaces only ledger entries, depots, goals, and local history in the selected portfolio. Installation, network, and access settings stay unchanged.",backupCreated:"Encrypted backup created",backupRestored:"Backup imported successfully",encryptionSettings:"Encryption",newMasterPassword:"New master password",currentMasterPassword:"Current master password",enableEncryption:"Enable encryption",disableEncryption:"Disable encryption",changePassword:"Change password",encryptionChoice:"Without encryption the local ledger is stored in plaintext. The allowlist then protects access only inside Home Assistant.",encryptionMode:"Storage mode",passwordProtected:"Password protection",unlocked:"Unlocked",privateMode:"Private sensor mode",confirmDisableEncryption:"Disable encryption? The ledger will then be stored locally in plaintext.",confirmRestore:"Import this backup and replace existing portfolio data?",passwordChanged:"Master password changed",encryptionChanged:"Encryption mode changed",repeatPassword:"Repeat password",passwordMismatch:"The passwords do not match.",
    appLog:"Technical app log",refreshLogs:"Refresh log",downloadLogs:"Download log",clearLogs:"Clear log",confirmClearLogs:"Clear the app log?",logCleared:"App log cleared",logPrivacy:"The log contains technical metadata only. Passwords, backups, and ledger content are never logged.",logLoading:"Loading log …",logEmpty:"No log entries yet.",
    networkSecurity:"Tor killswitch & leak test",runLeakTest:"Run leak test",leakTestHint:"The test sends no direct public probe. Counters are cumulative since startup: the integration can reject forbidden targets before opening a socket, while the killswitch drops any non-Tor packet in the gateway. Blocked means it was not sent unfiltered to the internet.",onlyTorOnline:"Connected through Tor",torConnecting:"Connecting to Tor",torDisconnected:"Tor connection lost",torNotEstablished:"Tor not connected yet",torError:"Tor error",clearnetLeak:"Clearnet leak detected",localCacheOnly:"Local data and cache only",protectionFault:"Killswitch protection fault",leakTestRunning:"Leak test running …",leakTestPassed:"Leak test passed: no direct Clearnet connection detected.",leakTestFailed:"Leak test failed",killswitch:"Firewall killswitch",torVerified:"Tor exit verified",torExitIp:"Tor exit IP",remoteDns:"Remote DNS / SafeSocks",blockedConnections:"Packets blocked by killswitch",coreBlocked:"Blocked by integration before connect",localConnections:"Allowed local connections",directClearnet:"Detected direct Clearnet sockets",noneAllowed:"0 detected",leakTargets:"Leak targets",lastBlocked:"Last blocked target",checkedAt:"Checked",appBuild:"App build",active:"Active",inactive:"Inactive",yes:"Yes",no:"No",checking:"Checking …",newTorIdentity:"New Tor connection",runLeakTest:"New Tor IP & leak test",automaticTorRotation:"Rotate Tor address automatically",automaticTorRotationHint:"Regularly requests new Tor circuits. A different exit IP cannot be guaranteed.",rotationInterval:"Rotation interval",saveTorRotation:"Save Tor rotation",rotationSaved:"Tor rotation saved",rotatingTor:"Building a new Tor connection …",torIdentityChanged:"Tor exit IP changed",torIdentityRequested:"New Tor circuits requested",previousExitIp:"Previous Tor exit IP",nextRotation:"Next automatic rotation",lastRotation:"Last Tor rotation",ipUnchanged:"Tor is still using the same exit IP",torControlNotReady:"Tor control is not ready yet",torBootstrap:"Tor bootstrap",discreetMode:"Discreet mode",hideSensitiveValues:"Hide financial values with ••••",discreetModeHint:"Applies only to this browser or device. Chart shapes remain visible while numbers are hidden.",chooseBackupFile:"Choose file",noFileSelected:"No file selected",torProcessUnavailable:"Tor process and SOCKS5 endpoint are unavailable",torStarting:"Tor is still starting",torLost:"Tor SOCKS5 connection was lost",torTimeout:"Tor check timed out"
  }
};

Object.assign(I18N.de, {
  trueReturn:"Echte Rendite",twr:"TWR",twrLong:"Zeitgewichtete Rendite",xirr:"XIRR p. a.",xirrLong:"Persönliche annualisierte Rendite",twrHint:"TWR zeigt die zeitgewichtete Rendite des gewählten Zeitraums und neutralisiert Ein- und Auszahlungen. XIRR ist deine geldgewichtete persönliche Rendite für denselben gewählten Zeitraum und wird auf ein Jahr hochgerechnet (365-Tage-Konvention).",xirrFxRequired:"Nicht berechenbar: Im Zeitraum liegen bewertete Cashflows in einer anderen Fiatwährung. Ohne FX-Kurs wird keine XIRR erfunden.",shortRangeXirr:"Bei kurzen Zeiträumen kann die annualisierte XIRR stark schwanken.",cashflowAdjusted:"Cashflow-bereinigt",unavailableReturn:"Nicht berechenbar",cashflowAdjustedChange:"Cashflow-bereinigt",netStackChange:"Netto-Veränderung",endingBalance:"Endbestand",currentProfitLoss:"Aktueller Stand",onOpenCostBasis:"Auf offenen Einstand",onInvestedCapital:"Auf investiertes Kapital",cumulativePurchaseOutlay:"Kumulierte Kaufaufwendungen",ambiguousReturn:"Mehrdeutig",
  dcaAnalysis:"DCA-Auswertung",purchasesInRange:"Käufe im Zeitraum",weightedAveragePrice:"Gewichteter Kaufkurs",averageSatsPerFiat:"Ø Sats pro Fiat",investedFiat:"Investiertes Fiat",feeRatio:"Gebührenquote",breakEvenPrice:"Break-even-Kurs",bestPurchase:"Bester Kauf",worstPurchase:"Schlechtester Kauf",acquiredStack:"Gekaufter Stack",differentCurrenciesOmitted:"Käufe in anderen Währungen wurden für Fiatkennzahlen nicht eingerechnet.",noPurchasesRange:"Keine passenden Käufe im gewählten Zeitraum.",
  drawdownAnalysis:"Drawdown im Zeitraum",periodHighDistance:"Abstand zum Zeitraumhoch",maximumDrawdown:"Maximaler Drawdown",bitcoinDrawdown:"Bitcoin",portfolioDrawdown:"Portfolio · TWR-bereinigt",peak:"Hoch",trough:"Tief",drawdownHint:"Der Portfolio-Drawdown basiert auf einem an jedem Cashflow getrennten TWR-Index. Die Berechnung nutzt die vollständige verfügbare Kursreihe; die Chart-Verdichtung beeinflusst die Kennzahl nicht.",
  fiatFreeMode:"Fiat-freier Modus",fiatFreeValues:"Nur BTC und Sats anzeigen",fiatFreeHint:"Blendet Fiatwerte in Übersichten, Buchungen und Charts aus. Die Eingabefelder für Käufe bleiben erhalten, damit Berechnungen möglich sind.",showSatsPerFiat:"Kurs als Sats pro Fiat anzeigen",showSatsPerFiatHint:"Zeigt optional, wie viele Sats eine Einheit der gewählten Währung kauft.",satsPerFiat:"Sats pro Fiat",fiatHidden:"Fiat ausgeblendet",
  backupHealth:"Backup-Gesundheit",lastEncryptedBackup:"Letztes verschlüsseltes Backup",lastRestoreTest:"Letzter Wiederherstellungstest",backupAgeLimit:"Backup-Warnung nach",restoreTestAgeLimit:"Test-Erinnerung nach",markRestoreTest:"Wiederherstellungstest als erledigt markieren",backupHealthy:"Backup aktuell",backupStale:"Backup fehlt oder ist zu alt",restoreTestDue:"Wiederherstellungstest ist fällig",restoreTestCurrent:"Wiederherstellungstest aktuell",backupHealthSaved:"Backup-Erinnerungen gespeichert",restoreTestMarked:"Wiederherstellungstest gespeichert",daysUnit:"Tagen",neverStoreSeed:"Seed-Wörter, Passphrases und private Schlüssel niemals in dieser App oder im Backup speichern.",backupCreatedHealth:"Backup-Zeitpunkt wurde in der Gesundheitsanzeige erfasst.",
  currentBtcPurchasingPower:"Aktueller Kurs",purchaseCount:"Anzahl Käufe",fiatSecured:"Kaufkraft in Sicherheit gebracht",lifetimePurchases:"Käufe insgesamt",finePriceSamples:"Adaptive Kurs-Samples",finePriceSamplesHint:"Einheitlich je Zeitraum: 1T 5 Min · seit Wochenbeginn/1W 30 Min · seit Monatsbeginn/30T 1 Std · 90T 4 Std · YTD/1J 12 Std (Tages-Fallback) · länger einheitlich verdichtete Tagesdaten",enableDiscreetMode:"Diskret-Modus einschalten",disableDiscreetMode:"Diskret-Modus ausschalten",openHaMenu:"Home-Assistant-Menü öffnen"
});
Object.assign(I18N.en, {
  trueReturn:"True return",twr:"TWR",twrLong:"Time-weighted return",xirr:"XIRR p.a.",xirrLong:"Personal annualized return",twrHint:"TWR is the time-weighted return for the selected period and neutralizes external cash flows. XIRR is your personal money-weighted return for the same selected period, annualized on a 365-day basis.",xirrFxRequired:"Unavailable: the range contains priced cash flows in another fiat currency. No XIRR is invented without an FX rate.",shortRangeXirr:"Annualized XIRR can be extremely volatile over short ranges.",cashflowAdjusted:"Cash-flow adjusted",unavailableReturn:"Unavailable",cashflowAdjustedChange:"Cash-flow adjusted",netStackChange:"Net change",endingBalance:"Ending balance",currentProfitLoss:"Current result",onOpenCostBasis:"On open cost basis",onInvestedCapital:"On invested capital",cumulativePurchaseOutlay:"Cumulative purchase outlay",ambiguousReturn:"Ambiguous",
  dcaAnalysis:"DCA analysis",purchasesInRange:"Purchases in range",weightedAveragePrice:"Weighted purchase price",averageSatsPerFiat:"Avg sats per fiat",investedFiat:"Invested fiat",feeRatio:"Fee ratio",breakEvenPrice:"Break-even price",bestPurchase:"Best purchase",worstPurchase:"Worst purchase",acquiredStack:"Purchased stack",differentCurrenciesOmitted:"Purchases in other currencies were excluded from fiat metrics.",noPurchasesRange:"No matching purchases in the selected range.",
  drawdownAnalysis:"Drawdown for selected range",periodHighDistance:"Distance from range high",maximumDrawdown:"Maximum drawdown",bitcoinDrawdown:"Bitcoin",portfolioDrawdown:"Portfolio · TWR adjusted",peak:"Peak",trough:"Trough",drawdownHint:"Portfolio drawdown uses a TWR index split at every cash flow. It is calculated from the full available price series, independent of display downsampling.",
  fiatFreeMode:"Fiat-free mode",fiatFreeValues:"Show BTC and sats only",fiatFreeHint:"Hides fiat values in summaries, ledger views, and charts. Purchase input fields remain available so calculations continue to work.",showSatsPerFiat:"Show price as sats per fiat",showSatsPerFiatHint:"Optionally shows how many sats one unit of the selected currency buys.",satsPerFiat:"Sats per fiat",fiatHidden:"Fiat hidden",
  backupHealth:"Backup health",lastEncryptedBackup:"Last encrypted backup",lastRestoreTest:"Last restore test",backupAgeLimit:"Backup warning after",restoreTestAgeLimit:"Restore-test reminder after",markRestoreTest:"Mark restore test complete",backupHealthy:"Backup is current",backupStale:"Backup is missing or stale",restoreTestDue:"Restore test is due",restoreTestCurrent:"Restore test is current",backupHealthSaved:"Backup reminders saved",restoreTestMarked:"Restore test recorded",daysUnit:"days",neverStoreSeed:"Never store seed words, passphrases, or private keys in this app or its backup.",backupCreatedHealth:"Backup creation time was recorded in backup health.",
  currentBtcPurchasingPower:"Current price",purchaseCount:"Purchase count",fiatSecured:"Purchasing power secured",lifetimePurchases:"Lifetime purchases",finePriceSamples:"Adaptive price samples",finePriceSamplesHint:"Uniform by range: 1d 5 min · week-to-date/1w 30 min · month-to-date/30d 1 h · 90d 4 h · YTD/1y 12 h (daily fallback) · longer uniformly compacted daily data",enableDiscreetMode:"Enable discreet mode",disableDiscreetMode:"Disable discreet mode",openHaMenu:"Open Home Assistant menu"
});
Object.assign(I18N.de,{refreshChartPrices:"Kurse aktualisieren",refreshingChartPrices:"Kurse für diesen Zeitraum werden über Tor neu geladen …",chartPricesRefreshed:"Kursdaten aktualisiert",chartPriceRefreshFailed:"Kursaktualisierung fehlgeschlagen",chartDailyFallback:"12-h-Kerzen nicht verfügbar · einheitliche Tagesdaten werden verwendet",exactCandles:"Exakte Chart-Kerzen",historySyncRunning:"Historische Tagesdaten werden über Tor synchronisiert …"});
Object.assign(I18N.de,{loadingData:"Daten werden geladen …",loadingLedger:"Buchungen werden bei Bedarf geladen …",loadingFifo:"FIFO-Zuordnungen werden bei Bedarf geladen …",loadingChart:"Chartdaten werden bei Bedarf geladen …"});
Object.assign(I18N.en,{loadingData:"Loading data …",loadingLedger:"Ledger entries are loaded on demand …",loadingFifo:"FIFO matches are loaded on demand …",loadingChart:"Chart data is loaded on demand …"});
Object.assign(I18N.en,{refreshChartPrices:"Refresh prices",refreshingChartPrices:"Reloading prices for this range through Tor …",chartPricesRefreshed:"Price data refreshed",chartPriceRefreshFailed:"Price refresh failed",chartDailyFallback:"12h candles unavailable · uniform daily data is being used",exactCandles:"Exact chart candles",historySyncRunning:"Synchronizing historical daily data through Tor …"});
Object.assign(I18N.de,{chartMilestones:"Meilensteine",chartHalvings:"Halvings",milestoneMarker:"Meilenstein",halvingMarker:"Bitcoin-Halving",blockHeight:"Blockhöhe",halvingLoadError:"Halving-Daten konnten nicht geladen werden"});
Object.assign(I18N.en,{chartMilestones:"Milestones",chartHalvings:"Halvings",milestoneMarker:"Milestone",halvingMarker:"Bitcoin halving",blockHeight:"Block height",halvingLoadError:"Halving data could not be loaded"});
Object.assign(I18N.de,{bitcoinNetwork:"BITCOIN NETZWERK",moscowTime:"Moscow Time",satsPerUsd:"sats / USD",halvingCountdown:"Halving-Countdown",estimatedHalving:"Halving geschätzt",nextHalvingBlock:"Nächster Halving-Block",networkDataSource:"Netzwerkdaten",monthlySavingsOverall:"Ø Sparrate gesamt",personalSavingsYear:"Persönliches Jahr",ongoing:"laufend",monthsCount:"Monate",fromFirstEntry:"seit erster Buchung",blocksLabel:"Blöcke",perMonth:"/ Monat",tenMinuteEstimate:"≈ 10 Min/Block"});
Object.assign(I18N.en,{bitcoinNetwork:"BITCOIN NETWORK",moscowTime:"Moscow Time",satsPerUsd:"sats / USD",halvingCountdown:"Halving countdown",estimatedHalving:"Estimated halving",nextHalvingBlock:"Next halving block",networkDataSource:"Network data",monthlySavingsOverall:"Avg monthly savings overall",personalSavingsYear:"Personal year",ongoing:"ongoing",monthsCount:"months",fromFirstEntry:"since first entry",blocksLabel:"blocks",perMonth:"/ month",tenMinuteEstimate:"≈ 10 min/block"});
Object.assign(I18N.de,{spentAmount:"Ausgegeben / Einstand",purchaseFees:"Kaufgebühren",purchaseOutlay:"Fiat-Aufwand inkl. Gebühren",openBasisHint:"Nur noch offene FIFO-Lots · Kaufgebühren anteilig enthalten",fiatSecuredHint:"Summe aus BTC-Menge × Kaufpreis aller Käufe · Gebühren nicht als Bitcoin-Kauf gezählt",technicalLogMemory:"Technisches Core-Log · maximal 500 Einträge · keine Passwörter oder Buchungsinhalte"});
Object.assign(I18N.en,{spentAmount:"Spent / cost basis",purchaseFees:"Purchase fees",purchaseOutlay:"Fiat outlay incl. fees",openBasisHint:"Open FIFO lots only · allocated purchase fees included",fiatSecuredHint:"Sum of BTC amount × purchase price for all purchases · fees are not counted as Bitcoin purchases",technicalLogMemory:"Technical Core log · maximum 500 entries · no passwords or ledger contents"});
Object.assign(I18N.de,{edit:"Bearbeiten",editEntry:"Buchung bearbeiten",cancelEdit:"Bearbeiten abbrechen",saveChanges:"Änderungen speichern",entryUpdated:"Buchung aktualisiert",consumed:"FIFO zugeordnet",holdingReasonConsumed:"Diese Buchung ist vollständig durch spätere Verkäufe oder Ausgaben verbraucht und deshalb kein offenes Lot mehr.",holdingReasonCurrency:"Ungeklärt: Kauf und Verkauf verwenden unterschiedliche Fiatwährungen; für den realisierten Gewinn fehlt eine FX-Umrechnung.",holdingReasonUnknownCost:"Ungeklärt: Die verwendeten BTC stammen ganz oder teilweise aus Bestand ohne bekannten Einstandskurs.",holdingReasonInsufficient:"Ungeklärt: Zum Buchungszeitpunkt war nicht genügend früherer BTC-Bestand im Depot vorhanden.",holdingReasonUnknown:"Ungeklärt: Die FIFO-/Haltezeit-Zuordnung konnte für diese Buchung nicht vollständig bestimmt werden.",editTypeLocked:"Die Buchungsart kann beim Bearbeiten korrigiert werden; FIFO wird danach vollständig neu geprüft."});
Object.assign(I18N.en,{edit:"Edit",editEntry:"Edit entry",cancelEdit:"Cancel editing",saveChanges:"Save changes",entryUpdated:"Entry updated",consumed:"FIFO assigned",holdingReasonConsumed:"This entry has been fully consumed by later sales or expenses and is therefore no longer an open lot.",holdingReasonCurrency:"Unresolved: purchase and sale use different fiat currencies; an FX conversion is missing for realized gain.",holdingReasonUnknownCost:"Unresolved: the BTC used comes wholly or partly from stack entries without a known cost basis.",holdingReasonInsufficient:"Unresolved: there was not enough earlier BTC in the depot at the transaction timestamp.",holdingReasonUnknown:"Unresolved: FIFO/holding-period assignment could not be determined completely for this entry.",editTypeLocked:"The entry type can be corrected while editing; FIFO is fully revalidated afterwards."});

Object.assign(I18N.de,{allLedgerEntries:"Alle Buchungen",currentYear:"Laufendes Jahr",ledgerPeriodFilter:"Buchungszeitraum",page:"Seite",of:"von",entriesShown:"Buchungen",historyAutomation:"Automatischer Historienabgleich",historyAutomationActive:"Aktiv",historyAutomationInactive:"Inaktiv",historyAutoRetryHint:"Vollständige Historie wird automatisch nachgeholt; bei Lücken erneuter Versuch alle 6 Std.",historyAutoLastAttempt:"Letzter Auto-Versuch"});
Object.assign(I18N.en,{allLedgerEntries:"All entries",currentYear:"Current year",ledgerPeriodFilter:"Ledger period",page:"Page",of:"of",entriesShown:"entries",historyAutomation:"Automatic history sync",historyAutomationActive:"Active",historyAutomationInactive:"Inactive",historyAutoRetryHint:"Full history is backfilled automatically; incomplete history retries every 6 h.",historyAutoLastAttempt:"Last automatic attempt"});

Object.assign(I18N.de, {
  csvImport:"CSV-Buchungen importieren",transactionFile:"Transaktionsdatei",chooseCsvFile:"CSV auswählen",targetDepot:"Zieldepot",checkCsv:"CSV prüfen",csvPrivacyHint:"Die Originaldatei wird nur im Arbeitsspeicher von Browser und Home Assistant Core gelesen und nie im Tor-Gateway gespeichert. Sensible Zusatzfelder wie Adresse, TXID, Order-ID, Memo oder Lightning-Rechnung sind beim Import standardmäßig abgewählt und werden nur nach aktiver Auswahl in die Notiz übernommen.",reviewCsv:"Erkannte Buchungen prüfen",selectValid:"Gültige auswählen",deselectAll:"Alle abwählen",sourceRow:"Quelle",cancel:"Abbrechen",confirmImport:"Ausgewählte Buchungen importieren",csvParsing:"CSV wird geprüft …",csvRecognized:"erkannt",csvSkipped:"übersprungen",csvNeedsReview:"zu prüfen",csvSelected:"ausgewählt",csvNoSelection:"Keine Buchung ausgewählt",csvImported:"Buchungen importiert",csvDuplicates:"Dubletten übersprungen",csvDuplicate:"Bereits vorhanden oder doppelt",csvReady:"Bereit",csvInvalid:"Bitte korrigieren",csvRemoved:"Entfernt",csvFileCleared:"Dateiauswahl wurde geleert",csvGenericWarning:"Unbekanntes Format: Bitte alle erkannten Werte besonders sorgfältig prüfen.",remove:"Entfernen",row:"Zeile",invalidImportRow:"Ausgewählte Zeile ist noch unvollständig oder ungültig",csvPriceRequired:"Preis muss größer als 0 sein",csvAmountRequired:"BTC-Menge muss größer als 0 sein",csvDateRequired:"Datum ist ungültig",csvCurrencyRequired:"Währung fehlt",csvFeeInvalid:"Gebühr darf nicht negativ sein",csvReviewHint:"Alle Werte können vor dem Speichern geändert werden. Nicht ausgewählte Zeilen werden verworfen. Zusatzfelder bleiben aus, bis du sie über der Tabelle auswählst.",optionalFieldsTitle:"Zusätzliche CSV-Felder in die Notiz übernehmen",optionalFieldsHint:"Standardmäßig ist alles abgewählt. Ausgewählte Werte werden nur an die Notiz der jeweiligen Buchung angehängt.",optionalFieldsClear:"Alle Zusatzfelder abwählen",optionalFieldOrderId:"Order-ID",optionalFieldTransactionId:"Transaktions-ID / TXID",optionalFieldAddress:"Adresse",optionalFieldLnInvoice:"Lightning-Rechnung",optionalFieldMemo:"Memo / Notiz aus CSV",optionalFieldTransactionType:"Transaktionsart",optionalFieldExchange:"Börse / Anbieter",optionalFieldTradeGroup:"Trade-Gruppe",optionalFieldsSelected:"Zusatzfelder in Notiz"
});
Object.assign(I18N.en, {
  csvImport:"Import CSV transactions",transactionFile:"Transaction file",chooseCsvFile:"Choose CSV",targetDepot:"Target depot",checkCsv:"Review CSV",csvPrivacyHint:"The original file is read only in browser and Home Assistant Core memory and is never stored by the Tor gateway. Sensitive optional fields such as address, TXID, order ID, memo, or Lightning invoice are disabled by default and are added to the note only after active selection.",reviewCsv:"Review detected transactions",selectValid:"Select valid",deselectAll:"Deselect all",sourceRow:"Source",cancel:"Cancel",confirmImport:"Import selected transactions",csvParsing:"Reviewing CSV …",csvRecognized:"recognized",csvSkipped:"skipped",csvNeedsReview:"need review",csvSelected:"selected",csvNoSelection:"No transaction selected",csvImported:"transactions imported",csvDuplicates:"duplicates skipped",csvDuplicate:"Already present or duplicated",csvReady:"Ready",csvInvalid:"Please correct",csvRemoved:"Removed",csvFileCleared:"File selection was cleared",csvGenericWarning:"Unknown format: review every detected value carefully.",remove:"Remove",row:"Row",invalidImportRow:"A selected row is incomplete or invalid",csvPriceRequired:"Price must be greater than 0",csvAmountRequired:"BTC amount must be greater than 0",csvDateRequired:"Date is invalid",csvCurrencyRequired:"Currency is missing",csvFeeInvalid:"Fee must not be negative",csvReviewHint:"Every value can be changed before saving. Unselected rows are discarded. Optional source fields remain off until you select them above the table.",optionalFieldsTitle:"Add optional CSV fields to the note",optionalFieldsHint:"Everything is disabled by default. Selected values are appended only to the note of the matching transaction.",optionalFieldsClear:"Deselect all optional fields",optionalFieldOrderId:"Order ID",optionalFieldTransactionId:"Transaction ID / TXID",optionalFieldAddress:"Address",optionalFieldLnInvoice:"Lightning invoice",optionalFieldMemo:"Memo / CSV note",optionalFieldTransactionType:"Transaction type",optionalFieldExchange:"Exchange / provider",optionalFieldTradeGroup:"Trade group",optionalFieldsSelected:"Optional fields in note"
});

Object.assign(I18N.de, {
  fiatTotal:"Fiat-Gesamtbetrag",fiatTotalPurchaseHint:"Kauf: BTC × Kurs + Fee",fiatTotalSaleHint:"Verkauf: BTC × Kurs − Fee",fiatControlOk:"Rechnung stimmt",fiatControlDifference:"Kontrollabweichung",fiatControlMissing:"Zwei der drei Werte BTC/Sats, Kurs und Fiat-Betrag reichen aus – der dritte wird automatisch berechnet.",fiatControlBlocked:"Die Kontrollwerte passen nicht zusammen. Bitte Betrag, Kurs, Fiat-Gesamtbetrag oder Fee prüfen.",fiatAmountRequired:"Fiat-Gesamtbetrag fehlt oder ist ungültig",amountUnit:"BTC / Sats",calculated:"Berechnet"
});
Object.assign(I18N.en, {
  fiatTotal:"Fiat total",fiatTotalPurchaseHint:"Purchase: BTC × price + fee",fiatTotalSaleHint:"Sale: BTC × price − fee",fiatControlOk:"Calculation matches",fiatControlDifference:"Control difference",fiatControlMissing:"Any two of BTC/sats, price and fiat total are enough – the third value is calculated automatically.",fiatControlBlocked:"The control values do not match. Check amount, price, fiat total or fee.",fiatAmountRequired:"Fiat total is missing or invalid",amountUnit:"BTC / sats",calculated:"Calculated"
});

Object.assign(I18N.de, {
  deleteAllDialogTitle:"Alle Buchungen löschen",deleteAllStepBackup:"Schritt 1 von 2 · Backup prüfen",deleteAllBackupText:"Erstelle vor dem Löschen ein aktuelles verschlüsseltes Backup. Ohne Backup können die Buchungen nicht wiederhergestellt werden.",deleteAllBackupContinue:"Backup erstellt – weiter",deleteAllStepFinal:"Schritt 2 von 2 · Letzte Warnung",deleteAllFinalText:"Alle eingetragenen Käufe, Verkäufe, Ausgaben und Stack-Einträge werden dauerhaft gelöscht.",deleteAllAcknowledge:"Ich verstehe, dass alle eingetragenen Daten dauerhaft gelöscht werden.",deleteAllNow:"Alle Buchungen endgültig löschen",deleteAllWorking:"Buchungen werden gelöscht …",deleteAllFallback:"Kompatibilitätsmodus: Buchungen werden einzeln entfernt.",deleteAllFailed:"Die Buchungen konnten nicht vollständig gelöscht werden.",tableHorizontalScroll:"Tabelle waagerecht verschieben",csvImportStarting:"Import wird gestartet …",csvImporting:"Buchungen werden importiert …",csvImportFailed:"Import fehlgeschlagen:",scrollTableLeft:"Tabelle nach links",scrollTableRight:"Tabelle nach rechts",
  goalReachedAt:"Ziel erreicht am",milestoneReached:"Meilenstein erreicht",wavespacePhysicalCard:"Physische Karte",wavespaceVirtualCard:"Virtuelle Karte",wavespaceCardCreationFee:"Kartenerstellungsgebühr",wavespaceCardPriceLocal:"Zuordnung anhand lokaler Kursdaten",wavespaceCardPriceCompared:"Zuordnung anhand der BTC-Beträge",wavespaceCashWithdrawal:"Bargeldabhebung",wavespaceCardPayment:"Kartenzahlung",
  autoLock:"Auto-Lock",autoLockAfter:"Bei Inaktivität sperren nach",disabled:"Deaktiviert",autoLockDisabled:"Core-Auto-Lock ist für diese entsperrte HA-Sitzung deaktiviert.",autoLockActive:"Core-Auto-Lock aktiv",autoLockTriggered:"Tresor wegen Inaktivität automatisch gesperrt.",browserSecretWarning:"Das Master-Passwort niemals als Seed-, BIP39-, xprv-, Wallet- oder Nostr-Schlüssel wiederverwenden. Ein kompromittierter Browser kann eingegebene Geheimnisse auslesen.",
  deleteEntryKicker:"BUCHUNG ENTFERNEN",deleteEntryDialogTitle:"Buchung löschen",deleteEntryText:"Diese einzelne Buchung dauerhaft löschen?",deleteEntryNow:"Buchung endgültig löschen",deleteEntryWorking:"Buchung wird gelöscht …",
  liveConnections:"Live-Verbindungen & Datenquellen",refreshConnections:"Verbindungen aktualisieren",refreshingConnections:"Aktualisiere …",connectionsRefreshed:"Verbindungen und Live-Kurse aktualisiert",connectionsRefreshFailed:"Aktualisierung fehlgeschlagen",viewRefreshedAt:"Ansicht aktualisiert",livePriceRefreshedAt:"Live-Kurse aktualisiert",livePriceAverage:"Aktueller Marktmittelwert",sourcesUsed:"Quellen verwendet",transportPathTitle:"Öffentlicher Datenweg",transportPathText:"Home Assistant Core → interner SOCKS5-Hop → Tor-Guard/Circuit → Tor-Exit → HTTPS-API. Der Tracker besitzt keinen direkten öffentlichen Clearnet-Fallback.",transportExitNote:"Die API-Verbindung nach dem Tor-Exit entsteht außerhalb deines Heimnetzes. Der öffentliche Anbieter sieht die Tor-Exit-IP, nicht deine Home-Assistant-IP.",liveConnectionsHint:"Zeigt konfigurierte Datenquellen, den vorgesehenen Netzwerkweg, beobachtete Requests und die aktuell sichtbaren Transport-Sockets. Nur für den Portfolio-Eigentümer sichtbar.",livePriceSources:"Echtzeit-Kursquellen",historySources:"Historische Kursquellen",systemSources:"System- und Tor-Prüfungen",observedConnections:"Beobachtete Netzwerkziele",transportConnections:"Aktuelle Transport-Verbindungen",connectionPath:"Verbindungsweg",connectionTarget:"Ziel",connectionStatus:"Status",connectionPurpose:"Zweck",connectionActive:"AKTIV",connectionReady:"Bereit / zuletzt genutzt",connectionConfigured:"Konfiguriert",connectionNever:"Noch nicht beobachtet",connectionNoData:"Keine Verbindungseinträge vorhanden.",routeTor:"Tor · SOCKS5 · Remote DNS",routeLocal:"Direkt · nur privates/lokales Netz",routeHaLocal:"Home Assistant intern · kein öffentlicher Egress",routeTorRelay:"Tor-Prozess → Guard/Relay · verschlüsselter Tor-Transport",routeBlocked:"NICHT ERLAUBT · direkter Clearnet-Egress",purposeLivePrice:"Echtzeitkurs",purposeHistory:"Historie",purposeInternal:"Home Assistant Core / Aktionen",purposeObserved:"Beobachteter Netzwerkrequest",purposeTorCheck:"Tor-Ausgangsprüfung",purposeTorTransport:"Tor-Relay-Transport",purposeBlocked:"Nicht-Tor-Verbindung",browserIngress:"Browser → Home Assistant Core",coreBridge:"Natives Bitcoin-Panel → Home Assistant Core",bundledTor:"Home Assistant Core → separates Tor-Gateway",connectionVersions:"Versionen",connectionOwnerOnly:"Verbindungsdetails sind nur für den Portfolio-Eigentümer sichtbar.",connectionCompatFallback:"Kompatibilitätsmodus: Die Verbindungsdaten werden aus dem normalen Dashboard-Status rekonstruiert.",connectionVersionMismatch:"Panel und Integration haben unterschiedliche Versionen. Bitte die Custom Integration vollständig aktualisieren und Home Assistant neu starten.",unlockHardened:"Gehärteter Geheimnis-Pfad: Master- und Backup-Passwörter, CSV-Dateien und Tresordaten gehen direkt vom nativen Home-Assistant-Panel an Home Assistant Core. Das Tor-Gateway liegt nicht in diesem Datenpfad und besitzt keinen Home-Assistant-API-Token.",cryptoKdf:"Passwort-KDF",cryptoMemory:"KDF-Speicher",cryptoProfileCurrent:"Aktuelles gehärtetes Profil",cryptoProfileOld:"Älteres Profil – wird nach erfolgreichem Unlock automatisch aktualisiert",cryptoEnvelope:"Schlüsselarchitektur",cryptoDataKey:"Tresor-Datenschlüssel",cryptoKeyWrap:"DEK-Schlüsselhülle",cryptoDeviceBinding:"Gerätebindung",cryptoNonceNote:"GCM-IV/Nonce (kein Schlüssel)",cryptoDeviceBound:"256-Bit separater Core-Geräteschlüssel",cryptoPortableNote:"Portable Backups sind absichtlich nicht gerätegebunden"
});
Object.assign(I18N.de, {
  purchasePriceThen:"Kaufkurs damals",fifoCostBasis:"FIFO-Einstand",salePrice:"Abgangskurs",fifoGain:"FIFO-Gewinn/Verlust",fifoReturn:"FIFO-Rendite",averageEntryToDate:"Ø Einkauf bis dahin",averageEntryBasis:"Ø-Vergleichseinstand",averageEntryGain:"Ø-Gewinn/Verlust",averageEntryReturn:"Ø-Rendite",averageEntryComparison:"Ø-P/L",averageComparisonSummary:"Historischer Durchschnittsvergleich",fifoAndAverageSummary:"Abgangsübersicht · FIFO + Ø-Kaufpreis",fifoLotMethod:"FIFO-Lot-Berechnung",averageComparisonPrice:"Ø Vergleichskaufkurs",averageComparisonHint:"Vergleicht jeden Abgang zusätzlich mit dem BTC-gewichteten Einstand aller Käufe derselben Fiatwährung, die bis zum jeweiligen Abgangszeitpunkt erfolgt waren. Bereits zuvor verkaufte Käufe bleiben Teil dieses historischen Vergleichs. Kein FIFO-/Steuerwert.",averageComparisonMissing:"Ohne historischen Durchschnittsvergleich",averageEntryHint:"BTC-gewichteter durchschnittlicher Einstand aller Käufe in derselben Fiatwährung bis zu diesem Zeitpunkt inklusive Kaufgebühren. Bereits zuvor verkaufte Käufe bleiben Teil dieses historischen Durchschnitts. Kein FIFO-/Steuerwert.",saleProceeds:"Erlös / Gegenwert",returnPercent:"Rendite",fifoSummary:"FIFO-Abgangsübersicht",soldAmount:"Abgegangene Menge",fifoCostBasisHint:"Damalige Anschaffungskosten der abgegangenen Sats inklusive anteiliger Kaufgebühren.",saleProceedsHint:"Nettoerlös bei Verkauf beziehungsweise Fiat-Gegenwert einer bewerteten Ausgabe nach anteiliger Gebühr.",fifoCurrencyNote:"Fiat-Gesamtwerte für {currency}; andere Abgangswährungen werden nicht umgerechnet.",fifoUnresolved:"Davon ohne bekannten FIFO-Einstand",dispositionType:"Art",dispositionDate:"Datum",dispositionSale:"Verkauf",dispositionExpense:"Ausgabe",dispositionCount:"Abgänge",
});
Object.assign(I18N.en, {
  purchasePriceThen:"Purchase price then",fifoCostBasis:"FIFO cost basis",salePrice:"Disposal price",fifoGain:"FIFO gain/loss",fifoReturn:"FIFO return",averageEntryToDate:"Avg buy-in to date",averageEntryBasis:"Avg comparison basis",averageEntryGain:"Avg gain/loss",averageEntryReturn:"Avg return",averageEntryComparison:"Avg P/L",averageComparisonSummary:"Historical average comparison",fifoAndAverageSummary:"Disposal overview · FIFO + avg buy-in",fifoLotMethod:"FIFO lot calculation",averageComparisonPrice:"Avg comparison buy price",averageComparisonHint:"Compares every disposal with the BTC-weighted effective acquisition price of all purchases in the same fiat currency made up to that disposal timestamp. Purchases already sold remain part of this historical comparison. Not a FIFO/tax basis.",averageComparisonMissing:"Without historical average comparison",averageEntryHint:"BTC-weighted effective acquisition price of all purchases in the same fiat currency up to this timestamp, including purchase fees. Purchases already sold remain part of this historical average. Not a FIFO/tax basis.",saleProceeds:"Proceeds / value",returnPercent:"Return",fifoSummary:"FIFO disposal summary",soldAmount:"Amount disposed",fifoCostBasisHint:"Original acquisition cost of the disposed sats including allocated purchase fees.",saleProceedsHint:"Net sale proceeds or fiat value of a priced expense after its allocated fee.",fifoCurrencyNote:"Fiat totals for {currency}; other disposal currencies are not converted.",fifoUnresolved:"Without known FIFO cost basis",dispositionType:"Type",dispositionDate:"Date",dispositionSale:"Sale",dispositionExpense:"Expense",dispositionCount:"disposals",
});

Object.assign(I18N.en, {
  deleteAllDialogTitle:"Delete all entries",deleteAllStepBackup:"Step 1 of 2 · Check backup",deleteAllBackupText:"Create a current encrypted backup before deleting. Without a backup, the ledger entries cannot be restored.",deleteAllBackupContinue:"Backup created – continue",deleteAllStepFinal:"Step 2 of 2 · Final warning",deleteAllFinalText:"All entered purchases, sales, expenses, and stack entries will be permanently deleted.",deleteAllAcknowledge:"I understand that all entered data will be permanently deleted.",deleteAllNow:"Permanently delete all entries",deleteAllWorking:"Deleting entries …",deleteAllFallback:"Compatibility mode: removing entries one by one.",deleteAllFailed:"The ledger entries could not be deleted completely.",tableHorizontalScroll:"Scroll table horizontally",csvImportStarting:"Starting import …",csvImporting:"Importing transactions …",csvImportFailed:"Import failed:",scrollTableLeft:"Scroll table left",scrollTableRight:"Scroll table right",
  goalReachedAt:"Goal reached on",milestoneReached:"Milestone reached",wavespacePhysicalCard:"Physical card",wavespaceVirtualCard:"Virtual card",wavespaceCardCreationFee:"Card creation fee",wavespaceCardPriceLocal:"Matched using local price data",wavespaceCardPriceCompared:"Matched by comparing BTC amounts",wavespaceCashWithdrawal:"Cash withdrawal",wavespaceCardPayment:"Card payment",
  autoLock:"Auto-lock",autoLockAfter:"Lock after inactivity",disabled:"Disabled",autoLockDisabled:"Core auto-lock is disabled for this unlocked HA session.",autoLockActive:"Core auto-lock active",autoLockTriggered:"Vault automatically locked because of inactivity.",browserSecretWarning:"Never reuse the master password as a seed, BIP39 passphrase, xprv, wallet password, or Nostr key. A compromised browser can read secrets while they are entered.",
  deleteEntryKicker:"REMOVE ENTRY",deleteEntryDialogTitle:"Delete entry",deleteEntryText:"Permanently delete this single ledger entry?",deleteEntryNow:"Permanently delete entry",deleteEntryWorking:"Deleting entry …",
  liveConnections:"Live connections & data sources",refreshConnections:"Refresh connections",refreshingConnections:"Refreshing …",connectionsRefreshed:"Connections and live prices refreshed",connectionsRefreshFailed:"Refresh failed",viewRefreshedAt:"View refreshed",livePriceRefreshedAt:"Live prices refreshed",livePriceAverage:"Current market average",sourcesUsed:"Sources used",transportPathTitle:"Public data route",transportPathText:"Home Assistant Core → internal SOCKS5 hop → Tor guard/circuit → Tor exit → HTTPS API. The tracker has no direct public Clearnet fallback.",transportExitNote:"The API connection after the Tor exit is outside your home network. The public provider sees the Tor exit IP, not your Home Assistant IP.",liveConnectionsHint:"Shows configured data sources, intended routes, observed requests, and currently visible transport sockets. Visible only to the portfolio owner.",livePriceSources:"Live price sources",historySources:"Historical price sources",systemSources:"System and Tor checks",observedConnections:"Observed network targets",transportConnections:"Current transport connections",connectionPath:"Route",connectionTarget:"Target",connectionStatus:"Status",connectionPurpose:"Purpose",connectionActive:"ACTIVE",connectionReady:"Ready / last used",connectionConfigured:"Configured",connectionNever:"Not observed yet",connectionNoData:"No connection entries available.",routeTor:"Tor · SOCKS5 · remote DNS",routeLocal:"Direct · private/local networks only",routeHaLocal:"Home Assistant internal · no public egress",routeTorRelay:"Tor process → guard/relay · encrypted Tor transport",routeBlocked:"NOT ALLOWED · direct Clearnet egress",purposeLivePrice:"Live price",purposeHistory:"History",purposeInternal:"Home Assistant Core / actions",purposeObserved:"Observed network request",purposeTorCheck:"Tor exit verification",purposeTorTransport:"Tor relay transport",purposeBlocked:"Non-Tor connection",browserIngress:"Browser → Home Assistant Core",coreBridge:"Native Bitcoin panel → Home Assistant Core",bundledTor:"Home Assistant Core → separate Tor gateway",connectionVersions:"Versions",connectionOwnerOnly:"Connection details are visible only to the portfolio owner.",connectionCompatFallback:"Compatibility mode: connection data is reconstructed from the normal dashboard status.",connectionVersionMismatch:"The panel and integration versions differ. Fully update the custom integration and restart Home Assistant.",unlockHardened:"Hardened secret path: master and backup passwords, CSV files, and vault data go directly from the native Home Assistant panel to Home Assistant Core. The Tor gateway is not in this data path and has no Home Assistant API token.",cryptoKdf:"Password KDF",cryptoMemory:"KDF memory",cryptoProfileCurrent:"Current hardened profile",cryptoProfileOld:"Older profile – automatically upgraded after a successful unlock",cryptoEnvelope:"Key architecture",cryptoDataKey:"Vault data key",cryptoKeyWrap:"DEK key wrap",cryptoDeviceBinding:"Device binding",cryptoNonceNote:"GCM IV/nonce (not a key)",cryptoDeviceBound:"Separate 256-bit Core device key",cryptoPortableNote:"Portable backups are intentionally not device-bound"
});

Object.assign(I18N.de, {
  stackingSpeed:"Stacking-Geschwindigkeit",stackingSpeedHint:"Netto-BTC-Veränderung inklusive Käufen, Einnahmen, Bestandszugängen, Verkäufen, Ausgaben sowie On-Chain-/Lightning-Transaktionsgebühren.",last30Days:"Letzte 30 Tage",last365Days:"Letzte 365 Tage",sinceStart:"Seit Beginn",avgPerDay:"Ø pro Tag",avgPerMonth:"Ø pro Monat",
  feeAnalytics:"Gebühren",feeAnalyticsHint:"Gebührenquoten sind volumengewichtet und damit unabhängig von der Größe einzelner Buchungen. Die Abgangsgebührenquote umfasst Verkäufe und bewertete Ausgaben/Kartenzahlungen. BTC-Gebühren umfassen tatsächlich in BTC belastete Gebühren einschließlich On-Chain-/Mininggebühren; bei unvollständigen Legacy-Daten wird kein falscher 0-Wert angezeigt.",totalFees:"Gesamte Gebühren",btcFees:"BTC-Gebühren (gesamt)",purchaseFeeRate:"Kaufgebührenquote",dispositionFeeRate:"Abgangsgebührenquote",weightedByVolume:"volumengewichtet",includedFees:"davon im Preis enthalten",estimatedIncludedFees:"davon geschätzt",btcFeeIncludesOnchain:"inkl. On-Chain-/Mininggebühren",btcFeeLegacyIncomplete:"ältere On-Chain-Buchungen ohne rekonstruierbaren BTC-Fee-Wert vorhanden",
  hodlBenchmark:"Cashflow-neutraler HODL-Benchmark",hodlBenchmarkHint:"Vergleicht den aktuellen Stack mit einem fee-freien HODL-Pfad bei denselben externen Fiat-Cashflows. Käufe und Einnahmen gelten als externe Zuflüsse, Verkäufe/Ausgaben als externe Entnahmen; bei mehreren Fiatwährungen wird kein versteckter FX-Kurs erfunden.",hodlStack:"HODL-Stack",yourStack:"Dein Stack",difference:"Differenz",strategyVsHodl:"Strategie vs. HODL",hodlUnavailableMixedFiat:"Nicht eindeutig: Das Ledger enthält mehrere Fiatwährungen und der Tracker erfindet keinen FX-Kurs.",
  btcCagr:"Bitcoin-Kurs · Ø jährliches Wachstum (CAGR)",btcCagrHint:"Durchschnittliche annualisierte Wachstumsrate des Bitcoin-Kurses vom ersten bewerteten Buchungsdatum bis heute. Käufe, Verkäufe, Einnahmen, Ausgaben und Gebühren verändern diesen Marktwert nicht; für deine persönliche Rendite sind XIRR und TWR relevant.",
  netInvestedFiat:"Netto investiertes Fiat",netInvestedFiatHint:"Kaufaufwendungen inklusive Kaufgebühren minus Nettoerlöse aus Verkäufen. Ausgaben werden nicht als zurückgeholtes Fiat behandelt.",realizedHint:"Realisierter FIFO-Gewinn/-Verlust aus Verkäufen, bewerteten Ausgaben und dem FIFO-Effekt verbrauchter BTC-Transaktionsgebühren.",unrealizedHint:"Aktueller Buchgewinn/-verlust der noch offenen FIFO-Lots gegenüber ihrem Einstand inklusive anteiliger Kaufgebühren.",totalProfitHint:"Realisierter plus unrealisierter Gewinn/Verlust.",
  daysSinceAth:"Tage seit letztem Hoch",longestRecovery:"Längste Erholung",completedRecoveryHint:"längste abgeschlossene Erholung",
  overHoldingRule:"Über Haltefrist",underHoldingRule:"Unter Haltefrist",next30Holding:"In 30 Tagen über Haltefrist",next90Holding:"In 90 Tagen über Haltefrist",weightedStackAge:"Gewichtetes Stack-Alter",oldestOpenLot:"Ältestes offenes Lot",yearsUnit:"Jahre",stackAgeDistribution:"Altersverteilung des offenen Stacks",holdingAgeHint:"Das Alter wird BTC-gewichtet aus den aktuell offenen FIFO-Lots berechnet.",under1Year:"< 1 Jahr",oneToTwoYears:"1–2 Jahre",twoToFourYears:"2–4 Jahre",overFourYears:"> 4 Jahre"
});
Object.assign(I18N.en, {
  stackingSpeed:"Stacking speed",stackingSpeedHint:"Net BTC change including purchases, income, opening-balance additions, sales, expenses, and on-chain/Lightning transaction fees.",last30Days:"Last 30 days",last365Days:"Last 365 days",sinceStart:"Since start",avgPerDay:"Avg per day",avgPerMonth:"Avg per month",
  feeAnalytics:"Fees",feeAnalyticsHint:"Fee ratios are volume-weighted, so they remain comparable across differently sized bookings. The disposition fee ratio includes sales and priced expenses/card payments. BTC fees include fees actually charged in BTC, including on-chain/mining fees; incomplete legacy data is never presented as a false zero.",totalFees:"Total fees",btcFees:"BTC fees (total)",purchaseFeeRate:"Purchase fee ratio",dispositionFeeRate:"Disposition fee ratio",weightedByVolume:"volume-weighted",includedFees:"included in execution price",estimatedIncludedFees:"estimated portion",btcFeeIncludesOnchain:"includes on-chain/mining fees",btcFeeLegacyIncomplete:"older on-chain bookings without a reconstructable BTC fee are present",
  hodlBenchmark:"Cash-flow-neutral HODL benchmark",hodlBenchmarkHint:"Compares the current stack with a fee-free HODL path using the same external fiat cash flows. Purchases and income are treated as external inflows and sales/expenses as external withdrawals; no hidden FX rate is invented for mixed-fiat ledgers.",hodlStack:"HODL stack",yourStack:"Your stack",difference:"Difference",strategyVsHodl:"Strategy vs HODL",hodlUnavailableMixedFiat:"Unavailable: the ledger contains multiple fiat currencies and the tracker does not invent an FX rate.",
  btcCagr:"Bitcoin price · average annual growth (CAGR)",btcCagrHint:"Average annualized growth rate of the Bitcoin market price from the first priced booking to today. Purchases, sales, income, expenses and fees do not change this market metric; XIRR and TWR describe your personal return.",
  netInvestedFiat:"Net fiat invested",netInvestedFiatHint:"Purchase outlays including purchase fees minus net proceeds from sales. Expenses are not treated as fiat returned to you.",realizedHint:"Realized FIFO profit/loss from sales, priced expenses, and the FIFO effect of BTC consumed as transaction fees.",unrealizedHint:"Current book profit/loss of open FIFO lots versus cost basis including allocated purchase fees.",totalProfitHint:"Realized plus unrealized profit/loss.",
  daysSinceAth:"Days since last high",longestRecovery:"Longest recovery",completedRecoveryHint:"longest completed recovery",
  overHoldingRule:"Over holding period",underHoldingRule:"Under holding period",next30Holding:"Over holding period within 30 days",next90Holding:"Over holding period within 90 days",weightedStackAge:"Weighted stack age",oldestOpenLot:"Oldest open lot",yearsUnit:"years",stackAgeDistribution:"Age distribution of open stack",holdingAgeHint:"Age is BTC-weighted across currently open FIFO lots.",under1Year:"< 1 year",oneToTwoYears:"1–2 years",twoToFourYears:"2–4 years",overFourYears:"> 4 years"
});

Object.assign(I18N.de,{
  marketAssessment:"Markteinschätzung",marketAssessmentShortHint:"Zusätzliche relative Einschätzung des aktuellen Bitcoin-Marktumfelds.",openMarketAssessment:"Details & Modell anpassen",
  buyOpportunity:"Markteinschätzung",buyOpportunityScoreHint:"Je höher, desto günstiger bewertet das Modell das aktuelle Bitcoin-Marktumfeld relativ zu seiner eigenen Historie und Volatilität.",buyOpportunityDisclaimer:"Zusätzliche modellbasierte Markteinschätzung aus öffentlichen historischen Kursdaten. Kein Kaufsignal, keine Prognose und keine Anlageempfehlung.",buyOpportunitySettings:"Markteinschätzung anpassen",buyOpportunitySettingsHint:"Alle wesentlichen Modellparameter sind modular. Die backgetesteten Standardwerte bleiben der sichere Ausgangspunkt und können jederzeit wiederhergestellt werden.",buyOpportunityProfile:"Profil",referenceCurrency:"Referenzwährung",componentWeights:"Gewichtung der Bewertungsgruppen",scoreThresholds:"Score-Grenzen",thresholdVeryExpensiveMax:"Sehr hoch bewertet bis",thresholdExpensiveMax:"Hoch bewertet bis",saveBuyOpportunitySettings:"Markteinschätzung speichern",buyOpportunitySaved:"Markteinschätzung gespeichert",resetMarketAssessmentDefaults:"Backtest-Standard wiederherstellen",marketAssessmentReset:"Backtest-Standard wiederhergestellt",
  profileBalanced:"Ausgewogen",profileLongTerm:"Langfristig",profileDip:"Dip / Abverkauf",profileCycle:"Zyklus",profileCustom:"Benutzerdefiniert",componentLongTerm:"Langfristige Bewertung",componentDrawdown:"Drawdown",componentRange:"Historische Preisposition",componentDeviation:"Trendabweichung",componentMomentum:"Momentum / Überverkauft",componentCycle:"Zyklusmodelle",
  ratingVeryExpensive:"Sehr hoch bewertet",ratingExpensive:"Hoch bewertet",ratingNeutral:"Neutral",ratingInteresting:"Interessant",ratingCheap:"Günstig",ratingVeryCheap:"Sehr günstig",ratingExtreme:"Extrem günstig",ratingUnavailable:"Nicht verfügbar",
  mayerMultiple:"Mayer Multiple",athDrawdown:"Drawdown vom Hoch",pricePercentile:"Preis-Perzentil",rsi14:"RSI",distanceSma200:"Abstand Basis-MA",powerLawRatio:"Power-Law-Verhältnis",dataCoverage:"Datenabdeckung",historyPoints:"Tageswerte",scoreVersion:"Score-Modell",
  signalWeights:"Einzelne Signale gewichten",signalWeightsHint:"0 deaktiviert ein Signal. Signalgewichte werden zuerst innerhalb ihrer Gruppe normalisiert; danach greifen die Gruppengewichte.",modelParameters:"Adaptive Modellparameter",modelParametersHint:"Diese Werte steuern Zeitfenster und Anpassung an die herrschende Bitcoin-Volatilität. Änderungen können historische Scores deutlich verändern.",
  signalTrendBase:"Langfristig · Basis-MA",signalTrendLong:"Langfristig · Langzeit-MA",signalTrendCycle:"Langfristig · Zyklus-MA",signalPowerLaw:"Langfristig · Power Law",signalDrawdownLocal:"Drawdown · lokales Hoch",signalDrawdownRegime:"Drawdown · Regimehoch",signalPricePercentile:"Preisposition · Perzentil",signalTrendMid:"Preisposition · Mitteltrend",signalShortZ:"Abweichung · Kurzfrist-Z",signalTrendShort:"Abweichung · Kurztrend",signalMomentumShort:"Momentum · kurz",signalMomentumLong:"Momentum · lang",signalRsi:"Momentum · RSI",signalCycleTrend:"Zyklus · Langzeittrend",signalPiCycle:"Zyklus · Pi-Cycle",signalTwoYear:"Zyklus · 2-Year-Multiplier",signalPowerLawCycle:"Zyklus · Power Law",
  modelMinimumHistory:"Mindesthistorie · Tage",modelAdaptiveWindow:"Regime-/Referenzfenster · Tage",modelAdaptiveMin:"Mindest-Referenzpunkte",modelVolatilityWindow:"Volatilitätsfenster · Tage",modelVolatilityMin:"Volatilität · Mindestpunkte",modelVolatilityFloor:"Volatilitäts-Floor · % p.a.",modelDrawdownWindow:"Drawdownfenster · Tage",modelDrawdownMin:"Drawdown · Mindestpunkte",modelRegimeHighMin:"Regimehoch · Mindestpunkte",modelPercentileWindow:"Preis-Perzentilfenster · Tage",modelPercentileMin:"Preis-Perzentil · Mindestpunkte",modelShortDeviation:"Kurzabweichung · Tage",modelTrendShort:"Kurztrend-MA · Tage",modelPiShort:"Pi-Cycle kurz · Tage",modelTrendBase:"Basis-MA · Tage",modelPiLong:"Pi-Cycle lang · Tage",modelTrendMid:"Mitteltrend-MA · Tage",modelTrendLong:"Langzeit-MA · Tage",modelTrendCycle:"Zyklus-MA · Tage",modelRsiPeriod:"RSI-Periode · Tage",modelMomentumShort:"Momentum kurz · Tage",modelMomentumLong:"Momentum lang · Tage",modelTwoYearMultiplier:"2-Year-Multiplikator",modelPowerLawMin:"Power Law · Mindestpunkte",modelVolRegimeLow:"Vola-Regime niedrig · Verhältnis",modelVolRegimeHigh:"Vola-Regime hoch · Verhältnis",
  turningPointAssessment:"Boden- & Top-Bereiche",turningPointDisclaimer:"Boden-/Top-Werte beschreiben Zonen und Bestätigungsmerkmale. Sie erklären weder einen exakten Boden noch ein exaktes Top und sind keine Handelssignale.",bottomZone:"Bottom Zone",bottomConfirmation:"Bottom Confirmation",topZone:"Top Zone",topConfirmation:"Top Confirmation",marketPhase:"Marktphase",turningPointWeights:"Boden-/Top-Modelle gewichten",turningPointWeightsHint:"0 deaktiviert ein Einzelsignal. Zonen und Bestätigungen werden getrennt berechnet; der Hauptscore bleibt davon unabhängig.",
  tpValuation:"Bewertung",tpDuration:"Drawdown-Dauer",tpMomentumStress:"Momentum-Stress",tpVolatilityStress:"Volatilitäts-Stress",tpRsiDivergence:"RSI-Divergenz",tpReturnDivergence:"Momentum-Divergenz",tpVolatilityCooling:"Vola-Abkühlung nach Spike",tpTrendReclaim:"Trend-Reclaim",tpSellingExhaustion:"Verkäufer-Erschöpfung",tpPriceRebound:"Preis-Rebound",tpTrendExtension:"Trend-Überdehnung",tpMomentumHeat:"Momentum-Hitze",tpAcceleration:"Parabolische Beschleunigung",tpNearHigh:"Nähe zum Regimehoch",tpTrendLoss:"Trendverlust",tpBuyingExhaustion:"Käufer-Erschöpfung",tpPriceRejection:"Preis-Rejection",
  modelTurningLookback:"Wendepunkt-Lookback · Tage",modelTurningSeparation:"Swing-Mindestabstand · Tage",modelTurningMemory:"Zonengedächtnis · Tage",modelDivergenceTolerance:"Divergenz-Preistoleranz · %",modelFastVolatility:"Schnelle Vola · Tage",modelSlowVolatility:"Langsame Vola · Tage",modelVolCoolingLookback:"Vola-Abkühlung · Lookback",modelExhaustionShort:"Erschöpfung kurz · Tage",modelConfirmationGate:"Bestätigung · Zonenbindung",modelTurningZoneThreshold:"Wendepunkt-Zone ab",modelTurningConfirmationThreshold:"Bestätigung ab",modelTurningExtremeThreshold:"Extreme Zone ab",
  phaseBottoming:"Mögliche Bodenbildung",phaseCapitulation:"Kapitulation / Extremzone",phaseTopFormation:"Mögliche Topbildung",phaseOverheating:"Überhitzung",phaseRecovery:"Erholung",phaseCooling:"Abkühlung",phaseDepressed:"Gedrücktes Marktregime",phaseExpansion:"Expansion",phaseNeutral:"Neutral"
});
Object.assign(I18N.en,{
  marketAssessment:"Market assessment",marketAssessmentShortHint:"Additional relative assessment of the current Bitcoin market environment.",openMarketAssessment:"Details & tune model",
  buyOpportunity:"Market assessment",buyOpportunityScoreHint:"The higher the score, the cheaper the model rates the current Bitcoin market environment relative to its own history and volatility.",buyOpportunityDisclaimer:"Additional model-based market assessment derived from public historical price data. Not a buy signal, forecast, or investment recommendation.",buyOpportunitySettings:"Tune market assessment",buyOpportunitySettingsHint:"All material model parameters are modular. The backtested defaults remain the safe starting point and can be restored at any time.",buyOpportunityProfile:"Profile",referenceCurrency:"Reference currency",componentWeights:"Valuation-group weights",scoreThresholds:"Score thresholds",thresholdVeryExpensiveMax:"Very highly valued below",thresholdExpensiveMax:"Highly valued below",saveBuyOpportunitySettings:"Save market assessment",buyOpportunitySaved:"Market assessment saved",resetMarketAssessmentDefaults:"Restore backtested defaults",marketAssessmentReset:"Backtested defaults restored",
  profileBalanced:"Balanced",profileLongTerm:"Long term",profileDip:"Dip / sell-off",profileCycle:"Cycle",profileCustom:"Custom",componentLongTerm:"Long-term valuation",componentDrawdown:"Drawdown",componentRange:"Historical price position",componentDeviation:"Trend deviation",componentMomentum:"Momentum / oversold",componentCycle:"Cycle models",
  ratingVeryExpensive:"Very highly valued",ratingExpensive:"Highly valued",ratingNeutral:"Neutral",ratingInteresting:"Interesting",ratingCheap:"Cheap",ratingVeryCheap:"Very cheap",ratingExtreme:"Extremely cheap",ratingUnavailable:"Unavailable",
  mayerMultiple:"Mayer Multiple",athDrawdown:"Drawdown from high",pricePercentile:"Price percentile",rsi14:"RSI",distanceSma200:"Distance from base MA",powerLawRatio:"Power-law ratio",dataCoverage:"Data coverage",historyPoints:"daily values",scoreVersion:"Score model",
  signalWeights:"Weight individual signals",signalWeightsHint:"0 disables a signal. Signal weights are normalized within their group first; group weights are applied afterwards.",modelParameters:"Adaptive model parameters",modelParametersHint:"These values control time windows and adaptation to prevailing Bitcoin volatility. Changes can materially alter historical scores.",
  signalTrendBase:"Long term · base MA",signalTrendLong:"Long term · long MA",signalTrendCycle:"Long term · cycle MA",signalPowerLaw:"Long term · power law",signalDrawdownLocal:"Drawdown · local high",signalDrawdownRegime:"Drawdown · regime high",signalPricePercentile:"Price position · percentile",signalTrendMid:"Price position · mid trend",signalShortZ:"Deviation · short Z",signalTrendShort:"Deviation · short trend",signalMomentumShort:"Momentum · short",signalMomentumLong:"Momentum · long",signalRsi:"Momentum · RSI",signalCycleTrend:"Cycle · long trend",signalPiCycle:"Cycle · Pi-Cycle",signalTwoYear:"Cycle · 2-Year multiplier",signalPowerLawCycle:"Cycle · power law",
  modelMinimumHistory:"Minimum history · days",modelAdaptiveWindow:"Regime/reference window · days",modelAdaptiveMin:"Minimum reference points",modelVolatilityWindow:"Volatility window · days",modelVolatilityMin:"Volatility · minimum points",modelVolatilityFloor:"Volatility floor · % p.a.",modelDrawdownWindow:"Drawdown window · days",modelDrawdownMin:"Drawdown · minimum points",modelRegimeHighMin:"Regime high · minimum points",modelPercentileWindow:"Price-percentile window · days",modelPercentileMin:"Price percentile · minimum points",modelShortDeviation:"Short deviation · days",modelTrendShort:"Short-trend MA · days",modelPiShort:"Pi-Cycle short · days",modelTrendBase:"Base MA · days",modelPiLong:"Pi-Cycle long · days",modelTrendMid:"Mid-trend MA · days",modelTrendLong:"Long-term MA · days",modelTrendCycle:"Cycle MA · days",modelRsiPeriod:"RSI period · days",modelMomentumShort:"Momentum short · days",modelMomentumLong:"Momentum long · days",modelTwoYearMultiplier:"2-Year multiplier",modelPowerLawMin:"Power law · minimum points",modelVolRegimeLow:"Low-vol regime · ratio",modelVolRegimeHigh:"High-vol regime · ratio",
  turningPointAssessment:"Bottom & top zones",turningPointDisclaimer:"Bottom/top values describe zones and confirmation characteristics. They do not declare an exact bottom or top and are not trading signals.",bottomZone:"Bottom Zone",bottomConfirmation:"Bottom Confirmation",topZone:"Top Zone",topConfirmation:"Top Confirmation",marketPhase:"Market phase",turningPointWeights:"Weight bottom/top models",turningPointWeightsHint:"0 disables an individual signal. Zones and confirmations are calculated separately; the main score remains independent.",
  tpValuation:"Valuation",tpDuration:"Drawdown duration",tpMomentumStress:"Momentum stress",tpVolatilityStress:"Volatility stress",tpRsiDivergence:"RSI divergence",tpReturnDivergence:"Momentum divergence",tpVolatilityCooling:"Volatility cooling after spike",tpTrendReclaim:"Trend reclaim",tpSellingExhaustion:"Seller exhaustion",tpPriceRebound:"Price rebound",tpTrendExtension:"Trend extension",tpMomentumHeat:"Momentum heat",tpAcceleration:"Parabolic acceleration",tpNearHigh:"Near regime high",tpTrendLoss:"Trend loss",tpBuyingExhaustion:"Buyer exhaustion",tpPriceRejection:"Price rejection",
  modelTurningLookback:"Turning-point lookback · days",modelTurningSeparation:"Minimum swing separation · days",modelTurningMemory:"Zone memory · days",modelDivergenceTolerance:"Divergence price tolerance · %",modelFastVolatility:"Fast volatility · days",modelSlowVolatility:"Slow volatility · days",modelVolCoolingLookback:"Volatility cooling lookback",modelExhaustionShort:"Exhaustion short · days",modelConfirmationGate:"Confirmation · zone gate",modelTurningZoneThreshold:"Turning-point zone from",modelTurningConfirmationThreshold:"Confirmation from",modelTurningExtremeThreshold:"Extreme zone from",
  phaseBottoming:"Possible bottom formation",phaseCapitulation:"Capitulation / extreme zone",phaseTopFormation:"Possible top formation",phaseOverheating:"Overheating",phaseRecovery:"Recovery",phaseCooling:"Cooling",phaseDepressed:"Depressed market regime",phaseExpansion:"Expansion",phaseNeutral:"Neutral"
});
Object.assign(I18N.de,{marketHistoryTitle:"Verlauf der Markteinschätzung",btcPriceOverlay:"BTC-Preis Overlay",priceOpacity:"Preis-Deckkraft",priceAxis:"Preisachse",marketSmoothing:"Glättung",smoothingOff:"Aus",restoreChartDefaults:"Standard wiederherstellen",marketHistoryDisplayReset:"Chart-Standard wiederhergestellt",marketHistoryCausalHint:"Jeder historische Punkt wird mit derselben aktuell gewählten Modellkonfiguration so berechnet, als wäre dieser Tag „heute“. Spätere Kurse fließen nicht rückwirkend ein. Die optionale EMA-Glättung ist rein visuell, arbeitet nur rückblickend und verändert weder den Rohscore noch den Home-Assistant-Sensor.",marketHistoryLoading:"Historischer Score wird geladen …",refresh:"Aktualisieren"});
Object.assign(I18N.en,{marketHistoryTitle:"Market assessment history",btcPriceOverlay:"BTC price overlay",priceOpacity:"Price opacity",priceAxis:"Price axis",marketSmoothing:"Smoothing",smoothingOff:"Off",restoreChartDefaults:"Restore defaults",marketHistoryDisplayReset:"Chart defaults restored",marketHistoryCausalHint:"Each historical point is calculated with the currently selected model configuration as if that day were today. Later prices never flow backward. Optional EMA smoothing is display-only, uses past points only, and changes neither the raw score nor the Home Assistant sensor.",marketHistoryLoading:"Loading historical score …",refresh:"Refresh"});

const BUY_OPPORTUNITY_PRESETS={
  balanced:{long_term:25,drawdown:20,range:15,deviation:15,momentum:10,cycle:15},
  long_term:{long_term:35,drawdown:15,range:15,deviation:10,momentum:5,cycle:20},
  dip:{long_term:15,drawdown:30,range:15,deviation:20,momentum:15,cycle:5},
  cycle:{long_term:25,drawdown:10,range:10,deviation:10,momentum:5,cycle:40}
};
const BUY_OPPORTUNITY_COMPONENTS=["long_term","drawdown","range","deviation","momentum","cycle"];
const BUY_OPPORTUNITY_COMPONENT_LABEL={long_term:"componentLongTerm",drawdown:"componentDrawdown",range:"componentRange",deviation:"componentDeviation",momentum:"componentMomentum",cycle:"componentCycle"};
const BUY_OPPORTUNITY_SIGNAL_DEFAULTS={
  long_term:{trend_base:2,trend_long:1,trend_cycle:0,power_law:0},
  drawdown:{drawdown_local:2,drawdown_regime:1},
  range:{price_percentile:1,trend_mid:1},
  deviation:{short_z:1,trend_short:1},
  momentum:{momentum_short:1,momentum_long:1,rsi:1},
  cycle:{trend_cycle:1,pi_cycle:1,two_year_upper:1,power_law:0}
};
const BUY_OPPORTUNITY_TURNING_DEFAULTS={
  bottom_zone:{valuation:25,drawdown:20,duration:10,range:15,momentum_stress:15,volatility_stress:15},
  bottom_confirmation:{rsi_divergence:25,return_divergence:15,volatility_cooling:5,trend_reclaim:15,selling_exhaustion:20,price_rebound:20},
  top_zone:{valuation:25,trend_extension:20,range:10,momentum_heat:15,pi_cycle:10,acceleration:15,near_high:5},
  top_confirmation:{rsi_divergence:20,return_divergence:10,volatility_cooling:5,trend_loss:15,buying_exhaustion:15,price_rejection:35}
};
const BUY_OPPORTUNITY_MODEL_DEFAULTS={minimum_history_points:365,adaptive_window_days:1460,adaptive_min_reference_points:180,volatility_window_days:365,volatility_min_points:90,volatility_floor_pct:5,drawdown_window_days:365,drawdown_min_points:180,regime_high_min_points:365,percentile_window_days:365,percentile_min_points:180,short_deviation_days:20,trend_short_days:50,pi_short_days:111,trend_base_days:200,pi_long_days:350,trend_mid_days:365,trend_long_days:730,trend_cycle_days:1400,rsi_period_days:14,momentum_short_days:30,momentum_long_days:90,two_year_multiplier:5,power_law_min_points:365,volatility_regime_low_ratio:.75,volatility_regime_high_ratio:1.25,turning_point_lookback_days:180,turning_point_separation_days:14,turning_zone_memory_days:45,divergence_price_tolerance_pct:8,volatility_fast_window_days:30,volatility_slow_window_days:90,volatility_cooling_lookback_days:45,exhaustion_short_days:7,confirmation_zone_gate:.65,turning_zone_threshold:75,turning_confirmation_threshold:40,turning_extreme_threshold:85};
const BUY_OPPORTUNITY_MODEL_KEYS=Object.keys(BUY_OPPORTUNITY_MODEL_DEFAULTS);
const BUY_OPPORTUNITY_FIELD_HELP={"profile":["Wählt ein abgestimmtes Preset. Ein anderes Profil verändert mehrere Gruppengewichte gleichzeitig; „Benutzerdefiniert“ lässt deine Einzelwerte unverändert.","Selects a tuned preset. Changing the profile changes several group weights together; “Custom” keeps your individual values."],"currency":["Legt fest, in welcher Fiatwährung Kurs und Historie für das Modell bewertet werden. Ändert keine BTC-Menge, kann aber bei abweichender Datenhistorie leicht andere Scores ergeben.","Sets the fiat currency used for price history and model evaluation. It does not change BTC amounts, but different history coverage can slightly change scores."],"weight_long_term":["Gewicht für langfristige Trend-/Bewertungssignale. Höher = diese Gruppe hat relativ mehr Einfluss auf den Gesamtscore; niedriger = weniger Einfluss; 0 = Gruppe aus. Ein höheres Gewicht erhöht den Score nicht automatisch, sondern verstärkt nur das jeweilige Signal.","Weight for long-term trend/valuation signals. Higher = this group has more relative influence on the total score; lower = less influence; 0 = group off. A higher weight does not automatically raise the score; it only amplifies that group’s signal."],"weight_drawdown":["Gewicht für Rückgänge von lokalen und Regime-Hochs. Höher = diese Gruppe hat relativ mehr Einfluss auf den Gesamtscore; niedriger = weniger Einfluss; 0 = Gruppe aus. Ein höheres Gewicht erhöht den Score nicht automatisch, sondern verstärkt nur das jeweilige Signal.","Weight for declines from local and regime highs. Higher = this group has more relative influence on the total score; lower = less influence; 0 = group off. A higher weight does not automatically raise the score; it only amplifies that group’s signal."],"weight_range":["Gewicht für die historische Preisposition und den Mitteltrend. Höher = diese Gruppe hat relativ mehr Einfluss auf den Gesamtscore; niedriger = weniger Einfluss; 0 = Gruppe aus. Ein höheres Gewicht erhöht den Score nicht automatisch, sondern verstärkt nur das jeweilige Signal.","Weight for historical price position and the mid-term trend. Higher = this group has more relative influence on the total score; lower = less influence; 0 = group off. A higher weight does not automatically raise the score; it only amplifies that group’s signal."],"weight_deviation":["Gewicht für kurzfristige Abweichungen vom Trend. Höher = diese Gruppe hat relativ mehr Einfluss auf den Gesamtscore; niedriger = weniger Einfluss; 0 = Gruppe aus. Ein höheres Gewicht erhöht den Score nicht automatisch, sondern verstärkt nur das jeweilige Signal.","Weight for short-term deviations from trend. Higher = this group has more relative influence on the total score; lower = less influence; 0 = group off. A higher weight does not automatically raise the score; it only amplifies that group’s signal."],"weight_momentum":["Gewicht für Momentum, Überverkauftheit und RSI. Höher = diese Gruppe hat relativ mehr Einfluss auf den Gesamtscore; niedriger = weniger Einfluss; 0 = Gruppe aus. Ein höheres Gewicht erhöht den Score nicht automatisch, sondern verstärkt nur das jeweilige Signal.","Weight for momentum, oversold conditions and RSI. Higher = this group has more relative influence on the total score; lower = less influence; 0 = group off. A higher weight does not automatically raise the score; it only amplifies that group’s signal."],"weight_cycle":["Gewicht für langfristige Zyklusmodelle. Höher = diese Gruppe hat relativ mehr Einfluss auf den Gesamtscore; niedriger = weniger Einfluss; 0 = Gruppe aus. Ein höheres Gewicht erhöht den Score nicht automatisch, sondern verstärkt nur das jeweilige Signal.","Weight for long-term cycle models. Higher = this group has more relative influence on the total score; lower = less influence; 0 = group off. A higher weight does not automatically raise the score; it only amplifies that group’s signal."],"signal_long_term_trend_base":["Abstand zum Basis-MA. Bewertet, ob der Preis relativ zu seinem mittelfristigen Grundtrend günstig oder teuer liegt. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Distance from the base MA; measures whether price is cheap or expensive relative to its medium-term base trend. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_long_term_trend_long":["Abstand zum Langzeit-MA. Betont längere Marktregime und reagiert träger als der Basis-MA. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Distance from the long-term MA; emphasizes longer regimes and reacts more slowly than the base MA. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_long_term_trend_cycle":["Abstand zum sehr langen Zyklus-MA. Liefert eine besonders langsame Zyklus-Perspektive. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Distance from the very long cycle MA; provides a very slow cycle perspective. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_long_term_power_law":["Bewertung relativ zur Power-Law-Kurve. Nutzt die langfristige Preis-Zeit-Beziehung als zusätzliche Bewertungsachse. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Valuation relative to the power-law curve, using the long-run price/time relationship as an additional axis. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_drawdown_drawdown_local":["Drawdown vom Hoch des lokalen Drawdownfensters. Große Rückgänge wirken stärker als günstiges Umfeld. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Drawdown from the high of the local drawdown window. Larger declines contribute more to a cheap-market reading. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_drawdown_drawdown_regime":["Drawdown vom Hoch des längeren adaptiven Regimes. Erfasst tiefe Rückgänge über längere Marktphasen. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Drawdown from the high of the longer adaptive regime, capturing deep declines across longer market phases. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_range_price_percentile":["Position des Preises innerhalb seines historischen Referenzfensters. Niedrige historische Positionen werden als günstiger bewertet. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Price position inside its historical reference window. Lower historical positions are rated as cheaper. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_range_trend_mid":["Abstand zum Mitteltrend-MA. Ergänzt das Perzentil um eine trendbasierte Preisposition. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Distance from the mid-trend MA, complementing percentile position with a trend-based measure. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_deviation_short_z":["Kurzfristiger Z-Score der logarithmischen Preisabweichung. Erkennt ungewöhnlich starke kurzfristige Über- oder Untertreibungen. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Short-term z-score of log-price deviation, detecting unusually strong short-term extensions or selloffs. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_deviation_trend_short":["Abstand zum kurzen Trend-MA. Reagiert schneller auf Dips und kurzfristige Überdehnung. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Distance from the short trend MA; reacts faster to dips and short-term extension. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_momentum_momentum_short":["Kurzfristige, volatilitätsbereinigte Rendite. Negative Bewegungen können Überverkauftheit anzeigen. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Short-term volatility-adjusted return; negative moves can indicate oversold conditions. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_momentum_momentum_long":["Längerfristige, volatilitätsbereinigte Rendite. Glättet kurzfristiges Rauschen stärker. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Longer-term volatility-adjusted return; filters short-term noise more strongly. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_momentum_rsi":["RSI-basierte Überkauft-/Überverkauft-Bewertung. Niedriger RSI unterstützt günstige, hoher RSI teure Marktphasen. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","RSI-based overbought/oversold assessment. Low RSI supports cheap readings; high RSI supports expensive readings. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_cycle_trend_cycle":["Sehr langfristiger Trendabstand als Zyklusindikator. Reagiert langsam und gewichtet große Marktphasen. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Very long-term trend distance used as a cycle indicator; slow and focused on major market phases. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_cycle_pi_cycle":["Nähe zum Pi-Cycle-Verhältnis aus kurzem und langem MA. Soll zyklische Überhitzung erkennen. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Proximity to the Pi-Cycle ratio of short and long MAs, intended to detect cyclical overheating. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_cycle_two_year_upper":["Preis relativ zum langfristigen MA multipliziert mit dem 2-Year-Faktor. Hohe Nähe zur Obergrenze spricht eher für Überhitzung. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Price relative to the long-term MA multiplied by the 2-Year factor. Closer proximity to the upper band suggests overheating. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"signal_cycle_power_law":["Power-Law-Bewertung innerhalb der Zyklusgruppe. Ergänzt MA-basierte Zyklussignale. Höher = dieses Signal zählt innerhalb seiner Gruppe stärker; niedriger = schwächer; 0 = aus. Das Vorzeichen des Signals entscheidet, ob der Gruppenwert steigt oder fällt.","Power-law valuation inside the cycle group, complementing MA-based cycle signals. Higher = this signal counts more inside its group; lower = less; 0 = off. The signal direction determines whether the group score rises or falls."],"turn_bottom_zone_valuation":["Bewertung des Hauptscores für eine mögliche Boden-Zone. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Main-score valuation contribution to a possible bottom zone. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_zone_drawdown":["Tiefe des Drawdowns als Merkmal einer möglichen Boden-Zone. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Drawdown depth as a feature of a possible bottom zone. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_zone_duration":["Dauer seit einem relevanten Hoch. Längere Schwäche kann die Boden-Zone stützen. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Time since a relevant high; prolonged weakness can support the bottom-zone reading. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_zone_range":["Historisch niedrige Preisposition als Bodenmerkmal. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Historically low price position as a bottom feature. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_zone_momentum_stress":["Stark negatives Momentum als Kapitulations-/Stressmerkmal. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Strong negative momentum as a capitulation/stress feature. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_zone_volatility_stress":["Erhöhte schnelle Volatilität relativ zur langsamen Volatilität als Stressmerkmal. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Elevated fast volatility versus slow volatility as a stress feature. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_confirmation_rsi_divergence":["Bullische RSI-Divergenz: Preis macht ein ähnliches/tieferes Tief, RSI verbessert sich. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Bullish RSI divergence: price makes a similar/lower low while RSI improves. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_confirmation_return_divergence":["Bullische Momentum-Divergenz: Preis bleibt schwach, Renditemomentum verbessert sich. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Bullish momentum divergence: price stays weak while return momentum improves. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_confirmation_volatility_cooling":["Abkühlung der Volatilität nach einem Stress-Spike als Stabilisierungssignal. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Volatility cooling after a stress spike as a stabilization signal. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_confirmation_trend_reclaim":["Rückeroberung eines kurzen Trends nach Schwäche. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Reclaim of a short trend after weakness. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_confirmation_selling_exhaustion":["Nachlassender Verkaufsdruck nach einer starken Abwärtsbewegung. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Fading selling pressure after a strong decline. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_bottom_confirmation_price_rebound":["Messbarer Rebound vom jüngsten Tief. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Measurable rebound from the recent low. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_zone_valuation":["Hohe/teure Bewertung als Merkmal einer möglichen Top-Zone. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","High/expensive valuation as a possible top-zone feature. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_zone_trend_extension":["Starke positive Überdehnung über langfristige Trends. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Strong positive extension above long-term trends. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_zone_range":["Historisch hohe Preisposition als Top-Merkmal. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Historically high price position as a top feature. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_zone_momentum_heat":["Sehr starkes positives Momentum als Überhitzungsmerkmal. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Very strong positive momentum as an overheating feature. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_zone_pi_cycle":["Nähe zum Pi-Cycle-Überhitzungsbereich. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Proximity to the Pi-Cycle overheating region. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_zone_acceleration":["Kurzfristiges Momentum beschleunigt stärker als langfristiges Momentum. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Short-term momentum accelerates more strongly than long-term momentum. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_zone_near_high":["Nähe zum Hoch des längeren Marktregimes. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Proximity to the high of the longer market regime. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_confirmation_rsi_divergence":["Bärische RSI-Divergenz: Preis bleibt hoch/steigt, RSI schwächt sich ab. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Bearish RSI divergence: price stays high/rises while RSI weakens. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_confirmation_return_divergence":["Bärische Momentum-Divergenz trotz hoher Preise. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Bearish momentum divergence despite high prices. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_confirmation_volatility_cooling":["Abkühlung nach einem Volatilitäts-/Euphorie-Spike. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Cooling after a volatility/euphoria spike. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_confirmation_trend_loss":["Verlust eines kurzen Trends nach Überdehnung. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Loss of a short trend after extension. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_confirmation_buying_exhaustion":["Nachlassender Kaufdruck nach einer starken Aufwärtsbewegung. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Fading buying pressure after a strong advance. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"turn_top_confirmation_price_rejection":["Deutliche Ablehnung vom jüngsten Hoch. Höher = dieses Merkmal prägt den jeweiligen Boden-/Top-Teilscore stärker; niedriger = schwächer; 0 = aus. Der Hauptscore bleibt davon unabhängig.","Clear rejection from the recent high. Higher = this feature shapes the respective bottom/top subscore more strongly; lower = less; 0 = off. The main score remains independent."],"model_minimum_history_points":["Mindestzahl an Kurstagen, bevor der Hauptscore überhaupt gültig wird. Höher = später verfügbar, dafür mehr Historie; niedriger = früher verfügbar, aber auf dünnerer Datenbasis.","Minimum price-history days before the main score becomes valid. Higher = available later with more history; lower = available earlier on thinner data."],"model_adaptive_window_days":["Länge des adaptiven Referenz-/Regimefensters für Perzentile und historische Einordnung. Höher = längeres Gedächtnis und trägere Anpassung; niedriger = stärker auf den jüngeren Markt fokussiert.","Length of the adaptive reference/regime window for percentiles and historical context. Higher = longer memory and slower adaptation; lower = more focused on the recent market."],"model_adaptive_min_reference_points":["Mindestzahl gültiger Punkte für adaptive Perzentile. Höher = strengere/stabilere Referenz, aber Signale später verfügbar; niedriger = früher und empfindlicher.","Minimum valid points for adaptive percentiles. Higher = stricter/more stable reference but later availability; lower = earlier and more sensitive."],"model_volatility_window_days":["Fenster für die annualisierte Volatilität, mit der Trend, Drawdown und Momentum normalisiert werden. Höher = glatter/träger; niedriger = reagiert schneller auf Regimewechsel.","Window for annualized volatility used to normalize trend, drawdown and momentum. Higher = smoother/slower; lower = reacts faster to regime changes."],"model_volatility_min_points":["Mindestdatenmenge für eine gültige Volatilitätsschätzung. Höher = robuster, aber später verfügbar; niedriger = früher, aber potenziell unruhiger.","Minimum data required for a valid volatility estimate. Higher = more robust but later; lower = earlier but potentially noisier."],"model_volatility_floor_pct":["Untergrenze der annualisierten Volatilität im Normalisierer. Höher = verhindert, dass ruhige Märkte kleine Bewegungen überbewerten und macht normalisierte Ausschläge kleiner; niedriger = ruhige Marktphasen reagieren empfindlicher.","Floor for annualized volatility in normalization. Higher = prevents quiet markets from over-amplifying small moves and reduces normalized extremes; lower = makes quiet regimes more sensitive."],"model_drawdown_window_days":["Zeitraum, in dem das lokale Hoch für den Drawdown gesucht wird. Höher = ältere Hochs bleiben länger relevant; niedriger = Fokus auf jüngere Rückgänge.","Period used to find the local high for drawdown. Higher = older highs remain relevant longer; lower = focuses on more recent declines."],"model_drawdown_min_points":["Mindestpunkte für den lokalen Drawdown. Höher = Drawdown-Signal startet später/stabiler; niedriger = früher verfügbar.","Minimum points for local drawdown. Higher = signal starts later/more stably; lower = available earlier."],"model_regime_high_min_points":["Mindestpunkte zur Bestimmung des Hochs im adaptiven Regimefenster. Höher = strengere Regimehistorie; niedriger = schneller verfügbar.","Minimum points used to determine the high in the adaptive regime window. Higher = stricter regime history; lower = available faster."],"model_percentile_window_days":["Fenster für die historische Preis-Perzentilposition. Höher = Vergleich mit längerer Historie; niedriger = stärker am jüngeren Preisband orientiert.","Window for historical price-percentile position. Higher = compares against longer history; lower = tracks the recent price range more closely."],"model_percentile_min_points":["Mindestpunkte für das Preis-Perzentil. Höher = stabiler/später; niedriger = früher/empfindlicher.","Minimum points for price percentile. Higher = more stable/later; lower = earlier/more sensitive."],"model_short_deviation_days":["Fenster für kurzfristige Mittelwert-/Z-Score-Abweichung. Höher = glatter und langsamer; niedriger = reagiert stärker auf kurze Dips/Spikes.","Window for short-term mean/z-score deviation. Higher = smoother/slower; lower = reacts more to short dips/spikes."],"model_trend_short_days":["Periode des kurzen Trend-MA. Höher = träger und weniger empfindlich; niedriger = schneller, aber rauschanfälliger.","Period of the short trend MA. Higher = slower/less sensitive; lower = faster but noisier."],"model_pi_short_days":["Kurze MA-Periode des Pi-Cycle-Verhältnisses. Höher = Pi-Cycle reagiert später/glatter; niedriger = früher/empfindlicher.","Short MA period of the Pi-Cycle ratio. Higher = Pi-Cycle reacts later/smoother; lower = earlier/more sensitive."],"model_trend_base_days":["Periode des Basis-MA für die langfristige Bewertung. Höher = längerfristige Perspektive; niedriger = reagiert schneller auf neue Trends.","Period of the base MA for long-term valuation. Higher = longer-term perspective; lower = reacts faster to new trends."],"model_pi_long_days":["Lange MA-Periode des Pi-Cycle-Verhältnisses. Höher = langsamere Zyklusreferenz; niedriger = schneller und näher am aktuellen Markt.","Long MA period of the Pi-Cycle ratio. Higher = slower cycle reference; lower = faster and closer to the current market."],"model_trend_mid_days":["Periode des Mitteltrend-MA für die Preisposition. Höher = längere Referenz; niedriger = kurzfristigere Referenz.","Period of the mid-trend MA for price position. Higher = longer reference; lower = shorter-term reference."],"model_trend_long_days":["Periode des Langzeit-MA. Höher = sehr träge Langfristbewertung; niedriger = reagiert früher auf Regimewechsel.","Period of the long-term MA. Higher = very slow long-term valuation; lower = reacts earlier to regime changes."],"model_trend_cycle_days":["Periode des Zyklus-MA. Höher = breiterer Mehrjahreszyklus und weniger kurzfristiger Einfluss; niedriger = Zyklusmodell reagiert früher.","Period of the cycle MA. Higher = broader multi-year cycle with less short-term influence; lower = cycle model reacts earlier."],"model_rsi_period_days":["RSI-Periode. Höher = glatter und langsamer; niedriger = empfindlicher auf kurzfristige Kursbewegungen.","RSI period. Higher = smoother/slower; lower = more sensitive to short-term moves."],"model_momentum_short_days":["Zeitraum für kurzes Momentum. Höher = weniger kurzfristig; niedriger = schnellere Reaktion auf Dips/Rallys.","Period for short momentum. Higher = less short-term; lower = faster response to dips/rallies."],"model_momentum_long_days":["Zeitraum für langes Momentum. Höher = stärker geglättet und zyklischer; niedriger = näher am aktuellen Markt.","Period for long momentum. Higher = more smoothed/cyclical; lower = closer to the current market."],"model_two_year_multiplier":["Multiplikator der oberen 2-Year-Bewertungsgrenze relativ zum Langzeit-MA. Höher = Obergrenze liegt weiter weg und Überhitzung wird später erkannt; niedriger = strengere/nähere Obergrenze.","Multiplier for the upper 2-Year valuation band relative to the long-term MA. Higher = farther upper band and later overheating detection; lower = stricter/closer band."],"model_power_law_min_points":["Mindesthistorie für die Power-Law-Schätzung. Höher = später, aber auf mehr Daten; niedriger = früher, jedoch instabiler.","Minimum history for the power-law fit. Higher = later but based on more data; lower = earlier but less stable."],"model_volatility_regime_low_ratio":["Grenze, unter der aktuelle Vola im Verhältnis zur historischen Referenz als „niedrig“ gilt. Höher = mehr Zustände werden als niedrige Vola eingestuft; niedriger = nur sehr ruhige Phasen.","Threshold below which current volatility versus historical reference is classified as low. Higher = more periods count as low-vol; lower = only very quiet periods."],"model_volatility_regime_high_ratio":["Grenze, über der aktuelle Vola relativ zur Referenz als „hoch“ gilt. Höher = nur extreme Vola gilt als hoch; niedriger = Hoch-Vola-Regime wird früher ausgelöst.","Threshold above which current volatility versus reference is classified as high. Higher = only extreme volatility counts as high; lower = high-vol regime triggers earlier."],"model_turning_point_lookback_days":["Rückblick für frühere Swing-Hochs/-Tiefs bei Divergenzen. Höher = ältere Vergleichspunkte erlaubt; niedriger = nur jüngere Wendepunkte.","Lookback for prior swing highs/lows used in divergences. Higher = allows older comparison points; lower = only recent turning points."],"model_turning_point_separation_days":["Mindestabstand zwischen zwei verglichenen Swing-Punkten. Höher = weniger, dafür klarer getrennte Divergenzen; niedriger = mehr und kurzfristigere Treffer.","Minimum separation between compared swing points. Higher = fewer but more clearly separated divergences; lower = more short-term matches."],"model_turning_zone_memory_days":["Wie lange eine starke Boden-/Top-Zone nachwirkt. Höher = Zone bleibt länger im Gedächtnis; niedriger = sie verfällt schneller.","How long a strong bottom/top zone remains active. Higher = longer memory; lower = faster decay."],"model_divergence_price_tolerance_pct":["Erlaubte Preisabweichung zwischen Swing-Punkten für Divergenzvergleiche. Höher = toleranter und mehr Divergenzen; niedriger = strenger und weniger Treffer.","Allowed price difference between swing points for divergence comparisons. Higher = more tolerant/more divergences; lower = stricter/fewer matches."],"model_volatility_fast_window_days":["Kurzes Volatilitätsfenster für Stress und Abkühlung. Höher = glatter/langsamer; niedriger = reagiert schneller auf Spikes.","Fast volatility window for stress/cooling. Higher = smoother/slower; lower = reacts faster to spikes."],"model_volatility_slow_window_days":["Langsames Vergleichsfenster der Volatilität. Höher = stabilere Langzeitbasis; niedriger = Referenz passt sich schneller an.","Slow comparison window for volatility. Higher = more stable long-run baseline; lower = baseline adapts faster."],"model_volatility_cooling_lookback_days":["Zeitraum, in dem nach einem vorherigen Vola-Spike für Abkühlung gesucht wird. Höher = ältere Spikes können noch bestätigen; niedriger = nur frische Spikes zählen.","Lookback in which a prior volatility spike can be followed by cooling. Higher = older spikes can still confirm; lower = only recent spikes count."],"model_exhaustion_short_days":["Kurzes Fenster für Käufer-/Verkäufer-Erschöpfung. Höher = breiter und glatter; niedriger = sehr kurzfristige Erschöpfung wird stärker erfasst.","Short window for buyer/seller exhaustion. Higher = broader/smoother; lower = emphasizes very short-term exhaustion."],"model_confirmation_zone_gate":["Bindet Bestätigungssignale an eine vorhandene Boden-/Top-Zone. Höher = Bestätigung wird ohne starke Zone stärker gedämpft; niedriger = Bestätigung arbeitet unabhängiger; 0 = keine Zonenbindung.","Gates confirmation signals by an existing bottom/top zone. Higher = confirmation is more suppressed without a strong zone; lower = more independent; 0 = no zone gating."],"model_turning_zone_threshold":["Schwelle, ab der eine Boden-/Top-Zone als relevant gilt. Höher = strengere, seltenere Zonen; niedriger = mehr/frühere Zonen.","Threshold at which a bottom/top zone becomes relevant. Higher = stricter/rarer zones; lower = more/earlier zones."],"model_turning_confirmation_threshold":["Schwelle, ab der die Bestätigung als erfüllt gilt. Höher = stärkere Bestätigung nötig; niedriger = leichter/früher bestätigt.","Threshold at which confirmation is considered met. Higher = stronger confirmation required; lower = easier/earlier confirmation."],"model_turning_extreme_threshold":["Schwelle für eine extreme Boden-/Top-Zone. Höher = nur sehr starke Extreme; niedriger = häufiger als extrem eingestuft.","Threshold for an extreme bottom/top zone. Higher = only very strong extremes; lower = more periods classified as extreme."],"threshold_very_expensive_max":["Obergrenze für „sehr hoch bewertet“. Höher = dieser Bereich reicht weiter nach oben und verschiebt die nächste Stufe nach oben; niedriger = „hoch bewertet“ beginnt früher.","Upper bound for “very highly valued”. Higher = this band extends upward and shifts the next band higher; lower = “highly valued” starts earlier."],"threshold_expensive_max":["Obergrenze für „hoch bewertet“. Höher = teure Einstufung reicht bis zu höheren Scores; niedriger = „interessant“ beginnt früher.","Upper bound for “highly valued”. Higher = expensive classification extends to higher scores; lower = “interesting” starts earlier."],"threshold_interesting":["Score ab dem „interessant“ beginnt. Höher = strengere Hürde und weniger Werte erreichen die Stufe; niedriger = Stufe wird früher erreicht.","Score where “interesting” begins. Higher = stricter hurdle and fewer readings reach it; lower = reached earlier."],"threshold_cheap":["Score ab dem „günstig“ beginnt. Höher = strengere Hürde; niedriger = mehr Marktphasen gelten als günstig.","Score where “cheap” begins. Higher = stricter hurdle; lower = more market periods count as cheap."],"threshold_very_cheap":["Score ab dem „sehr günstig“ beginnt. Höher = nur stärkere Setups; niedriger = häufiger „sehr günstig“.","Score where “very cheap” begins. Higher = only stronger setups; lower = “very cheap” occurs more often."],"threshold_extreme":["Score ab dem „extrem günstig“ beginnt. Höher = nur die seltensten Extremwerte; niedriger = Extremstatus wird leichter erreicht.","Score where “extremely cheap” begins. Higher = only the rarest extremes; lower = extreme status is easier to reach."]};

const t = key => I18N[state.lang][key] || key;
function historyCountSummary(counts = {}) {
  const entries = Object.entries(counts || {}).filter(([, count]) => Number.isFinite(Number(count)));
  if (!entries.length) return t("noData");
  return entries.map(([currency, count]) => `${currency}: ${fmtNumber(Number(count), 0)} ${t("dataPoints")}`).join(" · ");
}
const privateText = value => state.discreet ? "••••" : String(value ?? "–");
const privateHtml = value => esc(privateText(value));
function signedNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  const number = Number(value);
  const sign = number > 0 ? "+" : number < 0 ? "−" : "±";
  return `${sign}${fmtNumber(Math.abs(number), digits)}`;
}
function signedFiat(value, currency) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  const number = Number(value);
  const sign = number > 0 ? "+" : number < 0 ? "−" : "±";
  return `${sign}${fmtFiat(Math.abs(number), currency)}`;
}
function signedPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "–";
  const number = Number(value);
  const sign = number > 0 ? "+" : number < 0 ? "−" : "±";
  return `${sign}${fmtNumber(Math.abs(number), 2)} %`;
}
function todayKey() { return new Date().toISOString().slice(0, 10); }
function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  return new Intl.NumberFormat(state.lang === "de" ? "de-DE" : "en-US", {maximumFractionDigits:digits, minimumFractionDigits:Math.min(digits,2)}).format(Number(value));
}
function fmtFiat(value, currency) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  try { return new Intl.NumberFormat(state.lang === "de" ? "de-DE" : "en-US", {style:"currency",currency,maximumFractionDigits:2}).format(Number(value)); }
  catch { return `${fmtNumber(value,2)} ${currency}`; }
}
function fmtDate(value) {
  if (!value) return "–";
  const date = new Date(String(value).length === 10 ? `${value}T12:00:00Z` : value);
  return Number.isNaN(date.getTime()) ? String(value).slice(0,10) : new Intl.DateTimeFormat(state.lang === "de" ? "de-DE" : "en-US", {dateStyle:"medium"}).format(date);
}
function chartTimestamp(value) {
  if (!value) return NaN;
  const raw = String(value);
  if (chartTimestampCache.has(raw)) return chartTimestampCache.get(raw);
  const parsed = Date.parse(raw.length === 10 ? `${raw}T00:00:00Z` : raw);
  if (chartTimestampCache.size > 50000) chartTimestampCache.clear();
  chartTimestampCache.set(raw, parsed);
  return parsed;
}
function fmtChartPoint(value, intraday = false) {
  if (!value) return "–";
  const raw = String(value), date = new Date(raw.length === 10 ? `${raw}T12:00:00Z` : raw);
  if (Number.isNaN(date.getTime())) return raw;
  const locale = state.lang === "de" ? "de-DE" : "en-US";
  if (intraday || raw.length > 10) {
    return new Intl.DateTimeFormat(locale, {dateStyle:"medium", timeStyle:"short"}).format(date);
  }
  return new Intl.DateTimeFormat(locale, {dateStyle:"medium"}).format(date);
}
function calendarRangeStart(range) {
  const start = new Date();
  start.setHours(0,0,0,0);
  if (range === "week_start") { const offset=(start.getDay()+6)%7; start.setDate(start.getDate()-offset); return start.getTime(); }
  if (range === "month_start") { start.setDate(1); return start.getTime(); }
  if (range === "ytd") { start.setMonth(0,1); return start.getTime(); }
  return NaN;
}
function displayDaysForRange() {
  if (state.historyRange === "max" || state.historyRange === "first_purchase") return 0;
  if (state.historyRange === "1") return 1;
  if (["week_start","month_start","ytd"].includes(state.historyRange)) {
    const start=calendarRangeStart(state.historyRange);
    return Number.isFinite(start) ? Math.floor((Date.now()-start)/86400000)+1 : 1;
  }
  const requested = Number(state.historyRange) || 365;
  return requested > 0 ? requested : 365;
}
function historyDaysForRange() {
  const displayDays = displayDaysForRange();
  if (displayDays <= 0) return 0;
  // Always request one extra daily boundary. The 1-day intraday P/L chart
  // needs yesterday's end-of-day FIFO state so cost basis / realized P/L can
  // be projected onto the first 5-minute candle instead of starting with only
  // the single live point. The browser still trims the visible range exactly.
  return displayDays + 1;
}
function chartIntervalMinutesForRange() {
  // One fixed resolution per visible range. Longer ranges intentionally use the
  // durable daily cache and are uniformly compacted in the browser instead of
  // mixing dense recent candles with sparse older points.
  if (state.historyRange === "1") return 5;
  if (state.historyRange === "7" || state.historyRange === "week_start") return 30;
  if (state.historyRange === "30" || state.historyRange === "month_start") return 60;
  if (state.historyRange === "90") return 240;
  if (state.historyRange === "ytd" || state.historyRange === "365") return 720;
  return 1440;
}
function resampleSeriesUniform(values, intervalMinutes) {
  const interval = Math.max(1, Number(intervalMinutes) || 1440), bucketMs = interval * 60000;
  const buckets = new Map();
  for (const [key,rawValue] of Object.entries(filterSeriesToSelectedStart(values || {}))) {
    const timestamp = chartTimestamp(key), value = Number(rawValue);
    if (!Number.isFinite(timestamp) || !Number.isFinite(value)) continue;
    const bucket = Math.floor(timestamp / bucketMs) * bucketMs;
    const previous = buckets.get(bucket);
    if (!previous || timestamp >= previous.timestamp) buckets.set(bucket,{timestamp,value});
  }
  const result = {};
  for (const [bucket,item] of [...buckets.entries()].sort((a,b)=>a[0]-b[0])) {
    const bucketDate = new Date(bucket);
    const key = interval >= 1440 ? bucketDate.toISOString().slice(0,10) : new Date(item.timestamp).toISOString();
    result[key] = item.value;
  }
  return result;
}
function unitValue(btc) { return state.unit === "sats" ? Number(btc || 0) * SATS_PER_BTC : Number(btc || 0); }
function fmtStack(btc) { return state.unit === "sats" ? `${fmtNumber(unitValue(btc),0)} sats` : `${fmtNumber(btc,8)} BTC`; }
function rawUnitValue(btc) { return state.unit === "sats" ? Number(btc || 0) * SATS_PER_BTC : Number(btc || 0); }
function badge(status) { const label = status === "long_term" ? t("longTerm") : status === "short_term" ? t("shortTerm") : status === "mixed" ? t("mixed") : status === "consumed" ? t("consumed") : t("unknown"); return `<span class="badge ${esc(status)}">${esc(label)}</span>`; }
function toast(message) { const el = $("#toast"); el.textContent = message; el.classList.add("show"); setTimeout(() => el.classList.remove("show"), 2800); }
function fmtDateTime(value) {
  if (!value) return "–";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(state.lang === "de" ? "de-DE" : "en-US", {dateStyle:"medium",timeStyle:"short"}).format(date);
}
function updateBackupFileName() {
  const input = $("#backupFileInput"), label = $("#backupFileName");
  if (!label) return;
  label.textContent = input?.files?.[0]?.name || t("noFileSelected");
}
function updateDiscreetUi() {
  const hidden = state.discreet;
  for (const selector of ["#heroGoalCard", "#milestonesPanel", "#goalsStructurePanel"]) {
    const element = $(selector);
    if (element) element.classList.toggle("hidden", hidden);
  }
  const structureTab = $('.tabs button[data-tab="structure"]');
  if (structureTab) structureTab.textContent = hidden ? t("depots") : t("structure");
  const quick = $("#privacyButton");
  if (quick) {
    quick.classList.toggle("is-active", hidden);
    quick.setAttribute("aria-pressed", hidden ? "true" : "false");
    quick.title = hidden ? t("disableDiscreetMode") : t("enableDiscreetMode");
    quick.setAttribute("aria-label", quick.title);
  }
  updateChartMarkerButtons();
}
function renderActivePortfolioTab() {
  if (!state.data || state.data.locked) return;
  if (state.activeTab === "overview") renderOverview();
  else if (state.activeTab === "market") { renderBuyOpportunity(); renderBuyOpportunitySettings(); renderMarketAssessmentHistory(); void loadMarketAssessmentHistory(); }
  else if (state.activeTab === "ledger") renderLedger();
  else if (state.activeTab === "structure") { renderDepots(); if (!state.discreet) renderGoalsEditor(); }
  else if (state.activeTab === "tax") renderTax();
  else if (state.activeTab === "walletwatch") renderWalletWatch();
}
function renderDiscreetSensitiveViews() {
  // Privacy switching used to rebuild the complete app, including connection,
  // security and history panels and potentially thousands of ledger/FIFO rows.
  // Redraw only the currently visible portfolio tab. Other tabs are refreshed
  // when they are opened.
  renderActivePortfolioTab();
}
function applyDiscreetMode(enabled) {
  state.discreet = Boolean(enabled);
  localStorage.setItem("bst_discreet_mode", state.discreet ? "1" : "0");
  document.body.classList.toggle("discreet-mode", state.discreet);
  const toggle = $("#discreetMode");
  if (toggle) toggle.checked = state.discreet;
  updateDiscreetUi();
  if (state.data && !state.data.locked) {
    // Let the button/hidden goal panels update in the current frame first.
    requestAnimationFrame(() => {
      if (state.data && !state.data.locked) renderDiscreetSensitiveViews();
    });
  }
}
function localizeNetworkError(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  if (lower.includes("process and socks5 endpoint") || lower.includes("process is not running")) return t("torProcessUnavailable");
  if (lower.includes("starting") && lower.includes("tor")) return t("torStarting");
  if (lower.includes("socks5 connection was lost")) return t("torLost");
  if (lower.includes("timed out")) return t("torTimeout");
  if (lower.includes("control socket is not ready")) return t("torControlNotReady");
  if (lower.includes("still bootstrapping")) {
    const match = text.match(/\((\d{1,3})%\)/);
    return match ? `${t("torConnecting")} · ${match[1]} %` : t("torStarting");
  }
  return text;
}
function renderLeakTestResult() {
  const result = $("#leakTestResult");
  if (!result) return;
  result.classList.remove("positive","negative");
  if (!state.leakTest) { result.textContent = ""; return; }
  if (state.leakTest.status === "running") { result.textContent = t("leakTestRunning"); return; }
  if (state.leakTest.status === "passed") {
    result.textContent = t("leakTestPassed");
    result.classList.add("positive");
    return;
  }
  result.textContent = `${t("leakTestFailed")}: ${localizeNetworkError(state.leakTest.detail) || t("torError")}`;
  result.classList.add("negative");
}
function renderTorRotation() {
  const rotation = state.torRotation || {};
  const enabled = $("#torRotationEnabled"), interval = $("#torRotationInterval");
  if (enabled) enabled.checked = Boolean(rotation.enabled);
  if (interval && rotation.interval_minutes) interval.value = String(rotation.interval_minutes);
  const owner = Boolean(state.data?.security?.owner);
  for (const control of [enabled, interval, $("#saveTorRotationButton"), $("#newTorIdentityButton")]) if (control) control.disabled = !owner;
}
async function loadTorRotationSettings() {
  if (!state.data?.security?.owner) { state.torRotation = null; renderTorRotation(); return; }
  try {
    state.torRotation = await api(`api/tor/rotation-settings?entry_id=${encodeURIComponent(state.entryId)}`, {timeoutMs:5000});
  } catch (error) {
    state.torRotation = {...(state.torRotation || {}), last_error:error.message || String(error)};
  }
  renderTorRotation();
  renderNetworkStatus();
}
async function requestTorIdentity({withLeakTest=false}={}) {
  const rotateButton = $("#newTorIdentityButton"), leakButton = $("#leakTestButton"), result = $("#torRotationResult");
  if (rotateButton) rotateButton.disabled = true;
  if (leakButton) leakButton.disabled = true;
  if (result) { result.textContent = t("rotatingTor"); result.classList.remove("positive","negative"); }
  if (withLeakTest) { state.leakTest = {status:"running"}; renderLeakTestResult(); }
  try {
    const response = await api("api/tor/new-identity", {method:"POST",body:JSON.stringify({entry_id:state.entryId}),timeoutMs:70000});
    state.torRotation = response.rotation || state.torRotation;
    state.network = response.network || state.network;
    renderTorRotation();
    renderNetworkStatus();
    const previous = response.previous_exit_ip || "–", current = response.tor_exit_ip || "–";
    if (result) {
      result.textContent = response.ip_changed
        ? `${t("torIdentityChanged")}: ${previous} → ${current}`
        : `${t("torIdentityRequested")}: ${t("ipUnchanged")} (${current})`;
      result.classList.add("positive");
    }
    if (withLeakTest) await refreshNetworkStatus({force:true,interactive:true});
    else await refreshNetworkStatus({force:true,silent:true});
  } catch (error) {
    const detail = localizeNetworkError(error.message || String(error));
    if (result) { result.textContent = detail; result.classList.add("negative"); }
    if (withLeakTest) { state.leakTest = {status:"failed",detail}; renderLeakTestResult(); }
    toast(detail);
  } finally {
    const owner = Boolean(state.data?.security?.owner);
    if (rotateButton) rotateButton.disabled = !owner;
    if (leakButton) leakButton.disabled = !state.entryId;
  }
}

const NATIVE_PANEL = new URLSearchParams(window.location.search).get("native") === "1" && window.parent !== window;
const NATIVE_RPC_SOURCE = "bitcoin-stack-tracker-native";
const nativePending = new Map();
window.addEventListener("message", event => {
  if(!NATIVE_PANEL || event.source !== window.parent || event.origin !== window.location.origin)return;
  const message=event.data;
  if(!message || message.source!==NATIVE_RPC_SOURCE || message.type!=="response")return;
  const pending=nativePending.get(message.id);
  if(!pending)return;
  nativePending.delete(message.id);
  clearTimeout(pending.timer);
  if(message.error)pending.reject(new Error(message.error));
  else pending.resolve(message.payload ?? {});
});
function _bytesToBase64(bytes){
  const chunk=0x8000;let binary="";
  for(let i=0;i<bytes.length;i+=chunk)binary+=String.fromCharCode(...bytes.subarray(i,Math.min(i+chunk,bytes.length)));
  return btoa(binary);
}
async function _serializeNativeForm(form){
  const result=[];
  for(const [name,value] of form.entries()){
    if(value instanceof File){
      const bytes=new Uint8Array(await value.arrayBuffer());
      result.push({name,kind:"file",filename:value.name||"upload.bin",content_type:value.type||"application/octet-stream",data_base64:_bytesToBase64(bytes)});
    }else result.push({name,kind:"text",value:String(value)});
  }
  return result;
}
function openHomeAssistantMenu(){
  if(!NATIVE_PANEL)return;
  window.parent.postMessage({source:NATIVE_RPC_SOURCE,type:"ui-action",action:"open-menu"},window.location.origin);
}

async function nativeRpc(path, options={}){
  const id=(crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random()}`);
  const timeoutMs=Number(options.timeoutMs||35000);
  let form=null,bodyText=null,contentType="";
  if(options.body instanceof FormData){
    form=await _serializeNativeForm(options.body);
    contentType="multipart/form-data";
  }else if(options.body!==undefined&&options.body!==null){
    bodyText=String(options.body);
    contentType=String(options.headers?.["Content-Type"]||options.headers?.["content-type"]||"application/json");
  }
  const request={source:NATIVE_RPC_SOURCE,type:"request",id,path:String(path||""),method:String(options.method||"GET").toUpperCase(),content_type:contentType,body_text:bodyText,form};
  return await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{nativePending.delete(id);reject(new Error("Zeitüberschreitung bei Home Assistant Core"));},timeoutMs);
    nativePending.set(id,{resolve,reject,timer});
    window.parent.postMessage(request,window.location.origin);
  });
}

async function api(path, options = {}) {
  if(!NATIVE_PANEL){
    throw new Error("Bitcoin Stack Tracker muss über das native Home-Assistant-Seitenleistenpanel geöffnet werden.");
  }
  return nativeRpc(path,options);
}
function _base64ToBlob(data,mime){
  const binary=atob(String(data||"")),bytes=new Uint8Array(binary.length);
  for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
  return new Blob([bytes],{type:mime||"application/octet-stream"});
}
async function downloadApi(path, options={}, defaultName="download.bin"){
  if(!NATIVE_PANEL)throw new Error("Downloads sind nur über das native Home-Assistant-Panel erlaubt.");
  const result=await nativeRpc(path,options);
  const file=result?.__file__;
  if(!file?.data_base64)throw new Error("Home Assistant Core hat keine Download-Datei geliefert");
  const blob=_base64ToBlob(file.data_base64,file.mime),url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download=file.filename||defaultName;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
  return result;
}

async function service(name, data = {}, options = {}) {
  return api(`api/service/${name}`, {method:"POST", body:JSON.stringify(data), ...options});
}

async function hardenedUnlock(password) {
  return api(`api/vault/unlock?entry_id=${encodeURIComponent(state.entryId)}`, {
    method:"POST",
    headers:{"Content-Type":"text/plain; charset=utf-8"},
    body:String(password || ""),
    timeoutMs:60000
  });
}
async function hardenedEnableEncryption(password) {
  return api(`api/vault/enable?entry_id=${encodeURIComponent(state.entryId)}`, {
    method:"POST", headers:{"Content-Type":"text/plain; charset=utf-8"},
    body:String(password || ""), timeoutMs:60000
  });
}
async function hardenedDisableEncryption() {
  return api(`api/vault/disable?entry_id=${encodeURIComponent(state.entryId)}`, {
    method:"POST", body:"", timeoutMs:60000
  });
}
async function hardenedChangePassword(currentPassword,newPassword) {
  return api(`api/vault/change-password?entry_id=${encodeURIComponent(state.entryId)}`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({current_password:currentPassword,new_password:newPassword}), timeoutMs:60000
  });
}
function autoLockEligible(){
  return Boolean(state.data && !state.data.locked && state.data.security?.password_protected && state.autoLockMinutes > 0);
}
function renderAutoLock(){
  const block=$("#autoLockBlock"),select=$("#autoLockMinutes"),status=$("#autoLockStatus");
  const passwordMode=Boolean(state.data?.security?.password_protected);
  if(block)block.classList.toggle("hidden",!passwordMode);
  if(select)select.value=String(state.autoLockMinutes);
  if(!status)return;
  status.textContent=state.autoLockMinutes===0?t("autoLockDisabled"):`${t("autoLockActive")} · ${state.autoLockMinutes} min`;
}
function sharedLastActivity(){
  const shared=Number(localStorage.getItem("bst_last_activity_at")||0);
  return Math.max(Number(state.lastActivityAt||0),Number.isFinite(shared)?shared:0);
}
function scheduleAutoLock(){
  if(autoLockTimer){clearTimeout(autoLockTimer);autoLockTimer=null;}
  if(!autoLockEligible())return;
  state.lastActivityAt=sharedLastActivity();
  const idleMs=Math.max(0,Date.now()-state.lastActivityAt);
  const delay=Math.max(1000,state.autoLockMinutes*60000-idleMs);
  autoLockTimer=setTimeout(()=>performAutoLock(),delay);
}
async function syncCoreAutoLock({touch=true,silent=true}={}){
  if(!state.entryId||!state.data||state.data.locked||!state.data.security?.password_protected)return;
  try{
    const result=await api("api/security/session",{method:"POST",body:JSON.stringify({entry_id:state.entryId,auto_lock_minutes:state.autoLockMinutes,touch:Boolean(touch)}),timeoutMs:10000});
    coreActivitySyncAt=Date.now();
    if(state.data?.security){
      state.data.security.auto_lock_minutes=result.auto_lock_minutes;
      state.data.security.unlock_expires_in_seconds=result.unlock_expires_in_seconds;
      state.data.security.core_auto_lock=true;
    }
    const confirmed=Number(result?.auto_lock_minutes);
    if([0,5,15,30,60,120].includes(confirmed)){
      state.autoLockMinutes=confirmed;
      localStorage.setItem("bst_auto_lock_minutes",String(confirmed));
      renderAutoLock();
      scheduleAutoLock();
    }
  }catch(error){if(!silent)toast(error.message||String(error));}
}
function queueCoreActivitySync(){
  if(!autoLockEligible())return;
  const elapsed=Date.now()-coreActivitySyncAt;
  if(elapsed>=30000){void syncCoreAutoLock({touch:true,silent:true});return;}
  if(coreActivitySyncTimer)return;
  coreActivitySyncTimer=setTimeout(()=>{coreActivitySyncTimer=null;void syncCoreAutoLock({touch:true,silent:true});},Math.max(1000,30000-elapsed));
}
function recordUserActivity(){
  state.lastActivityAt=Date.now();
  localStorage.setItem("bst_last_activity_at",String(state.lastActivityAt));
  scheduleAutoLock();
  queueCoreActivitySync();
}
async function performAutoLock(){
  if(autoLockInFlight||!autoLockEligible())return;
  state.lastActivityAt=sharedLastActivity();
  if(Date.now()-state.lastActivityAt < state.autoLockMinutes*60000){scheduleAutoLock();return;}
  autoLockInFlight=true;
  try{
    await service("lock_vault",{config_entry_id:state.entryId});
    toast(t("autoLockTriggered"));
    state.lastActivityAt=Date.now();
    await loadData();
  }catch(error){
    toast(error.message||String(error));
    state.lastActivityAt=Date.now();
    scheduleAutoLock();
  }finally{autoLockInFlight=false;}
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  document.querySelector('meta[name="theme-color"]').content = state.theme === "dark" ? "#090a0d" : "#f2f3f5";
  $("#themeButton").textContent = state.theme === "dark" ? "☀" : "☾";
  localStorage.setItem("bst_theme", state.theme);
}
function updateVaultGateText() {
  if (!state.data?.locked) return;
  $("#vaultGateText").textContent = state.data.security?.setup_required ? t("vaultSetupText") : t("vaultLockedText");
}
function updateCurrentUserLabel() {
  if (!state.user) return;
  const name = String(state.user.user_name || state.user.user_id || "–").trim() || "–";
  const initial = (name.match(/[\p{L}\p{N}]/u)?.[0] || "?").toUpperCase();
  $("#currentUserAvatar").textContent = initial;
  $("#currentUserName").textContent = name;
  $("#currentUser").title = name;
  $("#currentUser").setAttribute("aria-label", `Home Assistant user: ${name}`);
}
function applyLanguage() {
  document.documentElement.lang = state.lang;
  $$('[data-i18n]').forEach(element => { const value = I18N[state.lang][element.dataset.i18n]; if (value) element.textContent = value; });
  $("#ledgerSearch").placeholder = t("search");
  updateCurrentUserLabel();
  updateVaultGateText();
  if(state.editingEntryId){const title=$("#transactionFormTitle"),submit=$("#transactionSubmit");if(title)title.textContent=t("editEntry");if(submit)submit.textContent=t("saveChanges");}
  localStorage.setItem("bst_lang", state.lang);
  updateBackupFileName();
  updateCsvFileName();
  const csvLeft=$("#csvScrollLeft"),csvRight=$("#csvScrollRight");
  if(csvLeft){csvLeft.title=t("scrollTableLeft");csvLeft.setAttribute("aria-label",t("scrollTableLeft"));}
  if(csvRight){csvRight.title=t("scrollTableRight");csvRight.setAttribute("aria-label",t("scrollTableRight"));}
  renderLeakTestResult();
  renderTorRotation();
  updateDiscreetUi();
  if (state.csvImport) renderCsvImportPreview();
  if (state.data && !state.data.locked) renderAll();
}
function applyUnit() {
  $("#unitButton").textContent = state.unit;
  $("#ledgerAmountHead").textContent = state.unit;
  $("#fifoAmountHead").textContent = state.unit;
  const amountUnit = $("#transactionForm select[name=amount_unit]");
  const goalUnit = $("#goalForm select[name=goal_unit]");
  if (amountUnit) amountUnit.value = state.unit;
  if (goalUnit) goalUnit.value = state.unit;
  localStorage.setItem("bst_unit", state.unit);
  if (state.data && !state.data.locked) renderAll();
}

function activateTab(tabName, {store=true, loadLog=false, render=true}={}) {
  const requested = String(tabName || "overview");
  const button = $(`.tabs button[data-tab="${requested}"]`) || $('.tabs button[data-tab="overview"]');
  const selected = button?.dataset.tab || "overview";
  $$('.tabs button').forEach(item => item.classList.toggle('active', item === button));
  $$('.tab').forEach(item => item.classList.toggle('active', item.id === `tab-${selected}`));
  state.activeTab = selected;
  if (selected !== "overview") cancelScheduledPerformanceSummary();
  if (store) localStorage.setItem("bst_active_tab", selected);
  if (render && state.data && !state.data.locked) renderActiveTabContent(selected);
  if (state.data && !state.data.locked) ensureActiveTabData(selected);
  if (loadLog && selected === "logs") loadLogs();
  if (selected === "settings" && !document.hidden) {
    void refreshNetworkStatus({silent:true});
    void refreshConnectionInventory({silent:true});
  }
}

async function boot() {
  try {
    state.user = await api("api/whoami");
    updateCurrentUserLabel();
    const response = await api("api/portfolios");
    state.portfolios = response.portfolios || [];
    if (!state.portfolios.length) throw new Error(t("noAccess"));
    $("#portfolioSelect").innerHTML = state.portfolios.map(item => `<option value="${esc(item.config_entry_id)}">${esc(item.title)}</option>`).join("");
    state.entryId = localStorage.getItem("bst_entry") || state.portfolios[0].config_entry_id;
    if (!state.portfolios.some(item => item.config_entry_id === state.entryId)) state.entryId = state.portfolios[0].config_entry_id;
    $("#portfolioSelect").value = state.entryId;
    $("#historyRange").value = state.historyRange;
    $("#chartMode").value = state.chartMode;
    $("#overlayOpacity").value = String(state.overlayOpacity);
    if ($("#overlayOpacityValue")) $("#overlayOpacityValue").textContent = `${state.overlayOpacity} %`;
    await loadData();
    if(state.data && !state.data.locked && state.data.security?.password_protected){
      await syncCoreAutoLock({touch:true,silent:true});
    }
    await loadTorRotationSettings();
    startNetworkPolling();
    startMarketAssessmentPolling();
    startLivePricePolling();
    startWalletWatchStatusPolling();
    await refreshLivePrice({silent:true});
    await refreshMarketAssessment({silent:true});
  } catch (error) {
    $("#fatal").textContent = errorText(error);
    $("#fatal").classList.remove("hidden");
  }
}

function updateChartMarkerButtons() {
  const milestone = $("#chartMilestonesButton"), halving = $("#chartHalvingsButton");
  if (milestone) {
    const active = state.showMilestones && !state.discreet;
    milestone.classList.toggle("is-active", active);
    milestone.classList.toggle("hidden", state.discreet);
    milestone.setAttribute("aria-pressed", active ? "true" : "false");
    milestone.title = t("chartMilestones");
  }
  if (halving) {
    halving.classList.toggle("is-active", state.showHalvings);
    halving.setAttribute("aria-pressed", state.showHalvings ? "true" : "false");
    halving.disabled = state.halvingsLoading;
    halving.title = state.halvingsError ? `${t("halvingLoadError")}: ${state.halvingsError}` : t("chartHalvings");
  }
}

function estimatedNextHalvingMs(info = state.halvingInfo) {
  const blocks = Number(info?.blocks_to_next_halving);
  if (!Number.isFinite(blocks) || blocks < 0) return NaN;
  const checked = new Date(info?.checked_at || Date.now()).getTime();
  if (!Number.isFinite(checked)) return NaN;
  return checked + blocks * 10 * 60 * 1000;
}
function halvingCountdownText(targetMs) {
  if (!Number.isFinite(targetMs)) return "–";
  let seconds = Math.max(0, Math.floor((targetMs - Date.now()) / 1000));
  const days = Math.floor(seconds / 86400); seconds -= days * 86400;
  const hours = Math.floor(seconds / 3600); seconds -= hours * 3600;
  const minutes = Math.floor(seconds / 60);
  const years = Math.floor(days / 365);
  const restDays = days - years * 365;
  if (years > 0) return `${years} J · ${restDays} T · ${hours} Std`;
  if (days > 0) return `${days} T · ${hours} Std · ${minutes} Min`;
  return `${hours} Std · ${minutes} Min`;
}
function renderBitcoinNetworkStrip() {
  const strip = $("#bitcoinNetworkStrip");
  if (!strip) return;
  const info = state.halvingInfo || {};
  const tip = Number(info.tip_height);
  const nextHeight = Number(info.next_halving_height);
  const blocks = Number(info.blocks_to_next_halving);
  const targetMs = estimatedNextHalvingMs(info);
  const currency = currentCurrency();
  const fiatPrice = Number(state.data?.prices?.[currency]);
  const moscow = Number.isFinite(fiatPrice) && fiatPrice > 0 ? SATS_PER_BTC / fiatPrice : NaN;
  $("#heroBlockHeight").textContent = Number.isFinite(tip) ? fmtNumber(tip,0) : "–";
  $("#heroMoscowTime").textContent = Number.isFinite(moscow) ? fmtNumber(moscow,0) : "–";
  const moscowUnit = $("#heroMoscowUnit");
  if (moscowUnit) moscowUnit.textContent = `sats / ${currency}`;
  $("#heroHalvingCountdown").textContent = halvingCountdownText(targetMs);
  $("#heroHalvingBlocks").textContent = Number.isFinite(blocks) ? `${fmtNumber(blocks,0)} ${t("blocksLabel")}` : "–";
  $("#heroHalvingEstimate").textContent = Number.isFinite(targetMs) ? fmtDateTime(new Date(targetMs).toISOString()) : "–";
  $("#heroHalvingHeight").textContent = Number.isFinite(nextHeight) ? `${t("nextHalvingBlock")}: ${fmtNumber(nextHeight,0)} · ${t("tenMinuteEstimate")}` : "–";
  $("#bitcoinNetworkSource").textContent = info?.source ? `${t("networkDataSource")}: ${info.source}` : (state.halvingsError || "–");
}
function startBitcoinNetworkTicker() {
  if (window.__bstBitcoinNetworkTicker) clearInterval(window.__bstBitcoinNetworkTicker);
  window.__bstBitcoinNetworkTicker = setInterval(() => {
    renderBitcoinNetworkStrip();
    if (!state.entryId || state.data?.locked || state.halvingsLoading) return;
    if (Date.now() - bitcoinNetworkRefreshAt >= 60 * 1000) void loadHalvings({force:true});
  }, 15000);
}

async function loadHalvings({force=false}={}) {
  if (!state.entryId || !state.data || state.data.locked || state.halvingsLoading) return false;
  if (!force && state.halvingsEntryId === state.entryId && state.halvings.length) return true;
  const requestedEntry = state.entryId;
  state.halvingsLoading = true;
  state.halvingsError = "";
  updateChartMarkerButtons();
  try {
    const suffix = force ? "&force=1" : "";
    const result = await api(`api/chart/halvings?entry_id=${encodeURIComponent(requestedEntry)}${suffix}`, {timeoutMs:120000});
    if (requestedEntry !== state.entryId) return false;
    state.halvings = Array.isArray(result?.halvings) ? result.halvings : [];
    state.halvingInfo = result && typeof result === "object" ? result : null;
    bitcoinNetworkRefreshAt = Date.now();
    state.halvingsEntryId = requestedEntry;
    state.halvingsError = Array.isArray(result?.errors) && result.errors.length && !state.halvings.length ? result.errors.join(" · ") : "";
    renderBitcoinNetworkStrip();
    if (state.activeTab === "overview") renderChart();
    return true;
  } catch (error) {
    if (requestedEntry === state.entryId) state.halvingsError = errorText(error);
    renderBitcoinNetworkStrip();
    return false;
  } finally {
    state.halvingsLoading = false;
    updateChartMarkerButtons();
  }
}

async function loadData() {
  const requestedEntry = state.entryId;
  const previousEntry = state.data?.portfolio?.config_entry_id || "";
  resetDashboardSections();
  const requestedRevision = dashboardLoadRevision;
  if (previousEntry && previousEntry !== requestedEntry) {
    // Do not leave another portfolio's sensitive values visible while the new
    // authenticated summary is in flight.
    state.data = null;
    $("#app")?.classList.add("hidden");
  }
  const summary = await api(`api/dashboard?entry_id=${encodeURIComponent(requestedEntry)}&section=summary&history_days=${historyDaysForRange()}&history_interval=${chartIntervalMinutesForRange()}`);
  if (requestedEntry !== state.entryId || requestedRevision !== dashboardLoadRevision) return;
  state.data = summary;
  state.dashboardSections.summary = true;
  invalidateDerivedCaches();
  state.securityUsers = [];
  state.connectionInventory = state.data?.connection_inventory || null;
  if (state.data?.addon_network) {
    state.network = state.data.addon_network;
  } else if (!state.network) {
    state.network = {tor_connection_state:"connecting",tor_verified:false};
  }
  renderNetworkStatus();
  void refreshNetworkStatus({silent:true});
  if (state.data.locked) {
    clearLazySensitiveViews();
    state.walletWatch = null;
    state.walletWatchLoading = false;
    state.walletWatchTxOverviews = {};
    const walletWatchList = $("#walletWatchMonitors"); if (walletWatchList) walletWatchList.innerHTML = "";
    const walletWatchStatus = $("#walletWatchStatus"); if (walletWatchStatus) walletWatchStatus.innerHTML = "";
    $("#app").classList.add("hidden");
    $("#vaultGate").classList.remove("hidden");
    $("#lockButton").classList.add("hidden");
    updateVaultGateText();
    if(autoLockTimer){clearTimeout(autoLockTimer);autoLockTimer=null;}
    renderAutoLock();
    return;
  }
  $("#vaultGate").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#lockButton").classList.toggle("hidden", !state.data.security?.password_protected);
  if (state.activeTab === "security" && state.data.security?.owner) {
    const response = await api(`api/security/users?entry_id=${encodeURIComponent(state.entryId)}`);
    state.securityUsers = response.users || [];
  }
  renderAll();
  renderTorRotation();
  scheduleAutoLock();
  activateTab(state.activeTab, {store:false, loadLog:false, render:false});
  ensureActiveTabData(state.activeTab);
  void loadHalvings();
}

async function ensureIntradayHistory({force=false,interactive=false} = {}) {
  if (intradayBootstrapInFlight || !state.entryId || !state.data || state.data.locked) return false;
  const requestedDays = historyDaysForRange(), displayDays = displayDaysForRange();
  if (!state.data.history?.enabled || requestedDays <= 0 || requestedDays > 731) return false;
  const currency = currentCurrency(), interval = chartIntervalMinutesForRange();
  if (interval >= 1440) return false;
  const marketInterval = Number(state.data.history?.market_interval_minutes || 0);
  const market = marketInterval === interval ? (state.data.history?.market_candles?.[currency] || {}) : {};
  const points = sortedNumericPoints(market);
  const targetDays = Math.max(1, displayDays || requestedDays);
  const cutoff = Date.now() - targetDays * 86400000;
  const expected = Math.max(2, Math.ceil(targetDays * 1440 / interval));
  const firstTime = points.length ? chartTimestamp(points[0].day) : NaN;
  const lastTime = points.length ? chartTimestamp(points.at(-1).day) : NaN;
  const enoughDensity = points.length >= Math.max(2, Math.floor(expected * 0.94));
  const enoughCoverage = Number.isFinite(firstTime) && Number.isFinite(lastTime)
    && firstTime <= cutoff + interval * 60000 * 3
    && lastTime >= Date.now() - interval * 60000 * 3
    && enoughDensity;
  if (!force && enoughCoverage) return true;

  const key = `${state.entryId}:${currency}:${targetDays}:${interval}`;
  const lastAttempt = Number(intradayBootstrapLastAttempt.get(key) || 0);
  if (!force && Date.now() - lastAttempt < 30000) return false;
  intradayBootstrapLastAttempt.set(key,Date.now());
  intradayBootstrapInFlight = true;
  const button = $("#refreshChartPrices");
  if (button) button.disabled = true;
  if (interactive) toast(t("refreshingChartPrices"));
  try {
    const result = await api("api/history/intraday", {
      method:"POST",
      body:JSON.stringify({entry_id:state.entryId,history_days:targetDays,interval_minutes:interval}),
      timeoutMs:180000
    });
    const count = Number(result?.sample_counts?.[currency] || 0);
    if (result?.errors?.length && count < 2) throw new Error(result.errors.join(" · "));
    if (count < 2) throw new Error(`Keine ${interval}-Minuten-Kerzen für ${currency} erhalten`);
    intradayBootstrapLastAttempt.delete(key);
    await loadData();
    if (interactive) toast(`${t("chartPricesRefreshed")} · ${interval < 60 ? `${interval} min` : `${interval/60} h`} · ${count}`);
    return true;
  } catch (error) {
    const detail = errorText(error);
    let dailyFallbackCount = Object.keys(filterSeriesToSelectedStart(state.data?.history?.prices?.[currency] || {})).length;
    console.warn("Bitcoin Stack exact chart candle refresh failed", detail);
    if (interval === 720 && dailyFallbackCount < 2 && interactive) {
      try {
        await service("sync_history",{config_entry_id:state.entryId},{timeoutMs:300000});
        await loadData();
        dailyFallbackCount = Object.keys(filterSeriesToSelectedStart(state.data?.history?.prices?.[currency] || {})).length;
      } catch (fallbackError) {
        console.warn("Bitcoin Stack daily fallback refresh failed",errorText(fallbackError));
      }
    }
    const dailyFallbackAvailable = interval === 720 && dailyFallbackCount >= 2;
    if (interactive) toast(dailyFallbackAvailable ? t("chartDailyFallback") : `${t("chartPriceRefreshFailed")}: ${detail}`);
    if (dailyFallbackAvailable) { renderOverview(); return true; }
    return false;
  } finally {
    intradayBootstrapInFlight = false;
    if (button) button.disabled = false;
  }
}

async function refreshChartPrices() {
  const interval = chartIntervalMinutesForRange(), days = displayDaysForRange();
  if (interval < 1440 && days > 0 && days <= 731) {
    await ensureIntradayHistory({force:true,interactive:true});
    return;
  }
  const button = $("#refreshChartPrices");
  if (button) button.disabled = true;
  toast(t("historySyncRunning"));
  try {
    const result = await service("sync_history",{config_entry_id:state.entryId},{timeoutMs:300000});
    if (result?.errors?.length) console.warn("Bitcoin Stack history refresh notes",result.errors);
    await loadData();
    toast(`${t("chartPricesRefreshed")} · ${historyCountSummary(result?.cached_daily_values || {})}`);
  } catch (error) {
    toast(`${t("chartPriceRefreshFailed")}: ${errorText(error)}`);
  } finally { if (button) button.disabled = false; }
}


function availableChartCurrencies() {
  const data = state.data || {}, history = data.history || {}, chart = history.chart || {};
  const values = new Set([
    ...(data.currencies || []),
    ...Object.keys(data.prices || {}),
    ...Object.keys(history.prices || {}),
    ...Object.keys(chart.portfolio_value || {})
  ].map(code => String(code || "").toUpperCase()).filter(Boolean));
  return [...values].sort((left, right) => {
    const priority = code => code === "EUR" ? 0 : code === "USD" ? 1 : 2;
    return priority(left) - priority(right) || left.localeCompare(right);
  });
}
function currentCurrency() {
  const currencies = availableChartCurrencies();
  return $("#chartCurrency").value || state.chartCurrency || currencies[0] || "EUR";
}
function uiIndexes() {
  const cacheKey=derivedCacheKey("uiIndexes");
  if(derivedCache.has(cacheKey))return derivedCache.get(cacheKey);
  const data=state.data||{},fifo=data.fifo||{};
  const depotNames=new Map((data.depots||[]).map(item=>[String(item.id),item.name]));
  const entryById=new Map((data.entries||[]).map(entry=>[String(entry.id),entry]));
  const openLotByEntry=new Map((fifo.open_lots||[]).map(lot=>[String(lot.entry_id),lot]));
  const matchesBySale=new Map();
  for(const [saleId,statuses] of Object.entries(fifo.match_statuses_by_sale||{})){
    matchesBySale.set(String(saleId),(Array.isArray(statuses)?statuses:[]).map(status=>({status})));
  }
  for(const match of (fifo.matches||[])){
    const key=String(match.sale_id||"");if(!key)continue;
    let rows=matchesBySale.get(key);if(!rows){rows=[];matchesBySale.set(key,rows);}rows.push(match);
  }
  const reversedMatches=[...(fifo.matches||[])].reverse();
  const result={depotNames,entryById,openLotByEntry,matchesBySale,reversedMatches};
  derivedCache.set(cacheKey,result);
  return result;
}
function depotName(id) { return uiIndexes().depotNames.get(String(id)) || id; }
function entryHoldingDetails(entry) {
  const fifo=state.data?.fifo||{},indexes=uiIndexes();
  if (entry.type === "sale") {
    const sale=fifo.sales?.[entry.id]||{}, matches=indexes.matchesBySale.get(String(entry.id))||[];
    const statuses=new Set(matches.map(item=>item.status));
    let reason="";
    if(sale.status==="insufficient_stack"||statuses.has("insufficient_stack"))reason=t("holdingReasonInsufficient");
    else if(statuses.has("currency_conversion_required"))reason=t("holdingReasonCurrency");
    else if(statuses.has("unknown_cost_basis"))reason=t("holdingReasonUnknownCost");
    else if((sale.holding_status||"unknown")==="unknown")reason=t("holdingReasonUnknown");
    return {status:sale.holding_status||"unknown",reason};
  }
  if (entry.type === "expense") {
    const expense=fifo.expenses?.[entry.id]||{}, status=expense.holding_status||"unknown";
    return {status,reason:expense.status==="insufficient_stack"?t("holdingReasonInsufficient"):(status==="unknown"?t("holdingReasonUnknown"):"")};
  }
  const lot=indexes.openLotByEntry.get(String(entry.id));
  if(lot)return {status:lot.holding_status||"unknown",reason:(lot.holding_status||"unknown")==="unknown"?t("holdingReasonUnknown"):""};
  return {status:"consumed",reason:t("holdingReasonConsumed")};
}
function entryHolding(entry) { return entryHoldingDetails(entry).status; }
function entryHoldingHtml(entry) { const detail=entryHoldingDetails(entry),showReason=detail.reason&&detail.status==="unknown"; return `${badge(detail.status)}${showReason?`<small class="ledger-status-reason" title="${esc(detail.reason)}">${esc(detail.reason)}</small>`:""}`; }

function applyStaticSelects() {
  const currencies = state.data.currencies || [];
  const currencyOptions = currencies.map(code => `<option value="${esc(code)}">${esc(code)}</option>`).join("");
  const depotOptions = state.data.depots.map(item => `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join("");
  $$('select[name="currency"]').forEach(select => { const old = select.value; select.innerHTML = currencyOptions; if (currencies.includes(old)) select.value = old; });
  $("#transactionForm select[name=depot_id]").innerHTML = depotOptions;
  const csvDepot = $("#csvDefaultDepot");
  if (csvDepot) {
    const oldCsvDepot = csvDepot.value;
    csvDepot.innerHTML = depotOptions;
    csvDepot.value = state.data.depots.some(item => item.id === oldCsvDepot) ? oldCsvDepot : (state.data.depots[0]?.id || "main");
  }
  $("#goalForm select[name=depot_id]").innerHTML = `<option value="all">${esc(t("allDepots"))}</option>${depotOptions}`;
  const chart = $("#chartCurrency");
  const chartCurrencies = availableChartCurrencies();
  const oldChartCurrency = chart.value || state.chartCurrency;
  chart.innerHTML = chartCurrencies.map(code => `<option value="${esc(code)}">${esc(code)}</option>`).join("");
  const selectedChartCurrency = chartCurrencies.includes(oldChartCurrency) ? oldChartCurrency : chartCurrencies[0] || "EUR";
  chart.value = selectedChartCurrency;
  state.chartCurrency = selectedChartCurrency;
  localStorage.setItem("bst_chart_currency", selectedChartCurrency);
  const transactionUnit = $("#transactionForm select[name=amount_unit]");
  transactionUnit.value = state.unit; transactionUnit.dataset.previousUnit = state.unit;
  $("#goalForm select[name=goal_unit]").value = state.unit;
  updateTransactionFiatLabel();
}

function renderActiveTabContent(selected = state.activeTab) {
  if (!state.data || state.data.locked) return;
  if (selected === "overview") renderOverview();
  else if (selected === "market") { renderBuyOpportunity(); renderBuyOpportunitySettings(); renderMarketAssessmentHistory(); void loadMarketAssessmentHistory(); }
  else if (selected === "ledger") {
    if (!dashboardSectionLoaded("ledger")) renderLazyTabPlaceholder("ledger");
    else renderLedger();
  }
  else if (selected === "structure") { renderDepots(); if (!state.discreet) renderGoalsEditor(); }
  else if (selected === "tax") {
    if (!dashboardSectionLoaded("fifo")) renderLazyTabPlaceholder("tax");
    else renderTax();
  }
  else if (selected === "walletwatch") {
    renderWalletWatch();
    if (!state.walletWatch && !state.walletWatchLoading) void loadWalletWatch();
  }
  else if (selected === "settings") { renderHistorySettings(); renderNetworkStatus(); renderConnections(); renderTorRotation(); renderLeakTestResult(); renderBackupHealth(); }
  else if (selected === "security") {
    renderSecurity();
    if (state.data?.security?.owner && !state.securityUsers.length) {
      void api(`api/security/users?entry_id=${encodeURIComponent(state.entryId)}`).then(response => {
        state.securityUsers = response.users || [];
        if (state.activeTab === "security") renderSecurity();
      }).catch(() => {});
    }
  }
}

function renderAll() {
  applyStaticSelects();
  const discreetToggle = $("#discreetMode");
  if (discreetToggle) discreetToggle.checked = state.discreet;
  updateDiscreetUi();
  const taxNote = String(state.data.tax_settings.note || "").trim();
  $("#taxDisclaimer").textContent = taxNote ? `${taxNote} · ${t("holdingDisclaimer")}` : t("holdingDisclaimer");
  $("#taxForm").long_term_days.value = state.data.tax_settings.long_term_days || 365;
  $("#taxForm").tax_note.value = state.data.tax_settings.note || "";
  // Heavy views (chart, ledger, FIFO tables) are rendered only when visible.
  // This avoids rebuilding every hidden tab after each save/refresh.
  renderActiveTabContent(state.activeTab);
}

function lifetimeFiatSecured(currency) {
  const code=String(currency||"").toUpperCase();
  const aggregate=state.data?.purchase_totals?.[code];
  if(aggregate){
    const fiat=Number(aggregate.fiat||0),btc=Number(aggregate.btc||0),fees=Number(aggregate.fees||0),count=Number(aggregate.count||0);
    return {fiat,btc,fees,count,totalOutlay:Number(aggregate.total_outlay ?? (fiat+fees))};
  }
  const purchases = chartLedgerEntries().filter(entry => entry?.type === "purchase" && String(entry?.currency || "").toUpperCase() === code);
  const result = purchases.reduce((summary, entry) => {
    const amount = Number(entry?.amount_btc || 0), price = Number(entry?.price || 0), fee = Number(entry?.fee || 0);
    if (Number.isFinite(amount) && amount > 0 && Number.isFinite(price) && price > 0) {
      summary.fiat += amount * price; summary.btc += amount; summary.count += 1;
      if (Number.isFinite(fee) && fee > 0) summary.fees += fee;
    }
    return summary;
  }, {fiat:0, btc:0, fees:0, count:0});
  result.totalOutlay = result.fiat + result.fees;
  return result;
}

function renderOverview() {
  const data = state.data, fifo = data.fifo, currency = currentCurrency(), rawPrice = data.prices[currency];
  const total = Number(fifo.total_btc || 0), value = rawPrice == null ? null : total * Number(rawPrice);
  const lots = (fifo.open_lots || []).filter(lot => lot.currency === currency);
  const invested = lots.reduce((sum, lot) => sum + Number(lot.remaining_btc || 0) * Number(lot.unit_basis || 0), 0);
  const known = lots.reduce((sum, lot) => sum + Number(lot.remaining_btc || 0), 0);
  const unrealized = rawPrice == null ? null : known * Number(rawPrice) - invested;
  const realized = Number(fifo.realized?.[currency] || 0);
  const secured = lifetimeFiatSecured(currency),activity=metricCurrency(currency).activity||{},sales=activity.sales||{},expenses=activity.expenses||{},income=activity.income||{},networkFees=activity.network_fees||{};
  const activityFees=item=>Number(item?.fees_fiat||0)+Number(item?.btc_fee_fiat||0);
  const realizedTotal=Number(activity.realized_total??realized);
  const cards = [
    [t("totalStack"), fmtStack(total), state.unit === "BTC" ? `${fmtNumber(total * SATS_PER_BTC,0)} sats` : `${fmtNumber(total,8)} BTC`, ""],
    [t("totalValue"), fmtFiat(value,currency), `${fmtFiat(rawPrice,currency)} / BTC`, ""],
    [t("openBasis"), fmtFiat(invested,currency), `${fmtStack(known)} · ${t("openBasisHint")}`, ""],
    [t("unrealized"), fmtFiat(unrealized,currency), `${t("realized")}: ${fmtFiat(realized,currency)}`, unrealized > 0 ? "positive" : unrealized < 0 ? "negative" : ""],
    [t("realizedTotal"), fmtFiat(realizedTotal,currency), `${t("salesSummary")}: ${fmtFiat(Number(sales.realized||0),currency)} · ${t("expensesSummary")}: ${fmtFiat(Number(expenses.realized||0),currency)} · ${t("networkFeeEffect")}: ${fmtFiat(Number(networkFees.realized||0),currency)}`, realizedTotal>0?"positive":realizedTotal<0?"negative":""],
    [t("salesSummary"), fmtStack(Number(sales.btc||0)), `${t("saleProceeds")}: ${fmtFiat(Number(sales.value||0),currency)} · ${t("fee")}: ${fmtFiat(activityFees(sales),currency)} · ${t("realizedCategory")}: ${fmtFiat(Number(sales.realized||0),currency)}`, ""],
    [t("expensesSummary"), fmtStack(Number(expenses.btc||0)), `${t("expenseValue")}: ${fmtFiat(Number(expenses.value||0),currency)} · ${t("fee")}: ${fmtFiat(activityFees(expenses),currency)} · ${t("realizedCategory")}: ${fmtFiat(Number(expenses.realized||0),currency)}`, ""],
    [t("incomeSummary"), fmtStack(Number(income.btc||0)), `${t("incomeValue")}: ${fmtFiat(Number(income.value||0),currency)} · ${t("fee")}: ${fmtFiat(activityFees(income),currency)}`, ""],
    [t("networkFeesSummary"), fmtStack(Number(networkFees.btc||0)), `${t("networkFeeValue")}: ${fmtFiat(Number(networkFees.value||0),currency)} · ${t("onchain")}: ${fmtStack(Number(networkFees.onchain_btc||0))} · ${t("lightning")}: ${fmtStack(Number(networkFees.lightning_btc||0))}`, ""],
    [t("fiatSecured"), fmtFiat(secured.fiat,currency), `${t("purchaseFees")}: ${fmtFiat(secured.fees,currency)} · ${t("purchaseOutlay")}: ${fmtFiat(secured.totalOutlay,currency)}`, ""]
  ];
  $("#summaryCards").innerHTML = cards.map(([label,value,sub,css]) => `<article class="metric-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong><small>${privateHtml(sub)}</small></article>`).join("");
  $("#heroLong").textContent = privateText(fmtStack(fifo.long_term_btc));
  const nextGoal = (data.goals || []).filter(goal => Number(goal.remaining_btc) > 0).sort((a,b) => Number(a.remaining_btc) - Number(b.remaining_btc))[0];
  $("#heroGoal").textContent = nextGoal ? `${nextGoal.name}: ${privateText(fmtStack(nextGoal.remaining_btc))}` : "✓";
  $("#heroText").textContent = state.lang === "de"
    ? `Lokales Bitcoin-Buch mit Käufen, Einnahmen, Verkäufen, Ausgaben und Netzwerkgebühren, depotweisem FIFO, ${data.tax_settings.long_term_days} Tagen Haltezeit-Regel und dauerhaft gespeichertem Tagesverlauf.`
    : `Local Bitcoin ledger with purchases, income, sales, expenses and network fees, per-depot FIFO, a ${data.tax_settings.long_term_days}-day holding rule, and durable daily history.`;
  renderChart();
  renderGoalCards();
}

function goalReachedAtFromEntries(goal) {
  const target = Number(goal?.amount_btc || 0);
  if (!(target > 0)) return null;
  const scope = String(goal?.depot_id || "all");
  const rows = chartLedgerEntries()
    .filter(row => scope === "all" || String(row?.depot_id || "main") === scope)
    .map(row => ({
      row,
      time: new Date(row?.timestamp || "").getTime(),
      outgoing: ["sale", "expense", "network_fee"].includes(String(row?.type || ""))
    }))
    .filter(item => Number.isFinite(item.time))
    .sort((a, b) => a.time - b.time || Number(a.outgoing) - Number(b.outgoing) || String(a.row?.id || "").localeCompare(String(b.row?.id || "")));
  let balance = 0;
  for (const item of rows) {
    const amount = Math.max(0, Number(item.row?.amount_btc || 0));
    const kind=String(item.row?.type || "");
    if (["purchase", "income", "stack"].includes(kind)) balance += amount;
    else if (["sale", "expense", "network_fee"].includes(kind)) balance -= amount;
    if (kind !== "network_fee" && item.row?.fee_btc_affects_stack) balance -= Math.max(0,Number(item.row?.fee_btc || 0));
    if (balance + 1e-12 >= target) return String(item.row?.timestamp || "") || null;
  }
  return null;
}

function sortedStackingGoals(goals = state.data?.goals || []) {
  const amount = goal => { const value = Number(goal?.amount_btc); return Number.isFinite(value) && value >= 0 ? value : Number.POSITIVE_INFINITY; };
  return [...goals].sort((left,right) => amount(left) - amount(right) || String(left?.name || "").localeCompare(String(right?.name || ""), state.lang === "de" ? "de" : "en", {sensitivity:"base"}));
}

function renderGoalCards() {
  const target = $("#goalCards");
  if (!target) return;
  if (state.discreet) {
    target.innerHTML = "";
    return;
  }
  const goals = sortedStackingGoals();
  target.innerHTML = goals.length ? goals.map(goal => {
    const targetBtc = Number(goal.amount_btc || 0);
    const current = Number(goal.current_btc || 0);
    const rawProgress = targetBtc > 0 ? Math.max(0, current / targetBtc * 100) : 0;
    const currentlyReached = Boolean(goal.is_reached ?? (targetBtc > 0 && current + 1e-12 >= targetBtc));
    const displayProgress = currentlyReached ? 100 : Math.min(99.9, rawProgress);
    const ringProgress = Math.min(100, rawProgress);
    const ringCircumference = 2 * Math.PI * 50;
    const ringDash = ringCircumference * ringProgress / 100;
    const ringGap = Math.max(0, ringCircumference - ringDash);
    const reachedAt = goal.goal_reached_at || goalReachedAtFromEntries(goal);
    const reached = reachedAt
      ? `<div class="goal-reached ${currentlyReached ? "" : "was-reached"}"><span>✓ ${esc(t("goalReachedAt"))}</span><strong>${esc(fmtDateTime(reachedAt))}</strong></div>`
      : "";
    return `<article class="goal-card ${currentlyReached ? "is-reached" : ""}">
      <div class="goal-ring" role="img" aria-label="${esc(`${fmtNumber(displayProgress,1)}%`)}">
        <svg class="goal-ring-svg" viewBox="0 0 120 120" aria-hidden="true">
          <circle class="goal-ring-track" cx="60" cy="60" r="50"></circle>
          ${ringProgress > 0 ? `<circle class="goal-ring-progress" cx="60" cy="60" r="50" stroke-dasharray="${ringDash} ${ringGap}"></circle>` : ""}
        </svg>
        <strong>${privateHtml(`${fmtNumber(displayProgress,1)}%`)}</strong>
      </div>
      <div><span class="kicker">${esc(goal.currency)} · ${esc(goal.depot_id === "all" ? t("allDepots") : depotName(goal.depot_id))}</span><h3>${esc(goal.name)}</h3>
        <div class="goal-values">
          <div><span>${esc(t("current"))}</span><strong>${privateHtml(fmtStack(goal.current_btc))}</strong></div>
          <div><span>${esc(t("target"))}</span><strong>${privateHtml(fmtStack(goal.amount_btc))}</strong></div>
          <div><span>${esc(t("remaining"))} ${esc(state.unit)}</span><strong>${privateHtml(fmtStack(goal.remaining_btc))}</strong></div>
          <div><span>${esc(t("remaining"))} ${esc(goal.currency)}</span><strong>${privateHtml(fmtFiat(goal.remaining_fiat,goal.currency))}</strong></div>
        </div>${reached}
      </div></article>`;
  }).join("") : `<p>${esc(t("noData"))}</p>`;
}

function firstPortfolioActivityDay() {
  const cacheKey = derivedCacheKey("firstPortfolioActivityDay");
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const entries = chartLedgerEntries();
  let firstPurchase = Number.POSITIVE_INFINITY, firstBooking = Number.POSITIVE_INFINITY;
  for (const entry of entries) {
    const timestamp = chartTimestamp(entry?.timestamp);
    if (!Number.isFinite(timestamp)) continue;
    if (timestamp < firstBooking) firstBooking = timestamp;
    if (entry?.type === "purchase" && timestamp < firstPurchase) firstPurchase = timestamp;
  }
  const selected = Number.isFinite(firstPurchase) ? firstPurchase : firstBooking;
  const result = Number.isFinite(selected) ? new Date(selected).toISOString().slice(0,10) : null;
  derivedCache.set(cacheKey,result);
  return result;
}

function filterSeriesToSelectedStart(values) {
  let entries = Object.entries(values || {});
  const now = Date.now();
  if (state.historyRange === "1") {
    const cutoff = now - 24 * 60 * 60 * 1000;
    entries = entries.filter(([day]) => chartTimestamp(day) >= cutoff);
  } else if (["week_start","month_start","ytd"].includes(state.historyRange)) {
    const cutoff=calendarRangeStart(state.historyRange);
    if (Number.isFinite(cutoff)) entries = entries.filter(([day]) => chartTimestamp(day) >= cutoff);
  } else if (/^\d+$/.test(String(state.historyRange || ""))) {
    const days = Number(state.historyRange);
    if (days > 0) {
      const cutoff = now - days * 24 * 60 * 60 * 1000;
      entries = entries.filter(([day]) => chartTimestamp(day) >= cutoff);
    }
  } else if (state.historyRange === "first_purchase") {
    const startDay = firstPortfolioActivityDay();
    if (startDay) entries = entries.filter(([day]) => String(day) >= startDay);
  }
  return Object.fromEntries(entries);
}
function seriesValuationTimestamp(key) {
  const raw = String(key || "");
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return Date.parse(`${raw}T23:59:59.999Z`);
  return chartTimestamp(raw);
}

function eventStepSeries(values, endOfDay = true) {
  const result = {};
  for (const [key,value] of Object.entries(values || {})) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) continue;
    const raw = String(key);
    // Daily FIFO chart snapshots represent end-of-day state. Treating them as
    // midnight state made a DCA look as if it had already happened all day.
    result[raw.length === 10 && endOfDay ? `${raw}T23:59:59.999Z` : raw] = numeric;
  }
  return result;
}
function projectStepSeries(source, targetKeys) {
  const sourcePoints = sortedNumericPoints(source), targets = [...targetKeys].sort((a,b)=>seriesValuationTimestamp(a)-seriesValuationTimestamp(b));
  const result = {};
  let position = 0, current = null;
  for (const key of targets) {
    const target = seriesValuationTimestamp(key);
    while (position < sourcePoints.length && seriesValuationTimestamp(sourcePoints[position].day) <= target) {
      current = sourcePoints[position].value;
      position += 1;
    }
    if (current !== null) result[key] = current;
  }
  return result;
}
function ledgerStackAndPortfolio(priceSeries) {
  const entries = chartLedgerEntries()
    .map(entry => ({entry,time:chartTimestamp(entry?.timestamp),amount:Number(entry?.amount_btc || 0)}))
    .filter(item => Number.isFinite(item.time) && Number.isFinite(item.amount) && item.amount > 0)
    .sort((a,b)=>a.time-b.time);
  const points = sortedNumericPoints(priceSeries), stackBtc = {}, portfolio = {};
  let position = 0, stack = 0, started = false;
  for (const point of points) {
    const timestamp = seriesValuationTimestamp(point.day);
    while (position < entries.length && entries[position].time <= timestamp) {
      const {entry,amount} = entries[position];
      if (["purchase","income","stack"].includes(entry.type)) stack += amount;
      else if (["sale","expense","network_fee"].includes(entry.type)) stack -= amount;
      if (entry.type !== "network_fee" && entry.fee_btc_affects_stack) stack -= Math.max(0,Number(entry.fee_btc || 0));
      stack = Math.max(0,stack);
      started = true;
      position += 1;
    }
    if (!started) continue;
    stackBtc[point.day] = stack;
    portfolio[point.day] = stack * point.value;
  }
  return {stackBtc,portfolio};
}
function fifoMetricEvents(currency) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const cacheKey = derivedCacheKey("fifoMetricEvents", selectedCurrency);
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const outgoingKinds=["sale","expense","network_fee"];
  const entries = chartLedgerEntries()
    .map((entry,index) => ({entry,index,time:chartTimestamp(entry?.timestamp)}))
    .filter(item => Number.isFinite(item.time))
    .sort((left,right) => left.time-right.time
      || Number(outgoingKinds.includes(left.entry?.type))-Number(outgoingKinds.includes(right.entry?.type))
      || String(left.entry?.id || "").localeCompare(String(right.entry?.id || ""))
      || left.index-right.index);
  const lotsByDepot = new Map(), cursorByDepot = new Map();
  let realized = 0, basis = 0, knownBtc = 0;
  const result = [];
  let sequence = 0;
  const consume=(depot,amount,currency,price,fee=0,zeroProceeds=false)=>{
    if (!(amount>0)) return;
    const lots=lotsByDepot.get(depot)||[]; let cursor=Number(cursorByDepot.get(depot)||0),remaining=amount;
    while(cursor<lots.length&&remaining>1e-15){
      const lot=lots[cursor]; if(!(lot.remaining>1e-15)){cursor+=1;continue;}
      const take=Math.min(remaining,lot.remaining);
      if(lot.currency===selectedCurrency&&Number.isFinite(lot.unitBasis)&&lot.unitBasis>=0){
        const cost=take*lot.unitBasis; basis-=cost; knownBtc-=take;
        if(zeroProceeds) realized-=cost;
        else if(currency===selectedCurrency&&Number.isFinite(price)&&price>0){
          const feeShare=Number.isFinite(fee)?Math.max(0,fee)*(take/amount):0;
          realized+=take*price-feeShare-cost;
        }
      }
      lot.remaining-=take; remaining-=take; if(!(lot.remaining>1e-15))cursor+=1;
    }
    cursorByDepot.set(depot,cursor);
  };
  for (const item of entries) {
    const entry=item.entry||{},kind=String(entry.type||""),depot=String(entry.depot_id||"main");
    const amount=Math.max(0,Number(entry.amount_btc||0));
    if (!(amount > 0)) continue;
    const lots=lotsByDepot.get(depot)||[]; lotsByDepot.set(depot,lots); if(!cursorByDepot.has(depot))cursorByDepot.set(depot,0);
    const entryCurrency=String(entry.currency||"").toUpperCase(),entryPrice=Number(entry.price),fiatFee=Math.max(0,Number(entry.fee||0));
    if (["purchase","income","stack"].includes(kind)) {
      if (["purchase","income"].includes(kind)) {
        const unitBasis=Number.isFinite(entryPrice)&&entryPrice>0?(amount*entryPrice+fiatFee)/amount:null;
        lots.push({remaining:amount,currency:entryCurrency,unitBasis});
        if(entryCurrency===selectedCurrency&&Number.isFinite(unitBasis)&&unitBasis>=0){basis+=amount*unitBasis;knownBtc+=amount;}
      } else lots.push({remaining:amount,currency:null,unitBasis:null});
    } else if (["sale","expense"].includes(kind)) {
      consume(depot,amount,entryCurrency,entryPrice,fiatFee,false);
    } else if (kind === "network_fee") {
      consume(depot,amount,entryCurrency,entryPrice,0,true);
    }
    if(kind!=="network_fee" && entry.fee_btc_affects_stack){
      const feeBtc=Math.max(0,Number(entry.fee_btc||0)); if(feeBtc>0)consume(depot,feeBtc,entryCurrency,entryPrice,0,true);
    }
    if (Math.abs(basis) < 1e-10) basis = 0;
    if (Math.abs(knownBtc) < 1e-15) knownBtc = 0;
    const key = new Date(item.time + sequence).toISOString();
    result.push({time:item.time,key,basis,realized,knownBtc});
    sequence = (sequence + 1) % 997;
  }
  derivedCache.set(cacheKey,result);
  return result;
}
function chartValues(currency, analytics = false) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const cacheKey = derivedCacheKey("chartValues", selectedCurrency, analytics ? "analytics" : "display", state.historyRange, chartIntervalMinutesForRange());
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);

  const history = state.data.history || {}, chart = history.chart || {}, fifo = state.data.fifo || {};
  currency = selectedCurrency;
  const interval = chartIntervalMinutesForRange();
  const marketInterval = Number(history.market_interval_minutes || 0);
  const exactMarket = marketInterval === interval ? (history.market_candles?.[currency] || {}) : {};
  const exactCount = Object.keys(exactMarket).length;
  const usingExactIntraday = interval < 1440 && exactCount >= 2;
  const dailyFallback = history.prices?.[currency] || {};
  // Never splice two resolutions together. YTD/1y may fall back wholesale to
  // daily closes if the 12h Bitstamp tier is unavailable; every longer range is
  // compacted from the daily cache to one uniform bucket size for the whole chart.
  const rawPrice = usingExactIntraday ? {...exactMarket} : {...dailyFallback};
  const livePrice = Number(state.data.prices?.[currency]), nowIso = new Date().toISOString();
  if (Number.isFinite(livePrice) && livePrice > 0) {
    if (usingExactIntraday) rawPrice[nowIso] = livePrice;
    else rawPrice[nowIso.slice(0,10)] = livePrice;
  }
  const effectiveInterval = usingExactIntraday ? interval : 1440;
  const price = effectiveInterval < 1440
    ? resampleSeriesUniform(rawPrice,effectiveInterval)
    : (analytics ? resampleSeriesUniform(rawPrice,1440) : resampleLongRangeUniform(rawPrice));
  const {stackBtc,portfolio} = ledgerStackAndPortfolio(price);

  const currencySummary = fifo.currency_summaries?.[String(currency).toUpperCase()] || {};
  const invested = Number(currencySummary.invested || 0);
  const knownBtc = Number(currencySummary.known_btc || 0);
  const realizedNow = Number(currencySummary.realized_gain ?? fifo.realized?.[currency] ?? 0);

  const intradayGrid = effectiveInterval < 1440;
  const basisEvents = eventStepSeries(chart.open_cost_basis?.[currency] || {},intradayGrid);
  const realizedEvents = eventStepSeries(chart.realized_profit_loss?.[currency] || {},intradayGrid);
  const knownEvents = {};
  const dailyBasis = chart.open_cost_basis?.[currency] || {};
  const dailyUnrealized = chart.unrealized_profit_loss?.[currency] || {};
  const dailyPrices = history.prices?.[currency] || {};
  for (const [day,rawBasis] of Object.entries(dailyBasis)) {
    const basis = Number(rawBasis), unrealized = Number(dailyUnrealized?.[day]), dayPrice = Number(dailyPrices?.[day]);
    if (!Number.isFinite(basis) || !Number.isFinite(unrealized) || !Number.isFinite(dayPrice) || dayPrice <= 0) continue;
    const cleanDay=String(day).slice(0,10);
    knownEvents[intradayGrid?`${cleanDay}T23:59:59.999Z`:cleanDay] = Math.max(0,(basis + unrealized) / dayPrice);
  }
  if (intradayGrid) {
    const todayStart = Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), new Date().getUTCDate());
    const now = Date.now();
    const metricEvents = fifoMetricEvents(currency).filter(item => item.time >= todayStart && item.time <= now);
    for (const item of metricEvents) {
      basisEvents[item.key] = item.basis;
      realizedEvents[item.key] = item.realized;
      knownEvents[item.key] = item.knownBtc;
    }
    if (!Object.keys(basisEvents).length) basisEvents[nowIso] = invested;
    if (!Object.keys(realizedEvents).length) realizedEvents[nowIso] = realizedNow;
    if (!Object.keys(knownEvents).length) knownEvents[nowIso] = knownBtc;
  } else {
    const currentMetricKey=nowIso.slice(0,10);
    basisEvents[currentMetricKey] = invested;
    realizedEvents[currentMetricKey] = realizedNow;
    knownEvents[currentMetricKey] = knownBtc;
  }

  const grid = Object.keys(price);
  const costBasis = projectStepSeries(basisEvents,grid);
  const realizedProfitLoss = projectStepSeries(realizedEvents,grid);
  const knownBtcOnGrid = projectStepSeries(knownEvents,grid);
  const unrealizedProfitLoss = {}, totalProfitLoss = {};
  for (const [key,rawMarketPrice] of Object.entries(price)) {
    const basis = Number(costBasis[key]), tracked = Number(knownBtcOnGrid[key]), marketPrice = Number(rawMarketPrice);
    const realized = Number(realizedProfitLoss[key]);
    if (Number.isFinite(basis) && Number.isFinite(tracked) && Number.isFinite(marketPrice)) {
      unrealizedProfitLoss[key] = tracked * marketPrice - basis;
      totalProfitLoss[key] = unrealizedProfitLoss[key] + (Number.isFinite(realized) ? realized : 0);
    } else if (Number.isFinite(realized)) {
      totalProfitLoss[key] = realized;
    }
  }

  const result = {price,portfolio,totalProfitLoss,unrealizedProfitLoss,realizedProfitLoss,costBasis,stackBtc};
  derivedCache.set(cacheKey,result);
  return result;
}

function analyticsValues(currency) { return chartValues(currency,true); }

function seriesChange(values) {
  const points = sortedNumericPoints(values);
  if (points.length < 2) return null;
  const startPoint = points[0], endPoint = points.at(-1);
  const start = Number(startPoint.value), end = Number(endPoint.value), absolute = end - start;
  const percent = start === 0 ? null : absolute / Math.abs(start) * 100;
  return {startDay:startPoint.day,endDay:endPoint.day,start,end,absolute,percent};
}

function compactAxis(value) {
  return new Intl.NumberFormat(state.lang === "de" ? "de-DE" : "en-US", {notation:"compact",maximumFractionDigits:1}).format(Number(value));
}
function chartAxisScale(index) {
  return index === 0 ? state.chartScaleLeft : state.chartScaleRight;
}
function setChartAxisScale(index, value) {
  const normalized = value === "log" ? "log" : "linear";
  if (index === 0) {
    state.chartScaleLeft = normalized;
    localStorage.setItem("bst_chart_scale_left", normalized);
  } else {
    state.chartScaleRight = normalized;
    localStorage.setItem("bst_chart_scale_right", normalized);
  }
}
function updateChartScaleButtons(series = []) {
  for (const index of [0,1]) {
    const button = $(`#chartScale${index === 0 ? "Left" : "Right"}Button`);
    const text = $(`#chartScale${index === 0 ? "Left" : "Right"}Text`);
    if (!button || !text) continue;
    const item = series[index];
    const unavailable = !item;
    const logBlocked = Boolean(item?.allowNegative || item?.forceLinear);
    if (logBlocked && chartAxisScale(index) === "log") setChartAxisScale(index,"linear");
    const label = chartAxisScale(index) === "log" ? t("logarithmic") : t("linear");
    text.textContent = `${index === 0 ? "L" : "R"} · ${label}`;
    button.classList.toggle("hidden", unavailable);
    button.disabled = unavailable || logBlocked;
    button.classList.toggle("is-disabled", unavailable || logBlocked);
    const axisLabel = index === 0 ? t("leftAxis") : t("rightAxis");
    button.title = logBlocked ? `${axisLabel}: ${t(item?.forceLinear?"marketScoreLinearOnly":"logUnavailable")}` : `${axisLabel}: ${label}`;
    button.setAttribute("aria-label", button.title);
  }
}
function renderChartLegend(series) {
  const legend = $("#chartLegend");
  if (!legend) return;
  const overlay = series.length > 1;
  legend.setAttribute("aria-label", t("chartLegend"));
  legend.innerHTML = series.map((item,index) => `<div class="chart-legend-item">
    <span class="chart-legend-swatch ${index ? "secondary" : "primary"}"${index ? ` style="opacity:${state.overlayOpacity / 100}"` : ""} aria-hidden="true"></span>
    <span class="chart-legend-label">${esc(item.label)}</span>
    ${overlay ? `<small>${esc(index ? t("rightAxis") : t("leftAxis"))}</small>` : ""}
  </div>`).join("");
}
function chartMilestoneEvents() {
  if (!state.showMilestones || state.discreet) return [];
  const events=[];
  for(const goal of (state.data?.goals||[])){
    const reachedAt=goal?.goal_reached_at;
    const timestamp=chartTimestamp(reachedAt);
    if(!Number.isFinite(timestamp))continue;
    events.push({kind: "milestone",timestamp,icon: "★",label:`${goal.name} · ${fmtStack(goal.amount_btc)}`});
  }
  return events;
}

function chartHalvingEvents() {
  if (!state.showHalvings) return [];
  return (state.halvings || []).map(item => {
    const timestamp = chartTimestamp(item?.timestamp || item?.date);
    return {
      kind: "halving",
      timestamp,
      icon: "₿",
      label: `${t("halvingMarker")} #${Number(item?.number || 0)} · ${t("blockHeight")} ${Number(item?.height || 0).toLocaleString(state.lang === "de" ? "de-DE" : "en-US")}`,
    };
  }).filter(item => Number.isFinite(item.timestamp));
}

function smoothMarketAssessmentPoints(points,windowSize=state.marketAssessmentHistorySmoothing){
  const rows=Array.isArray(points)?points:[],window=Math.max(1,Number(windowSize)||1);
  if(window<=1)return rows.map(point=>({...point,raw_score:Number(point?.score),display_score:Number(point?.score)}));
  const alpha=2/(window+1);let ema=null;
  return rows.map(point=>{
    const raw=Number(point?.score);
    if(Number.isFinite(raw))ema=ema==null?raw:(alpha*raw+(1-alpha)*ema);
    return {...point,raw_score:raw,display_score:ema==null?raw:ema};
  });
}
function marketAssessmentPointTimestamp(point,payload,index,total,{capTime=null}={}){
  const day=String(point?.date||"").slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return NaN;
  const calculated=chartTimestamp(payload?.calculated_at),calculatedDay=Number.isFinite(calculated)?new Date(calculated).toISOString().slice(0,10):"";
  if(index===total-1&&day===calculatedDay&&Number.isFinite(calculated))return Number.isFinite(capTime)?Math.min(calculated,capTime):calculated;
  return Date.parse(`${day}T23:59:59.999Z`);
}
function marketAssessmentSmoothingLabel(){
  const window=Number(state.marketAssessmentHistorySmoothing||1);
  return window<=1?walletWatchLang("Aus","Off"):walletWatchLang(`EMA ${window} Punkte`,`EMA ${window} points`);
}
function resetMarketAssessmentChartDisplayDefaults(){
  state.marketAssessmentHistoryRange="3y";
  state.marketAssessmentHistoryPriceOverlay=true;
  state.marketAssessmentHistoryPriceScale="log";
  state.marketAssessmentHistoryPriceOpacity=55;
  state.marketAssessmentHistorySmoothing=5;
  localStorage.setItem("bst_market_assessment_history_range",state.marketAssessmentHistoryRange);
  localStorage.setItem("bst_market_assessment_history_price_overlay","1");
  localStorage.setItem("bst_market_assessment_history_price_scale","log");
  localStorage.setItem("bst_market_assessment_history_price_opacity","55");
  localStorage.setItem("bst_market_assessment_history_smoothing","5");
  state.marketAssessmentHistory=null;invalidateDerivedCaches();renderMarketAssessmentHistory();
  if(state.activeTab==="market")void loadMarketAssessmentHistory({force:true});
  if(state.activeTab==="overview"&&state.chartMode==="price_market"){renderChart();void ensureChartMarketAssessmentHistory({force:true});}
  toast(t("marketHistoryDisplayReset"));
}

function chartMarketAssessmentRangeKey(){
  const map={"1":"1d","week_start":"week_start","7":"7d","month_start":"month_start","30":"30d","90":"90d","ytd":"ytd","365":"1y","1095":"3y","1825":"5y","3650":"10y","first_purchase":"max","max":"max"};
  return map[String(state.historyRange||"365")]||"1y";
}
function chartMarketAssessmentPayloadReady(){
  const payload=state.chartMarketAssessmentHistory;
  return Boolean(payload&&payload._entry_id===state.entryId&&payload._requested_range===chartMarketAssessmentRangeKey());
}
function chartMarketAssessmentOverlayValues(priceValues){
  if(!chartMarketAssessmentPayloadReady())return {};
  const payload=state.chartMarketAssessmentHistory,points=smoothMarketAssessmentPoints(Array.isArray(payload?.points)?payload.points:[]);
  const priceRows=Object.keys(priceValues||{}).map(key=>({key,time:chartTimestamp(key)})).filter(row=>Number.isFinite(row.time)).sort((a,b)=>a.time-b.time);
  if(!points.length||!priceRows.length)return {};
  const firstPriceTime=priceRows[0].time,lastPriceTime=priceRows.at(-1).time;
  const scorePoints=points.map((point,index)=>({time:marketAssessmentPointTimestamp(point,payload,index,points.length,{capTime:lastPriceTime}),score:Number(point?.display_score)})).filter(point=>Number.isFinite(point.time)&&Number.isFinite(point.score)).sort((a,b)=>a.time-b.time);
  if(!scorePoints.length)return {};
  const nearestPriceRow=target=>{let lo=0,hi=priceRows.length-1;while(lo<hi){const mid=Math.floor((lo+hi)/2);if(priceRows[mid].time<target)lo=mid+1;else hi=mid;}if(lo>0&&Math.abs(priceRows[lo-1].time-target)<=Math.abs(priceRows[lo].time-target))return priceRows[lo-1];return priceRows[lo];};
  const visible=scorePoints.filter(point=>point.time>=firstPriceTime&&point.time<=lastPriceTime);
  const previous=[...scorePoints].reverse().find(point=>point.time<firstPriceTime);
  if(previous)visible.unshift({...previous,time:firstPriceTime});
  const result={};
  for(const point of visible){const row=nearestPriceRow(point.time);result[row.key]=point.score;}
  // Do not forward-fill every intraday BTC candle with the same daily score.
  // Sparse causal score samples are connected by the chart, which preserves
  // the visible score movement instead of rendering a misleading flat band.
  if(Object.keys(result).length===1&&scorePoints.length>=2){
    const current=scorePoints.at(-1),prior=scorePoints.at(-2);
    result[priceRows[0].key]=prior.score;
    result[nearestPriceRow(Math.min(current.time,lastPriceTime)).key]=current.score;
  }
  return result;
}
async function ensureChartMarketAssessmentHistory({force=false}={}){
  if(state.chartMarketAssessmentHistoryLoading||!state.entryId||!state.data)return false;
  const range=chartMarketAssessmentRangeKey(),entryId=state.entryId;
  if(!force&&chartMarketAssessmentPayloadReady())return true;
  state.chartMarketAssessmentHistoryLoading=true;
  try{
    const payload=await api(`api/market-assessment/history?entry_id=${encodeURIComponent(entryId)}&range=${encodeURIComponent(range)}`,{timeoutMs:180000});
    if(entryId!==state.entryId||!payload)return false;
    state.chartMarketAssessmentHistory={...payload,_entry_id:entryId,_requested_range:range};
    invalidateDerivedCaches();
    if(state.activeTab==="overview"&&(state.chartMode==="price_market"||$("#chartMode")?.value==="price_market"))renderChart();
    return true;
  }catch(error){console.warn("Bitcoin Stack market-assessment chart overlay failed",errorText(error));return false;}
  finally{state.chartMarketAssessmentHistoryLoading=false;}
}

function renderChart() {
  updateChartMarkerButtons();
  if (!dashboardSectionLoaded("chart")) {
    const element=$("#chart"); if(element)element.innerHTML=`<p class="storage-note">${esc(t("loadingChart"))}</p>`;
    updateChartScaleButtons([]);
    void ensureDashboardSection("chart");
    return;
  }
  const currency = currentCurrency(), mode = $("#chartMode").value || state.chartMode;
  state.chartMode = mode;
  localStorage.setItem("bst_chart_mode",mode);
  if(mode==="price_market"&&!chartMarketAssessmentPayloadReady())void ensureChartMarketAssessmentHistory();
  const series = chartSeries(mode,currency);
  renderChartLegend(series);
  const overlay = series.length > 1;
  updateChartScaleButtons(series);
  const logarithmic = index => Boolean(series[index] && !series[index].allowNegative && chartAxisScale(index) === "log");
  $("#overlayOpacity").disabled = !overlay;
  $("#opacityControl").classList.toggle("is-inactive", !overlay);
  const usable = (value,index) => Number.isFinite(Number(value)) && (!logarithmic(index) || Number(value) > 0);
  const timelineKey = derivedCacheKey("chartTimeline",mode,currency,state.unit,state.lang,state.fiatFree?"fiat-free":"fiat",state.satsPerFiat?"sats-per-fiat":"plain");
  let dates = derivedCache.get(timelineKey);
  if (!dates) {
    dates = [...new Set(series.flatMap(item => Object.keys(item.values || {})))]
      .filter(day => Number.isFinite(chartTimestamp(day))).sort((left,right) => chartTimestamp(left) - chartTimestamp(right));
    derivedCache.set(timelineKey,dates);
  }
  const element = $("#priceChart");
  schedulePerformanceSummary(currency);
  if (dates.length < 2) { element.innerHTML = `<p>${esc(t("noData"))}</p>`; $("#chartTooltip").classList.add("hidden"); return; }

  const mobileChart = window.matchMedia("(max-width: 760px)").matches;
  const width = Math.max(mobileChart ? 320 : 760, Math.round(element.clientWidth || (mobileChart ? 360 : 1200)));
  const height = Math.max(mobileChart ? 500 : 420, Math.round(element.clientHeight || (mobileChart ? 520 : 420)));
  const pad = mobileChart
    ? {l:54,r:overlay?58:16,t:34,b:54}
    : {l:78,r:overlay?86:28,t:28,b:48};
  const plotWidth = width-pad.l-pad.r, plotHeight = height-pad.t-pad.b;
  const times = dates.map(chartTimestamp);
  const minTime = times[0], maxTime = times[times.length-1], timeSpan = Math.max(1,maxTime-minTime);
  const intradayAxis = timeSpan <= 2 * 86400000;
  const xDay = day => pad.l + (chartTimestamp(day)-minTime)/timeSpan*plotWidth;
  const markerEvents = [...chartMilestoneEvents(), ...chartHalvingEvents()]
    .filter(item => item.timestamp >= minTime && item.timestamp <= maxTime)
    .sort((a,b) => a.timestamp - b.timestamp)
    .map((item,index) => ({...item,index,x:pad.l + (item.timestamp-minTime)/timeSpan*plotWidth}));
  const marketSeriesIndex=series.findIndex(item=>item?.key==="market_assessment"),marketPayload=chartMarketAssessmentPayloadReady()?state.chartMarketAssessmentHistory:null,marketRawMarkers=marketSeriesIndex>=0?(Array.isArray(marketPayload?.marker_points)&&marketPayload.marker_points.length?marketPayload.marker_points:(marketPayload?.best_point?[marketPayload.best_point]:[])):[];
  const transform = (value,index) => logarithmic(index) ? Math.log10(Number(value)) : Number(value);
  const inverse = (value,index) => logarithmic(index) ? 10 ** Number(value) : Number(value);
  const getExtent = (item,index) => {
    if(Number.isFinite(Number(item?.fixedMin))&&Number.isFinite(Number(item?.fixedMax))&&Number(item.fixedMax)>Number(item.fixedMin))return [transform(Number(item.fixedMin),index),transform(Number(item.fixedMax),index)];
    let min=Number.POSITIVE_INFINITY,max=Number.NEGATIVE_INFINITY;
    for (const day of dates) {
      const raw = item.values[day];
      if (!usable(raw,index)) continue;
      const value = transform(raw,index);
      if (value < min) min=value;
      if (value > max) max=value;
    }
    if(!Number.isFinite(min)||!Number.isFinite(max)){min=0;max=1;}
    if(min===max){const delta=Math.max(Math.abs(min)*.05,.05);min-=delta;max+=delta;}
    const padding=(max-min)*.06;
    if (logarithmic(index)) return [min-padding,max+padding];
    return item.allowNegative ? [min-padding,max+padding] : [Math.max(0,min-padding),max+padding];
  };
  const extents = series.map(getExtent);
  const y = (value,index) => { const [min,max]=extents[index], mapped=transform(value,index); return pad.t + (1-(mapped-min)/(max-min))*plotHeight; };
  const nearestMarketDateIndex=target=>{let lo=0,hi=times.length-1;while(lo<hi){const mid=Math.floor((lo+hi)/2);if(times[mid]<target)lo=mid+1;else hi=mid;}if(lo>0&&Math.abs(times[lo-1]-target)<Math.abs(times[lo]-target))return lo-1;return lo;};
  const marketBestRows=marketRawMarkers.map((marker,markerIndex)=>{const target=chartTimestamp(marker?.date);if(!Number.isFinite(target))return null;const dateIndex=nearestMarketDateIndex(target),day=dates[dateIndex],displayValue=Number(series[marketSeriesIndex]?.values?.[day]);if(!usable(displayValue,marketSeriesIndex))return null;return {marker,markerIndex,day,x:xDay(day),y:y(displayValue,marketSeriesIndex),bottomConfirmed:Boolean(marker?.bottom_confirmation_met)};}).filter(Boolean);

  // Final render guard only. The durable fine-price cache is already adaptive:
  // today/very recent = dense, then 30m -> 2h -> 12h -> daily for long ranges.
  // This prevents minute-level data from ever leaking into 10-year/Max charts.
  const requestedChartDays = historyDaysForRange();
  const maxVisiblePoints = requestedChartDays > 0 && requestedChartDays <= 366 ? (mobileChart ? 2200 : 3600) : 1800;
  const step = Math.max(1,Math.ceil(dates.length/maxVisiblePoints));
  const displayDates = dates.filter((_,index)=>index===0||index===dates.length-1||index%step===0);
  const pointRows = (item,index) => {
    const rows=[];
    for (const day of displayDates) {
      const value=item.values[day];
      if (!usable(value,index)) continue;
      rows.push({day,x:xDay(day),y:y(value,index)});
    }
    return rows;
  };
  const pointText = (rows, stepped=false) => {
    if (!stepped || rows.length < 2) return rows.map(row=>`${row.x.toFixed(2)},${row.y.toFixed(2)}`).join(" ");
    const points=[`${rows[0].x.toFixed(2)},${rows[0].y.toFixed(2)}`];
    for(let index=1;index<rows.length;index++){
      const previous=rows[index-1],current=rows[index];
      points.push(`${current.x.toFixed(2)},${previous.y.toFixed(2)}`);
      points.push(`${current.x.toFixed(2)},${current.y.toFixed(2)}`);
    }
    return points.join(" ");
  };
  const primaryRows = pointRows(series[0],0), primaryPoints = pointText(primaryRows,Boolean(series[0].step));
  const primaryExtent = extents[0];
  const areaBaseline = series[0].allowNegative && primaryExtent[0] <= 0 && primaryExtent[1] >= 0
    ? y(0,0)
    : height-pad.b;
  const area = series[0].fill === false || !primaryRows.length ? "" : `${primaryRows[0].x.toFixed(2)},${areaBaseline.toFixed(2)} ${primaryPoints} ${primaryRows.at(-1).x.toFixed(2)},${areaBaseline.toFixed(2)}`;
  const axisValue = (extent,fraction,index) => inverse(extent[1]-fraction*(extent[1]-extent[0]),index);
  const grid = [0,.25,.5,.75,1].map(fraction => {
    const yy=pad.t+fraction*plotHeight, value=axisValue(extents[0],fraction,0);
    const axisText=series[0]?.publicValue?esc(compactAxis(value)):privateHtml(compactAxis(value));
    return `<line class="grid" x1="${pad.l}" y1="${yy}" x2="${width-pad.r}" y2="${yy}"/><text class="axis-text" x="8" y="${yy+4}">${axisText}</text>`;
  }).join("");
  const rightAxis = overlay ? [0,.25,.5,.75,1].map(fraction => { const yy=pad.t+fraction*plotHeight,value=axisValue(extents[1],fraction,1),axisText=series[1]?.publicValue?esc(compactAxis(value)):privateHtml(compactAxis(value)); return `<text class="axis-text" x="${width-4}" y="${yy+4}" text-anchor="end">${axisText}</text>`; }).join("") : "";
  const nearestDateIndex = target => { let lo=0,hi=times.length-1; while(lo<hi){const mid=Math.floor((lo+hi)/2);if(times[mid]<target)lo=mid+1;else hi=mid;} if(lo>0&&Math.abs(times[lo-1]-target)<Math.abs(times[lo]-target))return lo-1;return lo; };
  const tickFractions = mobileChart ? [0,.5,1] : [0,.25,.5,.75,1];
  const tickDates = [...new Set(tickFractions.map(fraction=>dates[nearestDateIndex(minTime+fraction*timeSpan)]))];
  const dateLabels = tickDates.map(day => `<text class="date-text" x="${xDay(day)}" y="${height-12}" text-anchor="middle">${esc(intradayAxis ? fmtChartPoint(day,true) : fmtDate(day))}</text>`).join("");
  const opacity = state.overlayOpacity / 100;
  const secondaryRows = overlay ? pointRows(series[1],1) : [];
  const secondary = overlay ? `<polyline class="series-secondary" stroke-opacity="${opacity.toFixed(2)}" points="${pointText(secondaryRows,Boolean(series[1].step))}"/>` : "";
  const markerSvg = markerEvents.map(item => {
    const markerY = pad.t + 15;
    const lineStart = markerY + 10;
    return `<g class="chart-event chart-event-${esc(item.kind)}"><title>${esc(item.label)}</title><line class="chart-event-line" x1="${item.x.toFixed(2)}" y1="${lineStart}" x2="${item.x.toFixed(2)}" y2="${height-pad.b}"/><circle class="chart-event-badge" cx="${item.x.toFixed(2)}" cy="${markerY}" r="9"/><text class="chart-event-icon" x="${item.x.toFixed(2)}" y="${markerY+4.5}" text-anchor="middle">${esc(item.icon)}</text></g>`;
  }).join("");
  const marketBestSvg=marketBestRows.map(({markerIndex,x,y,bottomConfirmed})=>`<g class="market-best-marker-hit chart-market-best${bottomConfirmed?" is-bottom":""}" data-market-marker-index="${markerIndex}" tabindex="0" role="button" aria-label="${esc(walletWatchLang("Bestwert anzeigen","Show best value"))}"><circle cx="${x.toFixed(2)}" cy="${Math.max(pad.t+14,y-9).toFixed(2)}" r="14"/><text class="market-best-star${bottomConfirmed?" is-bottom":""}" x="${x.toFixed(2)}" y="${Math.max(pad.t+14,y-9).toFixed(2)}" text-anchor="middle" aria-hidden="true">★</text></g>`).join("");
  const zeroLines = series.map((item,index) => {
    if (!item.allowNegative || logarithmic(index)) return "";
    const [min,max] = extents[index];
    if (min > 0 || max < 0) return "";
    const yy = y(0,index);
    return `<line class="zero-line ${index ? "secondary-zero" : ""}" x1="${pad.l}" y1="${yy}" x2="${width-pad.r}" y2="${yy}"/>`;
  }).join("");
  element.innerHTML = `<svg class="${mobileChart ? "mobile-chart-svg" : ""}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(series.map(item=>item.label).join(" + "))}">
    <defs><linearGradient id="areaPrimary" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7931a" stop-opacity=".32"/><stop offset="1" stop-color="#f7931a" stop-opacity="0"/></linearGradient></defs>
    ${grid}${rightAxis}${zeroLines}${markerSvg}${area?`<polygon class="area-primary" points="${area}"/>`:""}<polyline class="series-primary" points="${primaryPoints}"/>${secondary}${dateLabels}
    <text class="axis-text" x="${pad.l}" y="18">${esc(series[0].label)} · ${esc(logarithmic(0)?t("logarithmic"):t("linear"))}</text>${overlay?`<text class="axis-text" x="${width-pad.r}" y="18" text-anchor="end">${esc(series[1].label)} · ${esc(logarithmic(1)?t("logarithmic"):t("linear"))}</text>`:""}
    <line id="crossX" class="crosshair hidden" x1="0" y1="${pad.t}" x2="0" y2="${height-pad.b}"/><line id="crossY" class="crosshair hidden" x1="${pad.l}" y1="0" x2="${width-pad.r}" y2="0"/>
    <circle id="crossDotA" class="cross-dot hidden" r="5" stroke="#f7931a"/><circle id="crossDotB" class="cross-dot hidden" r="5" stroke="#66d19e"/>
    <rect id="chartHit" class="chart-hit" x="${pad.l}" y="${pad.t}" width="${plotWidth}" height="${plotHeight}"/>${marketBestSvg}
  </svg>`;
  const hit=$("#chartHit",element), crossX=$("#crossX",element), crossY=$("#crossY",element), dotA=$("#crossDotA",element), dotB=$("#crossDotB",element), tooltip=$("#chartTooltip");
  const hide=()=>{[crossX,crossY,dotA,dotB].forEach(node=>node?.classList.add("hidden"));tooltip.classList.add("hidden");};
  hit.addEventListener("pointerleave",hide);
  hit.addEventListener("pointermove",event=>{
    const rect=hit.getBoundingClientRect(), fraction=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)), index=nearestDateIndex(minTime+fraction*timeSpan), day=dates[index], xPos=xDay(day);
    const primary=Number(series[0].values[day]), secondaryValue=overlay?Number(series[1].values[day]):NaN;
    if(!usable(primary,0)){hide();return;}
    const yPos=y(primary,0);
    crossX.setAttribute("x1",xPos);crossX.setAttribute("x2",xPos);crossX.classList.remove("hidden");
    crossY.setAttribute("y1",yPos);crossY.setAttribute("y2",yPos);crossY.classList.remove("hidden");
    dotA.setAttribute("cx",xPos);dotA.setAttribute("cy",yPos);dotA.classList.remove("hidden");
    if(overlay&&usable(secondaryValue,1)){dotB.setAttribute("cx",xPos);dotB.setAttribute("cy",y(secondaryValue,1));dotB.classList.remove("hidden");}else dotB.classList.add("hidden");
    const nearbyMarkers = markerEvents.filter(item => Math.abs(item.x - xPos) <= 10);
    const markerDetails = nearbyMarkers.map(item => `<div class="chart-tooltip-event ${esc(item.kind)}"><span aria-hidden="true">${esc(item.icon)}</span>${esc(item.label)}</div>`).join("");
    const primaryHtml=series[0]?.publicValue?esc(series[0].format(primary)):privateHtml(series[0].format(primary));
    const secondaryHtml=overlay&&usable(secondaryValue,1)?(series[1]?.publicValue?esc(series[1].format(secondaryValue)):privateHtml(series[1].format(secondaryValue))):"";
    tooltip.innerHTML=`<strong>${esc(fmtChartPoint(day,intradayAxis))}</strong><div><span class="chart-tooltip-dot primary" aria-hidden="true"></span>${esc(series[0].label)}: ${primaryHtml}</div>${overlay&&usable(secondaryValue,1)?`<div><span class="chart-tooltip-dot secondary" aria-hidden="true"></span>${esc(series[1].label)}: ${secondaryHtml}</div>`:""}${markerDetails}`;
    tooltip.classList.remove("hidden");
    const panelRect=element.closest(".chart-panel").getBoundingClientRect(),desiredLeft=event.clientX-panelRect.left+14,maxLeft=panelRect.width-tooltip.offsetWidth-12;
    tooltip.style.left=`${Math.max(10,Math.min(maxLeft,desiredLeft))}px`;
    tooltip.style.top=`${Math.max(70,event.clientY-panelRect.top-tooltip.offsetHeight-15)}px`;
  });
  for(const node of $$(".chart-market-best",element)){const row=marketBestRows[Number(node.dataset.marketMarkerIndex)];if(!row)continue;const show=event=>{event.preventDefault();event.stopPropagation();[crossX,crossY,dotA,dotB].forEach(part=>part?.classList.add("hidden"));tooltip.innerHTML=marketBestMarkerPopupHtml(row.marker);tooltip.classList.remove("hidden");const rect=node.getBoundingClientRect();positionChartPopup(tooltip,element.closest(".chart-panel"),rect.left+rect.width/2,rect.top+rect.height/2);};node.addEventListener("pointerenter",event=>{if(event.pointerType!=="touch")show(event);});node.addEventListener("pointerleave",event=>{if(event.pointerType!=="touch")tooltip.classList.add("hidden");});node.addEventListener("pointerdown",show);node.addEventListener("focus",show);node.addEventListener("blur",()=>tooltip.classList.add("hidden"));}
}

function ledgerTypeClass(type) {
  const value = String(type || "").toLowerCase();
  return ["purchase", "income", "sale", "stack", "expense", "network_fee"].includes(value) ? `ledger-type-${value}` : "ledger-type-other";
}

function goalMilestonesByEntryId() {
  const cacheKey = derivedCacheKey("goalMilestonesByEntryId",state.discreet?"private":"normal");
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const result = new Map();
  if (state.discreet) return result;
  for (const goal of sortedStackingGoals()) {
    const target = Number(goal?.amount_btc || 0);
    if (!(target > 0)) continue;
    const scope = String(goal?.depot_id || "all");
    const rows = (Array.isArray(state.data?.entries) ? state.data.entries : [])
      .filter(row => scope === "all" || String(row?.depot_id || "main") === scope)
      .map(row => ({row,time:new Date(row?.timestamp || "").getTime(),outgoing:["sale","expense","network_fee"].includes(String(row?.type || ""))}))
      .filter(item => Number.isFinite(item.time))
      .sort((a,b) => a.time - b.time || Number(a.outgoing) - Number(b.outgoing) || String(a.row?.id || "").localeCompare(String(b.row?.id || "")));
    let balance = 0;
    for (const item of rows) {
      const amount = Math.max(0, Number(item.row?.amount_btc || 0));
      const kind=String(item.row?.type || "");
      if (["purchase","income","stack"].includes(kind)) balance += amount;
      else if (["sale","expense","network_fee"].includes(kind)) balance -= amount;
      if (kind !== "network_fee" && item.row?.fee_btc_affects_stack) balance -= Math.max(0,Number(item.row?.fee_btc || 0));
      if (balance + 1e-12 >= target) {
        const entryId = String(item.row?.id || "");
        if (entryId) {
          if (!result.has(entryId)) result.set(entryId, []);
          result.get(entryId).push(goal);
        }
        break;
      }
    }
  }
  derivedCache.set(cacheKey,result);
  return result;
}

function ledgerDetailHtml(entry, milestones = []) {
  const noteText = entry.note ? (state.discreet ? "***" : String(entry.note)) : "";
  const note = noteText ? `<div class="ledger-note-block"><span class="ledger-detail-label">${esc(t("note"))}</span><span>${esc(noteText)}</span></div>` : "";
  const goalEvents = milestones.map(goal => `<div class="ledger-milestone-block"><span aria-hidden="true">🎯</span><span><strong>${esc(t("milestoneReached"))}:</strong> ${esc(goal.name)} · ${privateHtml(fmtStack(goal.amount_btc))}</span></div>`).join("");
  return note + goalEvents;
}

function ledgerEntryYear(entry) {
  const date = new Date(entry?.timestamp || "");
  return Number.isNaN(date.getTime()) ? null : date.getFullYear();
}
function renderLedgerPeriodOptions(allEntries) {
  const select = $("#ledgerPeriodFilter");
  if (!select) return;
  const currentYear = new Date().getFullYear();
  const years = [...new Set(allEntries.map(ledgerEntryYear).filter(Number.isFinite))].sort((a,b)=>b-a);
  const options = [
    ["all", t("allLedgerEntries")],
    ["current", `${t("currentYear")} (${currentYear})`],
    ...years.filter(year => year !== currentYear).map(year => [`year:${year}`, String(year)])
  ];
  if (!options.some(([value]) => value === state.ledgerPeriodFilter)) state.ledgerPeriodFilter = "all";
  select.innerHTML = options.map(([value,label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("");
  select.value = state.ledgerPeriodFilter;
}
function ledgerMatchesPeriod(entry) {
  const filter = state.ledgerPeriodFilter || "all";
  if (filter === "all") return true;
  const year = ledgerEntryYear(entry);
  if (!Number.isFinite(year)) return false;
  if (filter === "current") return year === new Date().getFullYear();
  if (filter.startsWith("year:")) return year === Number(filter.slice(5));
  return true;
}
function ledgerPageButtons(totalPages) {
  if (totalPages <= 1) return [];
  const current = Math.min(Math.max(1,state.ledgerPage),totalPages);
  const pages = new Set([1,totalPages,current-2,current-1,current,current+1,current+2]);
  return [...pages].filter(page=>page>=1&&page<=totalPages).sort((a,b)=>a-b);
}
function scrollLedgerPageToStart() {
  const tableWrap = document.querySelector("#tab-ledger .ledger-table-wrap");
  if (tableWrap && getComputedStyle(tableWrap).display !== "none") {
    tableWrap.scrollTo({top:0,behavior:"smooth"});
    return;
  }
  document.querySelector("#ledgerCards")?.scrollIntoView({block:"start",behavior:"smooth"});
}
function renderLedgerPagination(totalEntries,totalPages,pageStart,pageEnd) {
  const host = $("#ledgerPagination");
  if (!host) return;
  if (!totalEntries) { host.innerHTML = ""; return; }
  const current = Math.min(Math.max(1,state.ledgerPage),Math.max(1,totalPages));
  const pages = ledgerPageButtons(totalPages);
  let last = 0;
  const pageButtons = pages.map(page => {
    const gap = last && page-last>1 ? '<span class="ledger-page-gap" aria-hidden="true">…</span>' : "";
    last = page;
    return `${gap}<button type="button" class="ghost compact ledger-page-button${page===current?" is-active":""}" data-page="${page}" aria-current="${page===current?"page":"false"}">${page}</button>`;
  }).join("");
  host.innerHTML = `<span class="ledger-page-summary">${fmtNumber(pageStart+1,0)}–${fmtNumber(pageEnd,0)} ${t("of")} ${fmtNumber(totalEntries,0)} ${t("entriesShown")}</span><div class="ledger-page-controls"><button type="button" class="ghost compact ledger-page-nav" data-page="${Math.max(1,current-1)}" ${current<=1?"disabled":""} aria-label="${esc(t("page"))} ${current-1}">‹</button>${pageButtons}<button type="button" class="ghost compact ledger-page-nav" data-page="${Math.min(totalPages,current+1)}" ${current>=totalPages?"disabled":""} aria-label="${esc(t("page"))} ${current+1}">›</button></div>`;
  $$("#ledgerPagination [data-page]").forEach(button => button.onclick=()=>{
    state.ledgerPage = Number(button.dataset.page) || 1;
    renderLedger();
    scrollLedgerPageToStart();
  });
}

function compactTableLayout() {
  return window.matchMedia("(max-width: 760px)").matches;
}

function renderLedger() {
  const query = String($("#ledgerSearch")?.value || "").toLowerCase();
  const milestoneMap = goalMilestonesByEntryId();
  const allEntries = [...(state.data.entries || [])].reverse();
  renderLedgerPeriodOptions(allEntries);
  const filteredEntries = allEntries.filter(item => {
    if (!ledgerMatchesPeriod(item)) return false;
    if (!query) return true;
    if (JSON.stringify(item).toLowerCase().includes(query)) return true;
    return (milestoneMap.get(String(item.id)) || []).some(goal => String(goal?.name || "").toLowerCase().includes(query));
  });
  const pageSize = Math.max(10,Number(state.ledgerPageSize)||25);
  const totalPages = Math.max(1,Math.ceil(filteredEntries.length/pageSize));
  state.ledgerPage = Math.min(Math.max(1,state.ledgerPage),totalPages);
  const pageStart = (state.ledgerPage-1)*pageSize;
  const pageEnd = Math.min(filteredEntries.length,pageStart+pageSize);
  const entries = filteredEntries.slice(pageStart,pageEnd);
  const compactLayout = compactTableLayout();
  $("#ledgerBody").innerHTML = compactLayout ? "" : entries.map(entry => {
    const sale=state.data.fifo.sales?.[entry.id], price=entry.price?(entry.type==="expense"?`${fmtNumber(Number(entry.amount_btc||0)*Number(entry.price||0),2)} ${entry.currency}`:`${fmtNumber(entry.price,2)} ${entry.currency}`):"–", holding=entryHolding(entry);
    const controlTotal=entry.price?transactionFiatTotal(entry.type,Number(entry.amount_btc||0),Number(entry.price||0),Number(entry.fee||0)):NaN;
    const totalLabel=Number.isFinite(controlTotal)&&controlTotal>0?fmtFiat(controlTotal,entry.currency):"–",feeLabel=transactionFeeDisplay(entry);
    const typeClass=ledgerTypeClass(entry.type), detail=ledgerDetailHtml(entry,milestoneMap.get(String(entry.id)) || []);
    return `<tr class="ledger-entry-row ${typeClass}"><td class="ledger-date-cell">${esc(fmtDate(entry.timestamp))}</td><td><span class="badge ledger-type-badge">${esc(t(entry.type) || entry.type)}</span></td><td><code>${privateHtml(fmtStack(entry.amount_btc))}</code></td><td>${privateHtml(price)}</td><td>${privateHtml(totalLabel)}</td><td>${privateHtml(feeLabel)}</td><td>${esc(depotName(entry.depot_id))}</td><td>${entryHoldingHtml(entry)}${sale?`<br><small>${privateHtml(fmtStack(sale.long_term_btc))} L / ${privateHtml(fmtStack(sale.short_term_btc))} S</small>`:""}</td><td><div class="ledger-row-actions"><button class="secondary compact edit-entry" type="button" data-id="${esc(entry.id)}" aria-label="${esc(t("edit"))}" title="${esc(t("edit"))}">✎</button><button class="danger compact delete-entry" type="button" data-id="${esc(entry.id)}" aria-label="${esc(t("delete"))}" title="${esc(t("delete"))}">×</button></div></td></tr>${detail ? `<tr class="ledger-note-row ${typeClass}"><td class="ledger-note-date-spacer" aria-hidden="true"></td><td colspan="8"><div class="ledger-entry-details">${detail}</div></td></tr>` : ""}`;
  }).join("");
  const cards = $("#ledgerCards");
  if (cards) {
    cards.innerHTML = !compactLayout ? "" : (entries.length ? entries.map(entry => {
      const sale=state.data.fifo.sales?.[entry.id], price=entry.price?(entry.type==="expense"?`${fmtNumber(Number(entry.amount_btc||0)*Number(entry.price||0),2)} ${entry.currency}`:`${fmtNumber(entry.price,2)} ${entry.currency}`):"–", holding=entryHolding(entry);
      const controlTotal=entry.price?transactionFiatTotal(entry.type,Number(entry.amount_btc||0),Number(entry.price||0),Number(entry.fee||0)):NaN;
      const totalLabel=Number.isFinite(controlTotal)&&controlTotal>0?fmtFiat(controlTotal,entry.currency):"–",feeLabel=transactionFeeDisplay(entry);
      const typeClass=ledgerTypeClass(entry.type), detail=ledgerDetailHtml(entry,milestoneMap.get(String(entry.id)) || []);
      return `<article class="ledger-mobile-card ${typeClass}">
        <div class="ledger-mobile-head"><div><span class="badge ledger-type-badge">${esc(t(entry.type) || entry.type)}</span><strong>${esc(fmtDate(entry.timestamp))}</strong></div><div class="ledger-row-actions"><button class="secondary compact edit-entry" type="button" data-id="${esc(entry.id)}" aria-label="${esc(t("edit"))}" title="${esc(t("edit"))}">✎</button><button class="danger compact delete-entry" type="button" data-id="${esc(entry.id)}" aria-label="${esc(t("delete"))}" title="${esc(t("delete"))}">×</button></div></div>
        <dl>
          <div><dt>${esc(t("amount"))}</dt><dd><code>${privateHtml(fmtStack(entry.amount_btc))}</code></dd></div>
          <div><dt>${esc(t("price"))}</dt><dd>${privateHtml(price)}</dd></div>
          <div><dt>${esc(t("fiatTotal"))}</dt><dd>${privateHtml(totalLabel)}</dd></div>
          <div><dt>${esc(t("fee"))}</dt><dd>${privateHtml(feeLabel)}</dd></div>
          <div><dt>${esc(t("depot"))}</dt><dd>${esc(depotName(entry.depot_id))}</dd></div>
          <div><dt>${esc(t("holding"))}</dt><dd>${entryHoldingHtml(entry)}${sale?`<small>${privateHtml(fmtStack(sale.long_term_btc))} L / ${privateHtml(fmtStack(sale.short_term_btc))} S</small>`:""}</dd></div>
        </dl>
        ${detail ? `<div class="ledger-mobile-note ledger-entry-details">${detail}</div>` : ""}
      </article>`;
    }).join("") : `<p class="storage-note">${esc(t("noData"))}</p>`);
  }
  renderLedgerPagination(filteredEntries.length,totalPages,pageStart,pageEnd);
  $$(".edit-entry").forEach(button => button.onclick=()=>beginEditEntry(button.dataset.id));
  $$(".delete-entry").forEach(button => button.onclick=()=>openDeleteEntryDialog(button.dataset.id));
  const deleteAll = $("#deleteAllEntries");
  if (deleteAll) {
    deleteAll.classList.toggle("hidden", !state.data?.security?.owner);
    deleteAll.disabled = !allEntries.length || !state.data?.security?.owner;
  }
}

function renderAggregateDepot() {
  const element = $("#aggregateDepotSummary");
  if (!element) return;
  const data = state.data || {}, fifo = data.fifo || {}, currency = currentCurrency();
  const totalBtc = Number(fifo.total_btc || 0);
  const livePrice = Number(data.prices?.[currency]);
  const totalValue = Number.isFinite(livePrice) ? totalBtc * livePrice : null;
  const values = chartValues(currency);
  const portfolioChange = seriesChange(values.portfolio);
  const stackChange = seriesChange(values.stackBtc);
  const rangeLabel = $("#historyRange option:checked")?.textContent || t("selectedRange");
  const portfolioCss = portfolioChange?.absolute > 0 ? "positive" : portfolioChange?.absolute < 0 ? "negative" : "";
  const stackCss = stackChange?.absolute > 0 ? "positive" : stackChange?.absolute < 0 ? "negative" : "";
  const portfolioPerformance = portfolioChange
    ? `${signedFiat(portfolioChange.absolute, currency)} · ${portfolioChange.percent==null?"–":signedPercent(portfolioChange.percent)}`
    : "–";
  const stackPerformance = stackChange
    ? `${state.unit === "sats" ? `${signedNumber(stackChange.absolute * SATS_PER_BTC, 0)} sats` : `${signedNumber(stackChange.absolute, 8)} BTC`} · ${signedPercent(stackChange.percent)}`
    : "–";
  element.innerHTML = `<article class="aggregate-depot-card">
    <div class="aggregate-depot-head"><div><span class="kicker">${esc(t("allDepotsCombined"))}</span><h3>${esc(t("totalDepot"))}</h3></div><span class="badge">${esc(rangeLabel)}</span></div>
    <div class="aggregate-depot-grid">
      <div><span>${esc(t("totalStack"))}</span><strong>${privateHtml(fmtStack(totalBtc))}</strong><small>${esc(t("longTerm"))}: ${privateHtml(fmtStack(fifo.long_term_btc || 0))} · ${esc(t("shortTerm"))}: ${privateHtml(fmtStack(fifo.short_term_btc || 0))}</small></div>
      <div><span>${esc(t("totalValue"))}</span><strong>${privateHtml(fmtFiat(totalValue, currency))}</strong><small>${privateHtml(fmtFiat(livePrice, currency))} / BTC</small></div>
      <div><span>${esc(t("rangePerformance"))}</span><strong class="${portfolioCss}">${privateHtml(portfolioPerformance)}</strong><small>${portfolioChange ? `${esc(t("twr"))} · ${esc(fmtDate(portfolioChange.startDay))} → ${esc(fmtDate(portfolioChange.endDay))}` : esc(t("comparisonUnavailable"))}</small></div>
      <div><span>${esc(t("stackChange"))}</span><strong class="${stackCss}">${privateHtml(stackPerformance)}</strong><small>${stackChange ? `${esc(fmtDate(stackChange.startDay))} → ${esc(fmtDate(stackChange.endDay))}` : esc(t("comparisonUnavailable"))}</small></div>
    </div>
  </article>`;
}
function renderDepots() {
  renderAggregateDepot();
  const counts=state.data.depot_entry_counts||{};
  $("#depotList").innerHTML = state.data.depots.map(depot => { const summary=state.data.depot_summaries.find(item=>item.id===depot.id)||{},canDelete=depot.id!=="main"&&Number(counts[depot.id]||0)===0;return `<div class="list-item"><div><strong>${esc(depot.name)}</strong><div class="meta">${esc(depot.id)} · ${privateHtml(fmtStack(summary.total_btc||0))} · ${esc(t("longTerm"))}: ${privateHtml(fmtStack(summary.long_term_btc||0))}</div></div>${canDelete?`<button class="danger delete-depot" data-id="${esc(depot.id)}">${esc(t("delete"))}</button>`:""}</div>`; }).join("");
  $$(".delete-depot").forEach(button=>button.onclick=async()=>{if(!confirm(t("confirmDelete")))return;await service("delete_depot",{config_entry_id:state.entryId,depot_id:button.dataset.id});await loadData();});
}
function renderGoalsEditor() {
  if (state.discreet) { const editor=$("#goalEditor"); if(editor)editor.innerHTML=""; return; }
  const depots=[{id:"all",name:t("allDepots")},...state.data.depots],currencies=state.data.currencies;
  $("#goalEditor").innerHTML=sortedStackingGoals().map(goal=>`<div class="goal-edit" data-id="${esc(goal.id)}"><label><span>${esc(t("name"))}</span><input class="g-name" value="${esc(goal.name)}"></label><label><span>${esc(state.unit)}</span><input class="g-amount" type="number" step="any" value="${esc(rawUnitValue(goal.amount_btc))}"></label><label><span>${esc(t("depot"))}</span><select class="g-depot">${depots.map(d=>`<option value="${esc(d.id)}" ${d.id===goal.depot_id?"selected":""}>${esc(d.name)}</option>`).join("")}</select></label><label><span>${esc(t("currency"))}</span><select class="g-currency">${currencies.map(code=>`<option ${code===goal.currency?"selected":""}>${esc(code)}</option>`).join("")}</select></label><div><button class="secondary save-goal">${esc(t("save"))}</button> <button class="danger delete-goal">×</button></div></div>`).join("");
  $$(".save-goal").forEach(button=>button.onclick=async()=>{const row=button.closest(".goal-edit");await service("update_goal",{config_entry_id:state.entryId,goal_id:row.dataset.id,goal_name:$(".g-name",row).value,goal:Number($(".g-amount",row).value),goal_unit:state.unit,depot_id:$(".g-depot",row).value,currency:$(".g-currency",row).value});toast(t("goalSaved"));await loadData();});
  $$(".delete-goal").forEach(button=>button.onclick=async()=>{if(!confirm(t("confirmDelete")))return;await service("delete_goal",{config_entry_id:state.entryId,goal_id:button.closest(".goal-edit").dataset.id});await loadData();});
}
function fifoPageButtons(totalPages) {
  if (totalPages <= 1) return [];
  const current = Math.min(Math.max(1,state.fifoPage),totalPages);
  const pages = new Set([1,totalPages,current-2,current-1,current,current+1,current+2]);
  return [...pages].filter(page=>page>=1&&page<=totalPages).sort((a,b)=>a-b);
}
function scrollFifoPageToStart() {
  const tableWrap = document.querySelector("#tab-tax .fifo-table-wrap");
  if (tableWrap && getComputedStyle(tableWrap).display !== "none") {
    tableWrap.scrollTo({top:0,behavior:"smooth"});
    return;
  }
  document.querySelector("#fifoCards")?.scrollIntoView({block:"start",behavior:"smooth"});
}
function renderFifoPagination(totalEntries,totalPages,pageStart,pageEnd) {
  const host = $("#fifoPagination");
  if (!host) return;
  if (!totalEntries) { host.innerHTML = ""; return; }
  const current = Math.min(Math.max(1,state.fifoPage),Math.max(1,totalPages));
  const pages = fifoPageButtons(totalPages);
  let last = 0;
  const pageButtons = pages.map(page => {
    const gap = last && page-last>1 ? '<span class="ledger-page-gap" aria-hidden="true">…</span>' : "";
    last = page;
    return `${gap}<button type="button" class="ghost compact ledger-page-button${page===current?" is-active":""}" data-fifo-page="${page}" aria-current="${page===current?"page":"false"}">${page}</button>`;
  }).join("");
  host.innerHTML = `<span class="ledger-page-summary">${fmtNumber(pageStart+1,0)}–${fmtNumber(pageEnd,0)} ${t("of")} ${fmtNumber(totalEntries,0)} ${t("entriesShown")}</span><div class="ledger-page-controls"><button type="button" class="ghost compact ledger-page-nav" data-fifo-page="${Math.max(1,current-1)}" ${current<=1?"disabled":""} aria-label="${esc(t("page"))} ${current-1}">‹</button>${pageButtons}<button type="button" class="ghost compact ledger-page-nav" data-fifo-page="${Math.min(totalPages,current+1)}" ${current>=totalPages?"disabled":""} aria-label="${esc(t("page"))} ${current+1}">›</button></div>`;
  $$("#fifoPagination [data-fifo-page]").forEach(button => button.onclick=()=>{
    state.fifoPage = Number(button.dataset.fifoPage) || 1;
    renderTax();
    scrollFifoPageToStart();
  });
}
function renderFifoSaleSummary(matches) {
  const host = $("#fifoSaleSummary");
  if (!host) return;
  if (!matches.length) { host.innerHTML = ""; return; }
  const currencies=[...new Set(matches.map(item=>String(item.sale_currency||"").toUpperCase()).filter(Boolean))];
  const preferred=String(currentCurrency()||"").toUpperCase();
  const currency=currencies.includes(preferred)?preferred:(currencies[0]||preferred||"EUR");
  const currencyMatches=matches.filter(item=>String(item.sale_currency||"").toUpperCase()===currency);
  const soldBtc=currencyMatches.reduce((sum,item)=>sum+Math.max(0,Number(item.amount_btc)||0),0);
  const basis=currencyMatches.reduce((sum,item)=>item.cost_basis==null?sum:sum+(Number(item.cost_basis)||0),0);
  const proceeds=currencyMatches.reduce((sum,item)=>item.net_proceeds==null?sum:sum+(Number(item.net_proceeds)||0),0);
  const gain=currencyMatches.reduce((sum,item)=>item.realized_gain==null?sum:sum+(Number(item.realized_gain)||0),0);
  const unresolvedBtc=currencyMatches.reduce((sum,item)=>item.cost_basis==null?sum+(Number(item.amount_btc)||0):sum,0);
  const roi=basis>0?(gain/basis)*100:null;
  const gainClass=gain>0?"positive":gain<0?"negative":"";

  // Non-FIFO comparison. Each FIFO row carries the historical average buy-in
  // that applied to the outgoing booking. Summing amount*average across the
  // split rows reconstructs the booking-level comparison without double
  // counting a disposal that consumed several FIFO lots.
  const averageRows=currencyMatches.filter(item=>{
    const amount=Math.max(0,Number(item.amount_btc)||0);
    const avg=Number(item.average_entry_price_to_date);
    return amount>0 && Number.isFinite(avg) && avg>0 && item.average_entry_gain!=null;
  });
  const averageAmount=averageRows.reduce((sum,item)=>sum+Math.max(0,Number(item.amount_btc)||0),0);
  const averageBasis=averageRows.reduce((sum,item)=>sum+(Math.max(0,Number(item.amount_btc)||0)*Number(item.average_entry_price_to_date)),0);
  const averageProceeds=averageRows.reduce((sum,item)=>item.net_proceeds==null?sum:sum+(Number(item.net_proceeds)||0),0);
  const averageGain=averageRows.reduce((sum,item)=>sum+(Number(item.average_entry_gain)||0),0);
  const averagePrice=averageAmount>0?averageBasis/averageAmount:null;
  const averageRoi=averageBasis>0?(averageGain/averageBasis)*100:null;
  const averageGainClass=averageGain>0?"positive":averageGain<0?"negative":"";
  const averageMissingBtc=Math.max(0,soldBtc-averageAmount);

  const note=t("fifoCurrencyNote").replace("{currency}",currency);
  const dispositionCount=new Set(currencyMatches.map((item,index)=>String(item.disposition_index??`${item.disposition_type||"sale"}:${item.sale_timestamp||""}:${index}`))).size;
  host.innerHTML=`<article class="aggregate-depot-card fifo-summary-card">
    <div class="aggregate-depot-head"><div><span class="kicker">FIFO ABGÄNGE · ${esc(currency)}</span><h3>${esc(t("fifoAndAverageSummary"))}</h3></div><span class="badge">${fmtNumber(dispositionCount,0)} ${esc(t("dispositionCount"))}</span></div>
    <div class="fifo-comparison-sections">
      <section class="fifo-method-block">
        <div class="fifo-method-head"><span class="kicker">FIFO-METHODE</span><strong>${esc(t("fifoLotMethod"))}</strong></div>
        <div class="aggregate-depot-grid fifo-summary-grid">
          <div><span>${esc(t("soldAmount"))}</span><strong>${privateHtml(state.unit==="sats"?`${fmtNumber(soldBtc*SATS_PER_BTC,0)} sats`:`${fmtNumber(soldBtc,8)} BTC`)}</strong><small>${unresolvedBtc>0?`${esc(t("fifoUnresolved"))}: ${privateHtml(fmtStack(unresolvedBtc))}`:"FIFO"}</small></div>
          <div class="fifo-fiat-metric"><span>${esc(t("fifoCostBasis"))}</span><strong>${privateHtml(fmtFiat(basis,currency))}</strong><small>${esc(t("fifoCostBasisHint"))}</small></div>
          <div class="fifo-fiat-metric"><span>${esc(t("saleProceeds"))}</span><strong>${privateHtml(fmtFiat(proceeds,currency))}</strong><small>${esc(t("saleProceedsHint"))}</small></div>
          <div class="fifo-fiat-metric"><span>${esc(t("fifoGain"))}</span><strong class="${gainClass}">${privateHtml(signedFiat(gain,currency))}</strong><small>${roi==null?"–":privateHtml(`${t("fifoReturn")}: ${signedPercent(roi)}`)}</small></div>
        </div>
      </section>
      <section class="fifo-method-block fifo-average-block" title="${esc(t("averageComparisonHint"))}">
        <div class="fifo-method-head"><span class="kicker">Ø BIS ZUM ABGANG</span><strong>${esc(t("averageComparisonSummary"))}</strong></div>
        <div class="aggregate-depot-grid fifo-summary-grid">
          <div class="fifo-fiat-metric"><span>${esc(t("averageComparisonPrice"))}</span><strong>${averagePrice==null?"–":privateHtml(`${fmtFiat(averagePrice,currency)} / BTC`)}</strong><small>${esc(t("averageEntryToDate"))}</small></div>
          <div class="fifo-fiat-metric"><span>${esc(t("averageEntryBasis"))}</span><strong>${averageBasis>0?privateHtml(fmtFiat(averageBasis,currency)):"–"}</strong><small>${esc(t("averageComparisonHint"))}</small></div>
          <div class="fifo-fiat-metric"><span>${esc(t("saleProceeds"))}</span><strong>${averageAmount>0?privateHtml(fmtFiat(averageProceeds,currency)):"–"}</strong><small>${averageAmount>0?privateHtml(fmtStack(averageAmount)):"–"}</small></div>
          <div class="fifo-fiat-metric"><span>${esc(t("averageEntryGain"))}</span><strong class="${averageGainClass}">${averageAmount>0?privateHtml(signedFiat(averageGain,currency)):"–"}</strong><small>${averageRoi==null?"–":privateHtml(`${t("averageEntryReturn")}: ${signedPercent(averageRoi)}`)}</small></div>
        </div>
        ${averageMissingBtc>1e-12?`<p class="storage-note fifo-summary-note">${esc(t("averageComparisonMissing"))}: ${privateHtml(fmtStack(averageMissingBtc))}</p>`:""}
      </section>
    </div>
    ${currencies.length>1?`<p class="storage-note fifo-summary-note">${esc(note)}</p>`:""}
  </article>`;
}
function renderTax() {
  const fifo=state.data.fifo,holding=state.data?.metrics?.holding||{},total=Number(holding.total_btc ?? fifo.total_btc ?? 0);
  const pct=value=>total>0?`${fmtNumber(Number(value||0)/total*100,1)} %`:"0 %";
  const stats=[
    [t("overHoldingRule"),`${fmtStack(holding.over_rule_btc ?? fifo.long_term_btc)} · ${holding.over_rule_percent!=null?`${fmtNumber(Number(holding.over_rule_percent),1)} %`:pct(fifo.long_term_btc)}`],
    [t("underHoldingRule"),`${fmtStack(holding.under_rule_btc ?? fifo.short_term_btc)} · ${holding.under_rule_percent!=null?`${fmtNumber(Number(holding.under_rule_percent),1)} %`:pct(fifo.short_term_btc)}`],
    [t("next30Holding"),holding.next_30_btc!=null?`+${fmtStack(holding.next_30_btc)}`:"–"],
    [t("next90Holding"),holding.next_90_btc!=null?`+${fmtStack(holding.next_90_btc)}`:"–"],
    [t("weightedStackAge"),holding.weighted_age_years!=null?`${fmtNumber(Number(holding.weighted_age_years),2)} ${t("yearsUnit")}`:"–"],
    [t("oldestOpenLot"),holding.oldest_open_lot_years!=null?`${fmtNumber(Number(holding.oldest_open_lot_years),2)} ${t("yearsUnit")}`:"–"]
  ];
  if(Number(holding.unknown_btc||fifo.unknown_holding_btc||0)>0)stats.push([t("unknown"),fmtStack(holding.unknown_btc ?? fifo.unknown_holding_btc)]);
  $("#taxSummary").innerHTML=stats.map(([label,value])=>`<div class="tax-stat"><span>${esc(label)}</span><strong>${privateHtml(value)}</strong></div>`).join("");
  const ageHost=$("#holdingAgeDistribution"),distribution=holding.age_distribution||{};
  if(ageHost){const buckets=[["under_1y",t("under1Year")],["1_to_2y",t("oneToTwoYears")],["2_to_4y",t("twoToFourYears")],["over_4y",t("overFourYears")]];ageHost.innerHTML=buckets.map(([key,label])=>{const item=distribution[key]||{},percent=Math.max(0,Math.min(100,Number(item.percent||0)));return `<div class="holding-age-row"><span>${esc(label)}</span><div class="holding-age-track"><div class="holding-age-fill" style="--age-width:${percent.toFixed(2)}%"></div></div><strong>${privateHtml(`${fmtNumber(percent,1)} % · ${fmtStack(Number(item.btc||0))}`)}</strong></div>`;}).join("");}
  const indexes=uiIndexes(),allMatches=indexes.reversedMatches;
  renderFifoSaleSummary(allMatches);
  const pageSize=Math.max(10,Number(state.ledgerPageSize)||25);
  const totalPages=Math.max(1,Math.ceil(allMatches.length/pageSize));
  state.fifoPage=Math.min(Math.max(1,state.fifoPage),totalPages);
  const pageStart=(state.fifoPage-1)*pageSize;
  const pageEnd=Math.min(allMatches.length,pageStart+pageSize);
  const matches=allMatches.slice(pageStart,pageEnd);
  const entryById=indexes.entryById;
  const rowData=match=>{
    const purchase=match.purchase_id==null?null:entryById.get(String(match.purchase_id));
    const sale=match.sale_id==null?null:entryById.get(String(match.sale_id));
    const purchaseCurrency=String(match.purchase_currency||purchase?.currency||match.sale_currency||"").toUpperCase();
    const saleCurrency=String(match.sale_currency||sale?.currency||"").toUpperCase();
    const purchasePrice=Number(match.purchase_price ?? purchase?.price);
    const salePrice=Number(match.sale_price ?? sale?.price);
    const gain=match.realized_gain==null?null:Number(match.realized_gain);
    const basis=match.cost_basis==null?null:Number(match.cost_basis);
    const roi=basis!=null&&basis>0&&gain!=null?(gain/basis)*100:null;
    const averageEntryPrice=match.average_entry_price_to_date==null?null:Number(match.average_entry_price_to_date);
    const averageEntryBasis=Number.isFinite(averageEntryPrice)&&averageEntryPrice>0?Math.max(0,Number(match.amount_btc)||0)*averageEntryPrice:null;
    const averageEntryGain=match.average_entry_gain==null?null:Number(match.average_entry_gain);
    const averageEntryRoi=match.average_entry_return_percent==null?null:Number(match.average_entry_return_percent);
    return {purchase,sale,purchaseCurrency,saleCurrency,purchasePrice,salePrice,gain,basis,roi,averageEntryPrice,averageEntryBasis,averageEntryGain,averageEntryRoi};
  };
  const dispositionLabel=match=>String(match?.disposition_type||"sale")==="expense"?t("dispositionExpense"):t("dispositionSale");
  const compactLayout=compactTableLayout();
  $("#fifoBody").innerHTML=compactLayout?"":matches.map(match=>{
    const d=rowData(match),gainClass=d.gain>0?"positive":d.gain<0?"negative":"";
    const purchasePrice=Number.isFinite(d.purchasePrice)&&d.purchasePrice>0?`${fmtFiat(d.purchasePrice,d.purchaseCurrency)} / BTC`:"–";
    const salePrice=Number.isFinite(d.salePrice)&&d.salePrice>0?`${fmtFiat(d.salePrice,d.saleCurrency)} / BTC`:"–";
    const averageEntryPrice=Number.isFinite(d.averageEntryPrice)&&d.averageEntryPrice>0?`${fmtFiat(d.averageEntryPrice,d.saleCurrency)} / BTC`:"–";
    const averageGainClass=d.averageEntryGain>0?"positive":d.averageEntryGain<0?"negative":"";
    return `<tr><td>${esc(fmtDate(match.sale_timestamp))}</td><td><span class="badge">${esc(dispositionLabel(match))}</span></td><td>${privateHtml(fmtStack(match.amount_btc))}</td><td>${privateHtml(purchasePrice)}${match.purchase_timestamp?`<br><small>${esc(fmtDate(match.purchase_timestamp))}</small>`:""}</td><td>${d.basis==null?"–":privateHtml(fmtFiat(d.basis,d.saleCurrency))}</td><td>${privateHtml(salePrice)}</td><td>${match.net_proceeds==null?"–":privateHtml(fmtFiat(match.net_proceeds,d.saleCurrency))}</td><td class="${gainClass}">${d.gain==null?"–":privateHtml(signedFiat(d.gain,d.saleCurrency))}</td><td class="${gainClass}">${d.roi==null?"–":privateHtml(signedPercent(d.roi))}</td><td class="fifo-fiat-metric" title="${esc(t("averageEntryHint"))}">${privateHtml(averageEntryPrice)}</td><td class="fifo-fiat-metric">${d.averageEntryBasis==null?"–":privateHtml(fmtFiat(d.averageEntryBasis,d.saleCurrency))}</td><td class="fifo-fiat-metric ${averageGainClass}">${d.averageEntryGain==null?"–":privateHtml(signedFiat(d.averageEntryGain,d.saleCurrency))}</td><td class="fifo-fiat-metric ${averageGainClass}">${d.averageEntryRoi==null?"–":privateHtml(signedPercent(d.averageEntryRoi))}</td></tr>`;
  }).join("");
  const fifoCards=$("#fifoCards");
  if(fifoCards)fifoCards.innerHTML=!compactLayout?"":(matches.length?matches.map(match=>{
    const d=rowData(match),gainClass=d.gain>0?"positive":d.gain<0?"negative":"";
    const purchasePrice=Number.isFinite(d.purchasePrice)&&d.purchasePrice>0?`${fmtFiat(d.purchasePrice,d.purchaseCurrency)} / BTC`:"–";
    const salePrice=Number.isFinite(d.salePrice)&&d.salePrice>0?`${fmtFiat(d.salePrice,d.saleCurrency)} / BTC`:"–";
    const averageEntryPrice=Number.isFinite(d.averageEntryPrice)&&d.averageEntryPrice>0?`${fmtFiat(d.averageEntryPrice,d.saleCurrency)} / BTC`:"–";
    const averageGainClass=d.averageEntryGain>0?"positive":d.averageEntryGain<0?"negative":"";
    return `<article class="ledger-mobile-card">
      <div class="ledger-mobile-head"><div><span class="badge">${esc(dispositionLabel(match))}</span><strong>${esc(fmtDate(match.sale_timestamp))}</strong><small>${esc(match.status)}</small></div>${badge(match.holding_status)}</div>
      <dl>
        <div><dt>${esc(t("amount"))}</dt><dd>${privateHtml(fmtStack(match.amount_btc))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("purchasePriceThen"))}</dt><dd>${privateHtml(purchasePrice)}${match.purchase_timestamp?`<small>${esc(fmtDate(match.purchase_timestamp))}</small>`:""}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("fifoCostBasis"))}</dt><dd>${d.basis==null?"–":privateHtml(fmtFiat(d.basis,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("salePrice"))}</dt><dd>${privateHtml(salePrice)}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("saleProceeds"))}</dt><dd>${match.net_proceeds==null?"–":privateHtml(fmtFiat(match.net_proceeds,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("fifoGain"))}</dt><dd class="${gainClass}">${d.gain==null?"–":privateHtml(signedFiat(d.gain,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("fifoReturn"))}</dt><dd class="${gainClass}">${d.roi==null?"–":privateHtml(signedPercent(d.roi))}</dd></div>
        <div class="fifo-average-mobile-heading"><span class="kicker">Ø BIS ZUM ABGANG</span><strong>${esc(t("averageComparisonSummary"))}</strong><small>${esc(t("averageEntryHint"))}</small></div>
        <div class="fifo-fiat-metric" title="${esc(t("averageEntryHint"))}"><dt>${esc(t("averageEntryToDate"))}</dt><dd>${privateHtml(averageEntryPrice)}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("averageEntryBasis"))}</dt><dd>${d.averageEntryBasis==null?"–":privateHtml(fmtFiat(d.averageEntryBasis,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("averageEntryGain"))}</dt><dd class="${averageGainClass}">${d.averageEntryGain==null?"–":privateHtml(signedFiat(d.averageEntryGain,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("averageEntryReturn"))}</dt><dd class="${averageGainClass}">${d.averageEntryRoi==null?"–":privateHtml(signedPercent(d.averageEntryRoi))}</dd></div>
      </dl>
    </article>`;
  }).join(""):`<p class="storage-note">${esc(t("noData"))}</p>`);
  renderFifoPagination(allMatches.length,totalPages,pageStart,pageEnd);
}

function buyOpportunityRatingLabel(rating){
  const key={very_expensive:"ratingVeryExpensive",expensive:"ratingExpensive",neutral:"ratingNeutral",interesting:"ratingInteresting",cheap:"ratingCheap",very_cheap:"ratingVeryCheap",extreme:"ratingExtreme",unavailable:"ratingUnavailable"}[String(rating||"unavailable")];
  return t(key||"ratingUnavailable");
}
function marketBestMarkerPopupHtml(marker){
  const score=Number(marker?.score),bottom=Boolean(marker?.bottom_confirmation_met),zone=Number(marker?.bottom_zone),markerConfirmation=Number(marker?.bottom_confirmation),confirmedZone=Number(marker?.bottom_confirmation_confirmed_zone),confirmedScore=Number(marker?.bottom_confirmation_confirmed_score),lag=Number(marker?.bottom_confirmation_lag_days),confirmedDate=marker?.bottom_confirmation_date;
  const zoneThreshold=Number(marker?.bottom_zone_threshold),confirmationThreshold=Number(marker?.bottom_confirmation_threshold),details=[];
  if(bottom){
    const lagText=Number.isFinite(lag)&&lag>0?walletWatchLang(` · +${fmtNumber(lag,0)} Tage`,` · +${fmtNumber(lag,0)} days`):"";
    details.push(`<div class="market-best-popup-bottom">${esc(walletWatchLang("✓ Boden bestätigt","✓ Bottom confirmed"))}${confirmedDate?` · ${esc(fmtDate(confirmedDate))}${esc(lagText)}`:""}</div>`);
    if(Number.isFinite(confirmedZone))details.push(`<div>${esc(walletWatchLang("Boden-Zone bei Bestätigung","Bottom zone at confirmation"))}: <strong>${esc(fmtNumber(confirmedZone,1))}</strong>${Number.isFinite(zoneThreshold)?` / ${esc(fmtNumber(zoneThreshold,1))}`:""}</div>`);
    if(Number.isFinite(confirmedScore))details.push(`<div>${esc(walletWatchLang("Bestätigungsscore","Confirmation score"))}: <strong>${esc(fmtNumber(confirmedScore,1))}</strong>${Number.isFinite(confirmationThreshold)?` / ${esc(fmtNumber(confirmationThreshold,1))}`:""}</div>`);
  }else{
    if(Number.isFinite(zone))details.push(`<div>${esc(walletWatchLang("Boden-Zone","Bottom zone"))}: <strong>${esc(fmtNumber(zone,1))}</strong>${Number.isFinite(zoneThreshold)?` / ${esc(fmtNumber(zoneThreshold,1))}`:""}</div>`);
    if(Number.isFinite(markerConfirmation))details.push(`<div>${esc(walletWatchLang("Bestätigung am Bestwert-Tag","Confirmation on best-value day"))}: <strong>${esc(fmtNumber(markerConfirmation,1))}</strong>${Number.isFinite(confirmationThreshold)?` / ${esc(fmtNumber(confirmationThreshold,1))}`:""}</div>`);
  }
  return `<strong>★ ${esc(walletWatchLang("Bestwert","Best value"))} · ${esc(Number.isFinite(score)?fmtNumber(score,1):"–")} / 100</strong><div>${esc(fmtDate(marker?.date))} · ${esc(buyOpportunityRatingLabel(marker?.rating))}</div>${details.join("")}`;
}
function positionChartPopup(tooltip,panel,clientX,clientY){
  if(!tooltip||!panel)return;const rect=panel.getBoundingClientRect(),desiredLeft=clientX-rect.left+14,maxLeft=Math.max(10,rect.width-tooltip.offsetWidth-12);tooltip.style.left=`${Math.max(10,Math.min(maxLeft,desiredLeft))}px`;tooltip.style.top=`${Math.max(54,clientY-rect.top-tooltip.offsetHeight-14)}px`;
}
function buyOpportunityRatingClass(rating){
  const value=String(rating||"");
  if(["cheap","very_cheap","extreme"].includes(value))return "positive";
  if(["very_expensive","expensive"].includes(value))return "negative";
  return "";
}
function marketPhaseLabel(phase){const key={bottoming_possible:"phaseBottoming",capitulation:"phaseCapitulation",top_formation_possible:"phaseTopFormation",overheating:"phaseOverheating",recovery:"phaseRecovery",cooling:"phaseCooling",depressed:"phaseDepressed",expansion:"phaseExpansion",neutral:"phaseNeutral"}[String(phase||"neutral")];return t(key||"phaseNeutral");}
function renderBuyOpportunity(){
  const result=state.data?.buy_opportunity||{},score=result.score_raw??result.score,host=$("#buyOpportunityPanel");
  const overviewScore=$("#marketAssessmentOverviewScore"),overviewRating=$("#marketAssessmentOverviewRating");
  const setSummary=(value,rating)=>{if(overviewScore)overviewScore.textContent=value==null?"–":fmtNumber(value,1);if(overviewRating){overviewRating.textContent=buyOpportunityRatingLabel(rating);overviewRating.className=`badge ${buyOpportunityRatingClass(rating)}`;}};
  if(!host){setSummary(score,result.rating||"unavailable");return;}
  const scoreEl=$("#buyOpportunityScore"),ratingEl=$("#buyOpportunityRating"),componentsEl=$("#buyOpportunityComponents"),indicatorsEl=$("#buyOpportunityIndicators"),hintEl=$("#buyOpportunityDataHint");
  if(score==null){
    scoreEl.textContent="–";ratingEl.textContent=buyOpportunityRatingLabel("unavailable");ratingEl.className="badge";setSummary(null,"unavailable");
    componentsEl.innerHTML="";indicatorsEl.innerHTML="";
    const quality=result.data_quality||{};hintEl.textContent=result.reason==="insufficient_history"?`${t("dataCoverage")}: ${fmtNumber(quality.history_points??result.history_points??0,0)} ${t("historyPoints")}`:t("ratingUnavailable");
    return;
  }
  setSummary(score,result.rating);
  scoreEl.textContent=fmtNumber(score,1);ratingEl.textContent=buyOpportunityRatingLabel(result.rating);ratingEl.className=`badge ${buyOpportunityRatingClass(result.rating)}`;
  const components=result.component_scores||{};
  componentsEl.innerHTML=BUY_OPPORTUNITY_COMPONENTS.map(key=>{const value=Number(components[key]);return `<article><span>${esc(t(BUY_OPPORTUNITY_COMPONENT_LABEL[key]))}</span><strong>${Number.isFinite(value)?`${fmtNumber(value,0)} / 100`:"–"}</strong><div class="buy-opportunity-bar"><i style="--score-width:${Number.isFinite(value)?Math.max(0,Math.min(100,value)):0}%"></i></div></article>`;}).join("");
  const ind=result.indicators||{},periods=ind.configured_periods||{};
  const indicatorRows=[
    [t("mayerMultiple"),ind.mayer_multiple==null?"–":fmtNumber(ind.mayer_multiple,2)],
    [t("athDrawdown"),ind.ath_drawdown_pct==null?"–":signedPercent(-Math.abs(Number(ind.ath_drawdown_pct)))],
    [t("pricePercentile"),ind.percentile_365d==null?"–":`${fmtNumber(ind.percentile_365d,0)} %`],
    [`${t("rsi14")} (${periods.rsi_period_days||14})`,ind.rsi_14==null?"–":fmtNumber(ind.rsi_14,1)],
    [`${t("distanceSma200")} (${periods.trend_base_days||200}D)`,ind.distance_sma200_pct==null?"–":signedPercent(Number(ind.distance_sma200_pct))],
    [t("powerLawRatio"),ind.power_law_ratio==null?"–":fmtNumber(ind.power_law_ratio,2)]
  ];
  indicatorsEl.innerHTML=indicatorRows.map(([label,value])=>`<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  const turning=result.turning_points||{},turningHost=$("#turningPointCards"),phaseHint=$("#marketPhaseHint");
  if(turningHost){const cards=[["bottomZone",turning.bottom_zone],["bottomConfirmation",turning.bottom_confirmation],["topZone",turning.top_zone],["topConfirmation",turning.top_confirmation]];turningHost.innerHTML=cards.map(([label,value])=>{const n=Number(value);return `<article><span>${esc(t(label))}</span><strong>${Number.isFinite(n)?`${fmtNumber(n,0)} / 100`:"–"}</strong><div class="buy-opportunity-bar"><i style="--score-width:${Number.isFinite(n)?Math.max(0,Math.min(100,n)):0}%"></i></div></article>`;}).join("");}
  if(phaseHint)phaseHint.textContent=`${t("marketPhase")}: ${marketPhaseLabel(turning.market_phase)} · ${state.lang==="de"?"nur Preis-Historie · keine neue externe Datenquelle":"price history only · no new external data source"}`;
  const quality=result.data_quality||{};
  hintEl.textContent=`${t("dataCoverage")}: ${fmtNumber(quality.history_points||0,0)} ${t("historyPoints")} · ${fmtNumber(quality.weight_coverage_pct||0,0)} % · ${t("scoreVersion")}: ${result.score_version||"–"}`;
}
function buyOpportunitySettingsDefaults(){return {profile:"balanced",currency:(state.data?.currencies||[])[0]||"EUR",weights:{...BUY_OPPORTUNITY_PRESETS.balanced},signal_weights:structuredClone(BUY_OPPORTUNITY_SIGNAL_DEFAULTS),turning_point_weights:structuredClone(BUY_OPPORTUNITY_TURNING_DEFAULTS),model:{...BUY_OPPORTUNITY_MODEL_DEFAULTS},thresholds:{very_expensive_max:20,expensive_max:35,interesting:50,cheap:65,very_cheap:80,extreme:90}};}
function setBuyOpportunityWeightInputs(weights={}){
  const form=$("#buyOpportunitySettingsForm");if(!form)return;
  for(const key of BUY_OPPORTUNITY_COMPONENTS){const input=form.elements[`weight_${key}`];if(input)input.value=String(Number(weights[key]??BUY_OPPORTUNITY_PRESETS.balanced[key]));}
}
function setBuyOpportunitySignalInputs(signalWeights={}){
  const form=$("#buyOpportunitySettingsForm");if(!form)return;
  for(const [component,defaults] of Object.entries(BUY_OPPORTUNITY_SIGNAL_DEFAULTS))for(const [key,defaultValue] of Object.entries(defaults)){const input=form.elements[`signal_${component}_${key}`];if(input)input.value=String(Number(signalWeights?.[component]?.[key]??defaultValue));}
}
function setBuyOpportunityTurningInputs(turningWeights={}){const form=$("#buyOpportunitySettingsForm");if(!form)return;for(const [modelName,defaults] of Object.entries(BUY_OPPORTUNITY_TURNING_DEFAULTS))for(const [key,defaultValue] of Object.entries(defaults)){const input=form.elements[`turn_${modelName}_${key}`];if(input)input.value=String(Number(turningWeights?.[modelName]?.[key]??defaultValue));}}
function setBuyOpportunityModelInputs(model={}){
  const form=$("#buyOpportunitySettingsForm");if(!form)return;
  for(const key of BUY_OPPORTUNITY_MODEL_KEYS){const input=form.elements[`model_${key}`];if(input)input.value=String(Number(model[key]??BUY_OPPORTUNITY_MODEL_DEFAULTS[key]));}
}
function renderBuyOpportunityFieldHelp(){
  const form=$("#buyOpportunitySettingsForm");if(!form)return;
  for(const control of form.querySelectorAll("input[name],select[name]")){
    const label=control.closest("label"),help=BUY_OPPORTUNITY_FIELD_HELP[String(control.name||"")];if(!label||!help)continue;
    let note=label.querySelector(":scope > .buy-opportunity-field-help");
    if(!note){note=document.createElement("small");note.className="buy-opportunity-field-help";label.appendChild(note);}
    note.textContent=state.lang==="de"?help[0]:help[1];
  }
}
function renderBuyOpportunitySettings(){
  const form=$("#buyOpportunitySettingsForm");if(!form)return;
  const defaults=buyOpportunitySettingsDefaults(),settings=state.data?.buy_opportunity_settings||defaults,owner=Boolean(state.data?.security?.owner);
  const profile=$("#buyOpportunityProfile"),currency=$("#buyOpportunityCurrency");
  profile.value=String(settings.profile||"balanced");
  const currencies=state.data?.currencies||[];currency.innerHTML=currencies.map(code=>`<option value="${esc(code)}">${esc(code)}</option>`).join("");currency.value=String(settings.currency||currencies[0]||"EUR");
  setBuyOpportunityWeightInputs(settings.weights||defaults.weights);setBuyOpportunitySignalInputs(settings.signal_weights||defaults.signal_weights);setBuyOpportunityTurningInputs(settings.turning_point_weights||defaults.turning_point_weights);setBuyOpportunityModelInputs(settings.model||defaults.model);
  const thresholds=settings.thresholds||defaults.thresholds;
  for(const key of ["very_expensive_max","expensive_max","interesting","cheap","very_cheap","extreme"]){const input=form.elements[`threshold_${key}`];if(input)input.value=String(Number(thresholds[key]??defaults.thresholds[key]));}
  for(const element of form.querySelectorAll("input,select,button"))element.disabled=!owner;
  const result=state.data?.buy_opportunity||{},quality=result.data_quality||{},preview=$("#buyOpportunitySettingsPreview");
  preview.textContent=result.score==null?t("ratingUnavailable"):`${t("marketAssessment")}: ${result.score}/100 · ${buyOpportunityRatingLabel(result.rating)} · ${t("dataCoverage")}: ${fmtNumber(quality.weight_coverage_pct||0,0)} %`;
  preview.className="result";
  renderBuyOpportunityFieldHelp();
}
function collectBuyOpportunitySignalWeights(form){
  const result={};for(const [component,defaults] of Object.entries(BUY_OPPORTUNITY_SIGNAL_DEFAULTS)){result[component]={};for(const key of Object.keys(defaults))result[component][key]=Number(form.elements[`signal_${component}_${key}`].value||0);}return result;
}
function collectBuyOpportunityTurningWeights(form){const result={};for(const [modelName,defaults] of Object.entries(BUY_OPPORTUNITY_TURNING_DEFAULTS)){result[modelName]={};for(const key of Object.keys(defaults))result[modelName][key]=Number(form.elements[`turn_${modelName}_${key}`].value||0);}return result;}
function collectBuyOpportunityModel(form){return Object.fromEntries(BUY_OPPORTUNITY_MODEL_KEYS.map(key=>[key,Number(form.elements[`model_${key}`].value)]));}
async function saveBuyOpportunitySettings(event){
  if(event){event.preventDefault();event.stopPropagation();}
  const form=$("#buyOpportunitySettingsForm"),button=$("#saveBuyOpportunitySettingsButton"),preview=$("#buyOpportunitySettingsPreview");if(!form||!button)return;
  const weights=Object.fromEntries(BUY_OPPORTUNITY_COMPONENTS.map(key=>[key,Number(form.elements[`weight_${key}`].value||0)]));
  const signal_weights=collectBuyOpportunitySignalWeights(form),turning_point_weights=collectBuyOpportunityTurningWeights(form),model=collectBuyOpportunityModel(form);
  const thresholds=Object.fromEntries(["very_expensive_max","expensive_max","interesting","cheap","very_cheap","extreme"].map(key=>[key,Number(form.elements[`threshold_${key}`].value||0)]));
  if(!(thresholds.very_expensive_max<thresholds.expensive_max&&thresholds.expensive_max<thresholds.interesting&&thresholds.interesting<thresholds.cheap&&thresholds.cheap<thresholds.very_cheap&&thresholds.very_cheap<thresholds.extreme)){preview.textContent=state.lang==="de"?"Grenzen müssen aufsteigend sein: Sehr hoch < Hoch < Interessant < Günstig < Sehr günstig < Extrem günstig":"Thresholds must ascend: Very high < High < Interesting < Cheap < Very cheap < Extremely cheap";preview.className="result negative";return;}
  if(!(model.volatility_regime_low_ratio<model.volatility_regime_high_ratio)){preview.textContent=state.lang==="de"?"Die Grenze für das niedrige Volatilitätsregime muss unter der hohen Grenze liegen.":"The low-volatility regime threshold must be below the high threshold.";preview.className="result negative";return;}
  if(!(model.volatility_fast_window_days<model.volatility_slow_window_days)){preview.textContent=state.lang==="de"?"Die schnelle Volatilitätsperiode muss kürzer als die langsame sein.":"The fast volatility window must be shorter than the slow window.";preview.className="result negative";return;}
  if(!(model.turning_point_separation_days<model.turning_point_lookback_days)){preview.textContent=state.lang==="de"?"Der Swing-Mindestabstand muss kürzer als der Wendepunkt-Lookback sein.":"Swing separation must be shorter than the turning-point lookback.";preview.className="result negative";return;}
  if(!(model.turning_zone_threshold<model.turning_extreme_threshold)){preview.textContent=state.lang==="de"?"Die Wendepunkt-Zonengrenze muss unter der Extremgrenze liegen.":"The turning-point zone threshold must be below the extreme threshold.";preview.className="result negative";return;}
  if(Object.values(weights).reduce((sum,value)=>sum+Math.max(0,value),0)<=0){preview.textContent=state.lang==="de"?"Mindestens ein Gruppengewicht muss größer als 0 sein.":"At least one group weight must be greater than 0.";preview.className="result negative";return;}
  button.disabled=true;
  try{
    const response=await service("set_buy_opportunity_settings",{config_entry_id:state.entryId,profile:form.elements.profile.value,currency:form.elements.currency.value,weights,signal_weights,turning_point_weights,model,thresholds});
    state.data.buy_opportunity_settings=response.settings||state.data.buy_opportunity_settings;
    preview.textContent=t("buyOpportunitySaved");preview.className="result positive";toast(t("buyOpportunitySaved"));state.marketAssessmentHistory=null;state.chartMarketAssessmentHistory=null;await loadData();if(state.activeTab==="market")void loadMarketAssessmentHistory({force:true});if(state.activeTab==="overview"&&state.chartMode==="price_market")void ensureChartMarketAssessmentHistory({force:true});
  }catch(error){preview.textContent=error.message||String(error);preview.className="result negative";toast(error.message||String(error));}
  finally{button.disabled=!state.data?.security?.owner;}
}
async function resetBuyOpportunitySettings(){
  const button=$("#resetBuyOpportunitySettingsButton"),preview=$("#buyOpportunitySettingsPreview");if(!button)return;button.disabled=true;
  try{const response=await service("set_buy_opportunity_settings",{config_entry_id:state.entryId,currency:$("#buyOpportunityCurrency")?.value||"EUR",reset_defaults:true});state.data.buy_opportunity_settings=response.settings;state.marketAssessmentHistory=null;state.chartMarketAssessmentHistory=null;preview.textContent=t("marketAssessmentReset");preview.className="result positive";toast(t("marketAssessmentReset"));await loadData();if(state.activeTab==="market")void loadMarketAssessmentHistory({force:true});if(state.activeTab==="overview"&&state.chartMode==="price_market")void ensureChartMarketAssessmentHistory({force:true});}
  catch(error){preview.textContent=error.message||String(error);preview.className="result negative";toast(error.message||String(error));}
  finally{button.disabled=!state.data?.security?.owner;}
}

function historySourceSummary(item={}) {
  const labels=[];
  const add=value=>{
    let label=String(value||"").trim();
    if(!label)return;
    if(label.toLowerCase()==="own mempool instance only")label="own mempool instance";
    if(!labels.some(existing=>existing.toLowerCase()===label.toLowerCase()))labels.push(label);
  };
  add(item.preferred_history_source);
  add(item.primary_history_source);
  add(item.fallback_history_source);
  return labels.join(" + ")||"local cache";
}

function renderHistorySettings() {
  const history=state.data.history||{},owner=Boolean(state.data.security?.owner);
  $("#historyEnabled").checked=Boolean(history.enabled);
  $("#historyAutoSync").checked=Boolean(history.auto_sync);
  $("#historyTorProxy").value=history.tor_proxy||"";
  $("#historyAutoSync").disabled=!history.enabled||!owner;
  $("#historyEnabled").disabled=!owner;
  $("#historyTorProxy").disabled=!owner;
  $("#saveHistorySettingsButton").disabled=!owner;
  $("#syncButton").disabled=!history.enabled;
  const counts=history.cached_daily_values||{},sampleCounts=history.cached_price_samples||{},marketCounts=history.cached_market_candles||{},metadata=history.source_metadata||{};
  const rows=[];
  rows.push([t("lastSync"),history.last_sync?fmtDate(history.last_sync):t("never")]);
  const autoRuntime = Boolean(history.auto_sync_runtime_active);
  rows.push([t("historyAutomation"), history.auto_sync && autoRuntime ? `${t("historyAutomationActive")} · ${t("historyAutoRetryHint")}` : t("historyAutomationInactive")]);
  if (history.auto_sync_last_attempt) rows.push([t("historyAutoLastAttempt"), `${fmtDateTime(history.auto_sync_last_attempt)} · ${history.auto_sync_last_result || "–"}`]);
  rows.push([t("torOnly"),history.public_route||"Tor only"]);
  for(const [currency,count] of Object.entries(counts)){
    const item=metadata[currency]||{};
    const source=historySourceSummary(item);
    rows.push([`${t("cachedValues")} ${currency}`,`${fmtNumber(count,0)} ${t("dataPoints")} · ${source}`]);
    const chain=Array.isArray(item.history_source_chain)?item.history_source_chain:[];
    if(chain.length) rows.push([`${t("sourceCascade")} ${currency}`,chain.map(part=>`${part.source||"?"} [${part.first_day||"?"} → ${part.last_day||"?"}]`).join(" → ")]);
    if(Number(sampleCounts[currency]||0)>0) rows.push([`${t("finePriceSamples")} ${currency}`,`${fmtNumber(sampleCounts[currency],0)} · ${t("finePriceSamplesHint")}`]);
    const tiers=marketCounts[currency]||{};
    if(Object.keys(tiers).length) rows.push([`${t("exactCandles")} ${currency}`,Object.entries(tiers).sort((a,b)=>Number(a[0])-Number(b[0])).map(([minutes,total])=>`${minutes<60?`${minutes}m`:`${Number(minutes)/60}h`}: ${fmtNumber(total,0)}`).join(" · ")]);
  }
  if(history.errors?.length)rows.push(["Fehler",history.errors.join(" · ")]);
  $("#historyDetails").innerHTML=rows.map(([label,value])=>`<div class="history-detail"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  const selectedInterval=chartIntervalMinutesForRange(),selectedCurrency=currentCurrency();
  if(history.enabled && selectedInterval < 1440){
    const selectedCount=Number((marketCounts[selectedCurrency]||{})[String(selectedInterval)]||0);
    const intervalLabel=selectedInterval<60?`${selectedInterval} min`:`${selectedInterval/60} h`;
    if(selectedCount>=2){
      $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: ${fmtNumber(selectedCount,0)} Kerzen · ${intervalLabel} · einheitliches Raster`;
    }else if(selectedInterval===720){
      const fallbackCount=history.series_loaded?Object.keys(resampleLongRangeUniform(history.prices?.[selectedCurrency]||{})).length:Number(counts[selectedCurrency]||0);
      $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: ${fmtNumber(fallbackCount,0)} Punkte · 1 Tag Fallback · einheitliches Raster`;
    }else{
      $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: 0 Kerzen · ${intervalLabel} · Abruf erforderlich`;
    }
  }else if(history.enabled){
    if(!history.series_loaded){
      const cached=Number(counts[selectedCurrency]||0);
      $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: ${fmtNumber(cached,0)} ${t("dataPoints")} · ${t("loadingChart")}`;
    }else{
      const daily=history.prices?.[selectedCurrency]||{}, uniform=resampleLongRangeUniform(daily), stepDays=longRangeUniformStepDays(daily);
      $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: ${fmtNumber(Object.keys(uniform).length,0)} Punkte · ${stepDays} Tag${stepDays===1?"":"e"} · einheitliches Raster`;
    }
  }else{
    $("#historyStatus").textContent=`${t("historyDisabled")} · ${historyCountSummary(counts)}`;
  }
}
function networkPresentation(addon) {
  const leak=Boolean(addon.clearnet_leak_detected);
  const stateCode=String(addon.tor_connection_state||"connecting");
  if(leak)return {css:"is-error",label:t("clearnetLeak")};
  if(stateCode==="connected")return {css:"is-online",label:t("onlyTorOnline")};
  if(stateCode==="connecting"){
    const progress=Number(addon.tor_bootstrap_percent);
    const suffix=Number.isFinite(progress)?` · ${Math.max(0,Math.min(100,Math.round(progress)))} %`:"";
    return {css:"is-checking",label:`${t("torConnecting")}${suffix}`};
  }
  if(stateCode==="disconnected")return {css:"is-error",label:t("torDisconnected")};
  if(stateCode==="not-established")return {css:"is-error",label:t("torNotEstablished")};
  if(stateCode==="protection-fault")return {css:"is-error",label:t("protectionFault")};
  return {css:"is-error",label:t("torError")};
}
function renderNetworkStatus() {
  const addon=state.network||{tor_connection_state:"connecting"},core=state.data?.network_security||{};
  const firewall=Boolean(addon.killswitch_active),tor=Boolean(addon.tor_verified);
  const presentation=networkPresentation(addon);
  const badge=$("#networkBadge"),badgeText=$("#networkBadgeText"),alert=$("#networkAlert");
  badge.classList.remove("is-checking","is-online","is-offline","is-error");
  badge.classList.add(presentation.css);
  badgeText.textContent=presentation.label;
  const localizedError=localizeNetworkError(addon.tor_error);
  badge.title=localizedError?`${presentation.label}: ${localizedError}`:presentation.label;
  alert.className=`network-alert ${presentation.css}`;
  const cacheNote=presentation.css==="is-online"?"":` · ${t("localCacheOnly")}`;
  alert.textContent=`${presentation.label}${cacheNote}${localizedError?` · ${localizedError}`:""}`;
  const blockedAddon=Number(addon.blocked_direct_packets||0),blockedCore=Number(core.blocked_direct_requests||0);
  const directSockets=Number(addon.non_tor_public_socket_count||0),leakTargets=(addon.non_tor_public_socket_targets||[]).join(", ");
  const rows=[
    [t("killswitch"),firewall?t("active"):t("inactive")],
    [t("torVerified"),tor?t("yes"):t("no")],
    ...(Number.isFinite(Number(addon.tor_bootstrap_percent))?[[t("torBootstrap"),`${fmtNumber(Number(addon.tor_bootstrap_percent),0)} %`]]:[]),
    [t("torExitIp"),addon.tor_exit_ip||"–"],
    ...(state.torRotation?[[t("automaticTorRotation"),state.torRotation.enabled?`${t("active")} · ${Number(state.torRotation.interval_minutes||30)} min`:t("inactive")]]:[]),
    ...(state.torRotation?.last_previous_ip?[[t("previousExitIp"),state.torRotation.last_previous_ip]]:[]),
    ...(state.torRotation?.last_rotated_at?[[t("lastRotation"),fmtDateTime(state.torRotation.last_rotated_at)]]:[]),
    ...(state.torRotation?.enabled&&state.torRotation?.next_rotation_at?[[t("nextRotation"),fmtDateTime(state.torRotation.next_rotation_at)]]:[]),
    [t("remoteDns"),addon.remote_dns_enforced&&addon.safe_socks_enforced?t("active"):t("inactive")],
    [t("directClearnet"),directSockets?fmtNumber(directSockets,0):t("noneAllowed")],
    ...(leakTargets?[[t("leakTargets"),leakTargets]]:[]),
    [t("blockedConnections"),fmtNumber(blockedAddon,0)],
    [t("coreBlocked"),fmtNumber(blockedCore,0)],
    [t("localConnections"),fmtNumber(core.local_direct_requests||0,0)],
    [t("lastBlocked"),core.last_blocked_host||"–"],
    [t("checkedAt"),addon.checked_at?fmtDate(addon.checked_at):"–"],
    [t("appBuild"),addon.app_version||BUILD_VERSION]
  ];
  const grid=$("#networkStatusGrid");
  if(grid)grid.innerHTML=rows.map(([label,value])=>`<div class="network-status-item"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  const bootstrapReady=Number(addon.tor_bootstrap_percent)===100;
  const button=$("#leakTestButton");
  if(button){
    button.disabled=!state.entryId||networkRefreshInFlight||!bootstrapReady;
    button.title=!bootstrapReady?t("torStarting"):"";
  }
  const identityButton=$("#newTorIdentityButton");
  if(identityButton){
    identityButton.disabled=!state.data?.security?.owner||!bootstrapReady||presentation.css!=="is-online";
    identityButton.title=!bootstrapReady?t("torStarting"):"";
  }
  renderConnections();
}
function connectionRouteLabel(route){
  const value=String(route||"").toLowerCase();
  if(value.includes("tor-relay"))return t("routeTorRelay");
  if(value.includes("blocked"))return t("routeBlocked");
  if(value.includes("tor"))return t("routeTor");
  if(value.includes("local-direct")||value==="direct")return t("routeLocal");
  if(value.includes("ha-local")||value.includes("internal"))return t("routeHaLocal");
  return route||"–";
}
function connectionPurposeLabel(purpose){
  const value=String(purpose||"");
  if(value==="live-price")return t("purposeLivePrice");
  if(value==="history")return t("purposeHistory");
  if(value==="observed")return t("purposeObserved");
  if(value==="tor-check")return t("purposeTorCheck");
  if(value==="tor-transport")return t("purposeTorTransport");
  if(value==="blocked")return t("purposeBlocked");
  return t("purposeInternal");
}
function connectionRow(item){
  const active=Number(item.active||0);
  const status=active>0?`${t("connectionActive")} · ${active}`:(item.last_success_at||item.last_update?t("connectionReady"):(item.configured?t("connectionConfigured"):t("connectionNever")));
  const last=item.last_success_at||item.last_update;
  const rowClass=item.severity==="danger"?"is-danger":(active>0?"is-active":"");
  const providerPrices=item.provider_prices&&typeof item.provider_prices==="object"
    ?Object.entries(item.provider_prices).map(([currency,value])=>`BTC/${esc(currency)} ${esc(fmtNumber(value,2))}`).join(" · ")
    :"";
  return `<div class="connection-row ${rowClass}"><div><strong>${esc(item.label||item.target||"–")}</strong><small>${esc(connectionPurposeLabel(item.purpose))}${providerPrices?` · ${providerPrices}`:""}</small></div><div><span>${esc(t("connectionTarget"))}</span><code>${esc(item.target||"–")}</code></div><div><span>${esc(t("connectionPath"))}</span><strong>${esc(connectionRouteLabel(item.route))}</strong></div><div><span>${esc(t("connectionStatus"))}</span><strong>${esc(status)}</strong>${last?`<small>${esc(fmtDateTime(last))}</small>`:""}</div></div>`;
}
function renderConnections(){
  const summary=$("#connectionSummary"),inventory=$("#connectionInventory"),button=$("#refreshConnectionsButton"),refreshResult=$("#connectionRefreshResult");
  if(!summary||!inventory)return;
  const owner=Boolean(state.data?.security?.owner);
  if(button){button.disabled=!owner||connectionRefreshInFlight;button.textContent=connectionRefreshInFlight?t("refreshingConnections"):t("refreshConnections");}
  if(!owner){summary.innerHTML="";inventory.innerHTML=`<p class="storage-note">${esc(t("connectionOwnerOnly"))}</p>`;return;}
  const protocol=location.protocol==="https:"?"HTTPS":"HTTP";
  const torState=networkPresentation(state.network||{}).label;
  const panelVersion=String(state.data?.addon_version||state.network?.app_version||BUILD_VERSION||"–");
  const integrationVersion=String(state.data?.integration_version||state.data?.portfolio?.version||"–");
  const mismatch=panelVersion!=="–"&&integrationVersion!=="–"&&panelVersion!==integrationVersion;
  summary.innerHTML=[
    ["Browser → Home Assistant Core",`${protocol} · native HA panel · ${location.host}`,false],
    ["Tresor-/CSV-Pfad","Direkt in Home Assistant Core · kein Add-on-Proxy",false],
    ["Öffentliche Requests","Core → interner SOCKS5 → Tor-Gateway → Tor-Circuit → HTTPS-API",false],
    ["Direkter Clearnet-Fallback","BLOCKIERT · Core-Policy + nftables-Killswitch",false],
    ["Core → Tor Gateway",torState,false],
    [t("connectionVersions"),`Panel ${panelVersion} · Integration ${integrationVersion}`,mismatch]
  ].map(([label,value,warn])=>`<div class="connection-summary-item ${warn?"is-warning":""}"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  const data=state.connectionInventory||state.data?.connection_inventory||{};
  const live=data.live_price_sources||[],history=data.history_sources||[],system=data.system_sources||[],observed=data.observed_connections||[];
  const network=state.network||{};
  const transport=[];
  for(const target of (network.app_local_socket_targets||[]))transport.push({label:"Core → Tor-Gateway (interner SOCKS5-Hop)",target,route:"ha-local",purpose:"internal",active:network.tor_verified?1:0});
  for(const target of (network.tor_public_socket_targets||[]))transport.push({label:"Tor Guard/Relay",target,route:"tor-relay",purpose:"tor-transport",active:1});
  for(const target of (network.non_tor_public_socket_targets||[]))transport.push({label:"NICHT-Tor Public Socket",target,route:"blocked",purpose:"blocked",active:1,severity:"danger"});
  const groups=[
    [t("livePriceSources"),live],
    [t("historySources"),history],
    [t("systemSources"),system],
    [t("observedConnections"),observed.map(item=>({...item,label:item.target,purpose:"observed"}))],
    [t("transportConnections"),transport]
  ];
  const notes=[];
  if(mismatch)notes.push(`<p class="result negative">${esc(t("connectionVersionMismatch"))}</p>`);
  if(data.inventory_origin==="legacy-fallback")notes.push(`<p class="storage-note">${esc(t("connectionCompatFallback"))}</p>`);
  const averages=data.live_price_averages||{};
  const averageRows=Object.entries(averages).map(([currency,item])=>{
    const price=Number(item?.price);
    const count=Number(item?.source_count||0);
    const spread=Number(item?.spread_pct||0);
    return `<div class="connection-summary-item"><span>${esc(t("livePriceAverage"))} BTC/${esc(currency)}</span><strong>${Number.isFinite(price)?esc(fmtNumber(price,2)):"–"}</strong><small>${esc(t("sourcesUsed"))}: ${esc(count)}${Number.isFinite(spread)?` · Spread ${esc(fmtNumber(spread,3))} %`:""}</small></div>`;
  }).join("");
  const routeExplanation=`<section class="connection-route-explanation"><h3>${esc(t("transportPathTitle"))}</h3><p>${esc(t("transportPathText"))}</p><small>${esc(t("transportExitNote"))}</small></section>`;
  inventory.innerHTML=notes.join("")+averageRows+routeExplanation+groups.map(([title,items])=>`<section class="connection-group"><h3>${esc(title)}</h3>${items.length?items.map(connectionRow).join(""):`<p class="storage-note">${esc(t("connectionNoData"))}</p>`}</section>`).join("");
  if(refreshResult){
    const info=state.connectionRefresh;
    if(!info){refreshResult.textContent="";refreshResult.className="result";}
    else if(info.status==="running"){refreshResult.textContent=t("refreshingConnections");refreshResult.className="result";}
    else if(info.status==="ok"){
      const bits=[t("connectionsRefreshed")];
      if(info.at)bits.push(`${t("viewRefreshedAt")}: ${fmtDateTime(info.at)}`);
      if(info.liveAt)bits.push(`${t("livePriceRefreshedAt")}: ${fmtDateTime(info.liveAt)}`);
      refreshResult.textContent=bits.join(" · ");refreshResult.className="result positive";
    }else{refreshResult.textContent=`${t("connectionsRefreshFailed")}: ${info.error||""}`;refreshResult.className="result negative";}
  }
}


async function refreshConnectionInventory({silent=false,refreshLive=false}={}){
  if(!state.entryId||!state.data?.security?.owner)return;
  connectionRefreshInFlight=true;
  if(!silent)state.connectionRefresh={status:"running"};
  renderConnections();
  try{
    const liveParam=refreshLive?"&refresh_live=1":"";
    const result=await api(`api/core-network?entry_id=${encodeURIComponent(state.entryId)}${liveParam}`,{timeoutMs:refreshLive?35000:8000});
    state.connectionInventory=result.connection_inventory||state.connectionInventory;
    if(result.network_security&&state.data)state.data.network_security=result.network_security;
    if(result.integration_version&&state.data)state.data.integration_version=result.integration_version;
    if(!silent)state.connectionRefresh={status:"ok",at:result.refreshed_at||new Date().toISOString(),liveAt:result.live_price_updated_at||null};
    renderConnections();
    if(!silent)toast(t("connectionsRefreshed"));
    return result;
  }catch(error){
    if(!silent)state.connectionRefresh={status:"error",error:error.message||String(error),at:new Date().toISOString()};
    renderConnections();
    if(!silent)toast(error.message||String(error));
    return null;
  }finally{
    connectionRefreshInFlight=false;
    renderConnections();
  }
}


async function refreshNetworkStatus({force=false,interactive=false,silent=false}={}) {
  if(!state.entryId||!state.data?.security?.owner)return state.network;
  const button=$("#leakTestButton"),result=$("#leakTestResult");
  if(networkRefreshInFlight){
    if(!interactive)return state.network;
    state.leakTest={status:"running"};
    renderLeakTestResult();
    await new Promise(resolve=>setTimeout(resolve,250));
    return refreshNetworkStatus({force,interactive,silent});
  }
  networkRefreshInFlight=true;
  if(interactive){
    if(button){button.disabled=true;button.textContent=t("checking");}
    state.network={...(state.network||{}),tor_connection_state:"connecting",tor_verified:false,tor_error:null};
    state.leakTest={status:"running"};
    renderLeakTestResult();
    renderNetworkStatus();
  }
  try{
    if(force){
      state.network=await api(`api/network-status?force=1&entry_id=${encodeURIComponent(state.entryId)}`, {timeoutMs:35000});
    }else{
      state.network=await api(`api/network-status?entry_id=${encodeURIComponent(state.entryId)}`, {timeoutMs:25000});
    }
    if(state.network?.tor_last_rotated_at){
      state.torRotation={...(state.torRotation||{}),last_rotated_at:state.network.tor_last_rotated_at};
    }
    renderNetworkStatus();
    if(interactive){
      const failed=Boolean(state.network.clearnet_leak_detected)||state.network.tor_connection_state!=="connected";
      state.leakTest=failed
        ? {status:"failed",detail:`${networkPresentation(state.network).label}${state.network.tor_error?` · ${localizeNetworkError(state.network.tor_error)}`:""}`}
        : {status:"passed"};
      renderLeakTestResult();
    }
    return state.network;
  }catch(error){
    state.network={...(state.network||{}),tor_connection_state:"error",tor_verified:false,tor_error:error.message||String(error)};
    renderNetworkStatus();
    if(interactive){state.leakTest={status:"failed",detail:localizeNetworkError(error.message||String(error))};renderLeakTestResult();}
    if(!silent)toast(error.message||String(error));
    return state.network;
  }finally{
    networkRefreshInFlight=false;
    if(button){button.textContent=t("runLeakTest");button.disabled=!state.entryId;}
  }
}
async function refreshLivePrice({silent=true}={}){
  if(livePriceRefreshInFlight||!state.entryId||!state.data)return false;
  const requestedEntry=state.entryId;
  livePriceRefreshInFlight=true;
  try{
    const result=await api(`api/live-price?entry_id=${encodeURIComponent(requestedEntry)}`,{timeoutMs:7000});
    if(requestedEntry!==state.entryId||!state.data)return false;
    const nextPrices=result?.prices&&typeof result.prices==="object"?result.prices:{};
    const nextUpdatedAt=String(result?.updated_at||"");
    const oldPrices=JSON.stringify(state.data.prices||{});
    const newPrices=JSON.stringify(nextPrices);
    const changed=nextUpdatedAt!==livePriceUpdatedAt||oldPrices!==newPrices;
    state.data.prices=nextPrices;
    state.data.price_details=result?.price_details&&typeof result.price_details==="object"?result.price_details:{};
    state.data.price_errors=Array.isArray(result?.errors)?result.errors:[];
    state.data.live_source_by_currency=result?.live_source_by_currency&&typeof result.live_source_by_currency==="object"?result.live_source_by_currency:{};
    state.data.live_price_updated_at=nextUpdatedAt||null;
    state.data.live_price_intervals={
      local:Number(result?.local_interval_seconds||300),
      public:Number(result?.public_interval_seconds||60),
      dashboard:Number(result?.dashboard_poll_seconds||15)
    };
    livePriceUpdatedAt=nextUpdatedAt;
    if(changed){
      invalidateDerivedCaches();
      renderBitcoinNetworkStrip();
      renderActiveTabContent(state.activeTab);
      if(state.activeTab==="settings")void refreshConnectionInventory({silent:true,refreshLive:false});
    }
    return true;
  }catch(error){
    if(!silent)toast(errorText(error));
    return false;
  }finally{livePriceRefreshInFlight=false;}
}
function startLivePricePolling(){
  if(livePricePollTimer)clearInterval(livePricePollTimer);
  // This 15-second UI loop is local-only: it reads the coordinator cache from
  // Home Assistant and never triggers an external request itself. Public Tor
  // sources refresh independently (default 60 s), own/local sources default to
  // 300 s. This makes a newly cached quote visible quickly without hammering
  // either the own node or public providers.
  livePricePollTimer=setInterval(()=>{
    if(document.hidden)return;
    void refreshLivePrice({silent:true});
  },15000);
}

function renderMarketAssessmentHistory(){
  const host=$("#marketAssessmentHistoryChart"),hint=$("#marketAssessmentHistoryHint"),bestLegend=$("#marketAssessmentHistoryBestLegend"),markerTooltip=$("#marketAssessmentHistoryMarkerTooltip"),select=$("#marketAssessmentHistoryRange"),overlayToggle=$("#marketAssessmentHistoryPriceOverlay"),priceScaleSelect=$("#marketAssessmentHistoryPriceScale"),opacityInput=$("#marketAssessmentHistoryPriceOpacity"),opacityValue=$("#marketAssessmentHistoryPriceOpacityValue"),opacityControl=$("#marketAssessmentHistoryPriceOpacityControl"),smoothingSelect=$("#marketAssessmentHistorySmoothing");
  if(!host)return;if(select)select.value=state.marketAssessmentHistoryRange||"3y";if(overlayToggle)overlayToggle.checked=Boolean(state.marketAssessmentHistoryPriceOverlay);if(priceScaleSelect){priceScaleSelect.value=state.marketAssessmentHistoryPriceScale||"log";priceScaleSelect.disabled=!state.marketAssessmentHistoryPriceOverlay;}if(opacityInput){opacityInput.value=String(state.marketAssessmentHistoryPriceOpacity);opacityInput.disabled=!state.marketAssessmentHistoryPriceOverlay;}if(opacityValue)opacityValue.textContent=`${Math.round(state.marketAssessmentHistoryPriceOpacity)} %`;if(opacityControl)opacityControl.classList.toggle("is-inactive",!state.marketAssessmentHistoryPriceOverlay);if(smoothingSelect)smoothingSelect.value=String(state.marketAssessmentHistorySmoothing||5);
  const payload=state.marketAssessmentHistory,rawPoints=Array.isArray(payload?.points)?payload.points:[],points=smoothMarketAssessmentPoints(rawPoints);
  if(!points.length){host.innerHTML=`<p class="storage-note">${esc(walletWatchLang("Noch keine rekonstruierte Score-Historie geladen.","No reconstructed score history loaded yet."))}</p>`;if(bestLegend)bestLegend.innerHTML="";if(markerTooltip)markerTooltip.classList.add("hidden");if(hint)hint.textContent="";return;}
  const overlay=Boolean(state.marketAssessmentHistoryPriceOverlay),priceLog=state.marketAssessmentHistoryPriceScale!=="linear",priceOpacity=Math.max(0,Math.min(1,Number(state.marketAssessmentHistoryPriceOpacity||0)/100)),currency=String(payload?.currency||state.data?.summary?.reference_currency||"EUR").toUpperCase();
  const mobile=window.matchMedia("(max-width: 760px)").matches,width=Math.max(mobile?320:760,Math.round(host.clientWidth||(mobile?360:1100))),height=Math.max(mobile?600:560,Math.round(host.clientHeight||(mobile?620:590))),pad={l:58,r:overlay?(mobile?72:88):18,t:32,b:54},pw=width-pad.l-pad.r,ph=height-pad.t-pad.b;
  const times=points.map((point,index)=>marketAssessmentPointTimestamp(point,payload,index,points.length)),minT=Math.min(...times),maxT=Math.max(...times),span=Math.max(1,maxT-minT),x=i=>pad.l+(times[i]-minT)/span*pw,yScore=value=>pad.t+(1-Math.max(0,Math.min(100,Number(value)))/100)*ph;
  const priceTransform=value=>priceLog?Math.log10(Math.max(Number(value),1e-12)):Number(value),priceInverse=value=>priceLog?10**Number(value):Number(value),priceValues=points.map(point=>Number(point.price)).filter(value=>Number.isFinite(value)&&value>0).map(priceTransform);let priceMin=priceValues.length?Math.min(...priceValues):0,priceMax=priceValues.length?Math.max(...priceValues):1;if(priceMin===priceMax){const d=Math.max(Math.abs(priceMin)*.05,.05);priceMin-=d;priceMax+=d;}const pp=(priceMax-priceMin)*.06;priceMin-=pp;priceMax+=pp;if(!priceLog)priceMin=Math.max(0,priceMin);
  const yPrice=value=>pad.t+(1-(priceTransform(value)-priceMin)/Math.max(1e-12,priceMax-priceMin))*ph,scorePoly=points.map((p,i)=>`${x(i).toFixed(2)},${yScore(p.display_score).toFixed(2)}`).join(" "),priceRows=overlay?points.map((p,i)=>({i,value:Number(p.price)})).filter(row=>Number.isFinite(row.value)&&row.value>0):[],pricePoly=priceRows.map(row=>`${x(row.i).toFixed(2)},${yPrice(row.value).toFixed(2)}`).join(" ");
  const grid=[0,25,50,75,100].map(v=>{const yy=yScore(v);return `<line class="grid" x1="${pad.l}" y1="${yy}" x2="${width-pad.r}" y2="${yy}"/><text class="axis-text" x="8" y="${yy+4}">${v}</text>`;}).join(""),priceAxis=overlay?[0,.25,.5,.75,1].map(f=>{const yy=pad.t+f*ph,value=priceInverse(priceMax-f*(priceMax-priceMin));return `<text class="axis-text market-price-axis" x="${width-4}" y="${yy+4}" text-anchor="end">${esc(compactAxis(value))}</text>`;}).join(""):"";
  const nearestIndexForTime=target=>{let lo=0,hi=times.length-1;while(lo<hi){const mid=Math.floor((lo+hi)/2);if(times[mid]<target)lo=mid+1;else hi=mid;}if(lo>0&&Math.abs(times[lo-1]-target)<Math.abs(times[lo]-target))return lo-1;return lo;},tickFractions=mobile?[0,.5,1]:[0,.25,.5,.75,1],tickIdx=[...new Set(tickFractions.map(f=>nearestIndexForTime(minT+f*span)))],labels=tickIdx.map(i=>`<text class="date-text" x="${x(i)}" y="${height-12}" text-anchor="middle">${esc(fmtDate(points[i].date))}</text>`).join("");
  const fallbackBest=rawPoints.reduce((best,point)=>{const score=Number(point?.score);return Number.isFinite(score)&&(!best||score>Number(best.score))?point:best;},null),fallbackMarkers=fallbackBest?[fallbackBest]:[],markers=(Array.isArray(payload?.marker_points)&&payload.marker_points.length?payload.marker_points:fallbackMarkers).filter(marker=>Number.isFinite(Number(marker?.score)));
  const markerRows=markers.map((marker,markerIndex)=>{let index=points.findIndex(point=>String(point?.date||"").slice(0,10)===String(marker?.date||"").slice(0,10));if(index<0)index=nearestIndexForTime(chartTimestamp(marker?.date));const displayScore=Number(points[index]?.display_score),rawScore=Number(marker.score),starY=yScore(Number.isFinite(displayScore)?displayScore:rawScore),starX=x(index),bottomConfirmed=Boolean(marker?.bottom_confirmation_met);return {marker,markerIndex,index,rawScore,starX,starY,bottomConfirmed};}),bestMarkers=markerRows.map(({markerIndex,starX,starY,bottomConfirmed})=>`<g class="market-best-marker-hit${bottomConfirmed?" is-bottom":""}" data-marker-index="${markerIndex}" tabindex="0" role="button" aria-label="${esc(walletWatchLang("Bestwert anzeigen","Show best value"))}"><circle cx="${starX}" cy="${Math.max(pad.t+14,starY-9)}" r="14"/><text class="market-best-star${bottomConfirmed?" is-bottom":""}" x="${starX}" y="${Math.max(pad.t+14,starY-9)}" text-anchor="middle" aria-hidden="true">★</text></g>`).join("");
  host.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(walletWatchLang("Historischer Markteinschätzungs-Score mit Bitcoin-Preis","Historical market assessment score with Bitcoin price"))}">${grid}${priceAxis}<polyline class="series-primary market-score-series" fill="none" points="${scorePoly}"/>${overlay&&pricePoly?`<polyline class="series-secondary market-price-series" stroke-opacity="${priceOpacity.toFixed(2)}" fill="none" points="${pricePoly}"/>`:""}${labels}<text class="axis-text market-score-axis-title" x="${pad.l}" y="18">${esc(walletWatchLang(`Markteinschätzung · 0–100 · ${marketAssessmentSmoothingLabel()}`,`Market assessment · 0–100 · ${marketAssessmentSmoothingLabel()}`))}</text>${overlay?`<text class="axis-text market-price-axis-title" x="${width-pad.r}" y="18" text-anchor="end">${esc(walletWatchLang(`Bitcoin-Preis · ${currency} · ${priceLog?"logarithmisch":"linear"}`,`Bitcoin price · ${currency} · ${priceLog?"logarithmic":"linear"}`))}</text>`:""}<line id="marketHistoryCrossX" class="crosshair hidden" x1="0" y1="${pad.t}" x2="0" y2="${height-pad.b}"/><line id="marketHistoryCrossY" class="crosshair hidden" x1="${pad.l}" y1="0" x2="${width-pad.r}" y2="0"/><circle id="marketHistoryCrossDot" class="cross-dot hidden" r="5" stroke="#f7931a"/><circle id="marketHistoryPriceDot" class="cross-dot hidden" r="4.5" stroke="#66d19e"/><g id="marketHistoryDateBadge" class="crosshair-axis-badge hidden"><rect rx="6" ry="6" width="104" height="24"/><text x="52" y="16" text-anchor="middle">–</text></g><g id="marketHistoryScoreBadge" class="crosshair-axis-badge hidden"><rect rx="6" ry="6" width="50" height="24"/><text x="25" y="16" text-anchor="middle">–</text></g><g id="marketHistoryPriceBadge" class="crosshair-axis-badge market-price-badge hidden"><rect rx="6" ry="6" width="84" height="24"/><text x="42" y="16" text-anchor="middle">–</text></g><rect id="marketHistoryHit" class="chart-hit" x="${pad.l}" y="${pad.t}" width="${pw}" height="${ph}"/>${bestMarkers}</svg>`;
  const hit=$("#marketHistoryHit",host),crossX=$("#marketHistoryCrossX",host),crossY=$("#marketHistoryCrossY",host),dot=$("#marketHistoryCrossDot",host),priceDot=$("#marketHistoryPriceDot",host),dateBadge=$("#marketHistoryDateBadge",host),scoreBadge=$("#marketHistoryScoreBadge",host),priceBadge=$("#marketHistoryPriceBadge",host),panel=host.closest(".panel");
  const hideCross=()=>[crossX,crossY,dot,priceDot,dateBadge,scoreBadge,priceBadge].forEach(node=>node?.classList.add("hidden")),hideMarkerPopup=()=>markerTooltip?.classList.add("hidden");
  const showAtPointer=event=>{hideMarkerPopup();const rect=hit.getBoundingClientRect();if(!(rect.width>0))return;const fraction=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),index=nearestIndexForTime(minT+fraction*span),point=points[index],score=Number(point?.display_score),price=Number(point?.price);if(!Number.isFinite(score)){hideCross();return;}const xPos=x(index),yPos=yScore(score),dateText=fmtDate(point.date),scoreText=fmtNumber(score,1);crossX.setAttribute("x1",xPos);crossX.setAttribute("x2",xPos);crossX.classList.remove("hidden");crossY.setAttribute("y1",yPos);crossY.setAttribute("y2",yPos);crossY.classList.remove("hidden");dot.setAttribute("cx",xPos);dot.setAttribute("cy",yPos);dot.classList.remove("hidden");const dateWidth=104,dateX=Math.max(pad.l,Math.min(width-pad.r-dateWidth,xPos-dateWidth/2));dateBadge.setAttribute("transform",`translate(${dateX},${height-pad.b+8})`);$("text",dateBadge).textContent=dateText;dateBadge.classList.remove("hidden");const scoreY=Math.max(pad.t,Math.min(height-pad.b-24,yPos-12));scoreBadge.setAttribute("transform",`translate(4,${scoreY})`);$("text",scoreBadge).textContent=scoreText;scoreBadge.classList.remove("hidden");if(overlay&&Number.isFinite(price)&&price>0){const py=yPrice(price);priceDot.setAttribute("cx",xPos);priceDot.setAttribute("cy",py);priceDot.classList.remove("hidden");const badgeWidth=84,priceY=Math.max(pad.t,Math.min(height-pad.b-24,py-12));priceBadge.setAttribute("transform",`translate(${width-badgeWidth-3},${priceY})`);$("text",priceBadge).textContent=fmtFiat(price,currency);priceBadge.classList.remove("hidden");}else{priceDot.classList.add("hidden");priceBadge.classList.add("hidden");}};
  hit.addEventListener("pointerleave",hideCross);hit.addEventListener("pointermove",showAtPointer);hit.addEventListener("pointerdown",showAtPointer);
  for(const node of $$(".market-best-marker-hit",host)){const row=markerRows[Number(node.dataset.markerIndex)];if(!row)continue;const show=event=>{event.preventDefault();event.stopPropagation();hideCross();if(!markerTooltip)return;markerTooltip.innerHTML=marketBestMarkerPopupHtml(row.marker);markerTooltip.classList.remove("hidden");const rect=node.getBoundingClientRect();positionChartPopup(markerTooltip,panel,rect.left+rect.width/2,rect.top+rect.height/2);};node.addEventListener("pointerenter",event=>{if(event.pointerType!=="touch")show(event);});node.addEventListener("pointerleave",event=>{if(event.pointerType!=="touch")hideMarkerPopup();});node.addEventListener("pointerdown",show);node.addEventListener("focus",show);node.addEventListener("blur",hideMarkerPopup);}
  if(bestLegend){if(markerRows.length){const intervalYears=Number(payload?.marker_interval_years||0),title=intervalYears>0?walletWatchLang(`Bestwerte je ${intervalYears} Jahre`,`Best values per ${intervalYears} years`):walletWatchLang("Bestwert im Zeitraum","Best value in range");bestLegend.innerHTML=`<strong class="market-best-legend-title">${esc(title)}</strong><div class="market-best-legend-items">${markerRows.map(({marker,rawScore,bottomConfirmed})=>`<span class="market-best-legend-item${bottomConfirmed?" is-bottom":""}"><b>★</b><span>${esc(fmtDate(marker.date))}</span><strong>${esc(fmtNumber(rawScore,1))}</strong>${bottomConfirmed?`<small>${esc(walletWatchLang("Boden bestätigt","Bottom confirmed"))}${marker?.bottom_confirmation_date?` · ${esc(fmtDate(marker.bottom_confirmation_date))}`:""}</small>`:""}</span>`).join("")}</div>`;}else bestLegend.innerHTML="";}
  if(hint)hint.textContent=walletWatchLang(`${points.length} dargestellte Punkte${payload.sampled?` aus ${payload.source_points} verfügbaren Tagen`:""} · ${marketAssessmentSmoothingLabel()} · nur Anzeige, Rohscore unverändert · Modell ${payload.score_version||""}${overlay?` · BTC-Preis ${currency} auf rechter ${priceLog?"Log-":""}Skala`:""}`,`${points.length} displayed points${payload.sampled?` from ${payload.source_points} available days`:""} · ${marketAssessmentSmoothingLabel()} · display only, raw score unchanged · model ${payload.score_version||""}${overlay?` · BTC price ${currency} on right ${priceLog?"log ":""}axis`:""}`);
}

async function loadMarketAssessmentHistory({force=false}={}){
  if(!state.entryId||!state.data)return false;const range=state.marketAssessmentHistoryRange||"3y";
  if(!force&&state.marketAssessmentHistory?.range===range)return true;
  const host=$("#marketAssessmentHistoryChart");if(host)host.innerHTML=`<p class="storage-note">${esc(walletWatchLang("Historischer Score wird rekonstruiert …","Reconstructing historical score …"))}</p>`;
  try{const payload=await api(`api/market-assessment/history?entry_id=${encodeURIComponent(state.entryId)}&range=${encodeURIComponent(range)}`,{timeoutMs:180000});if(payload){state.marketAssessmentHistory=payload;renderMarketAssessmentHistory();return true;}}catch(error){if(host)host.innerHTML=`<p class="storage-note">${esc(errorText(error))}</p>`;}return false;
}

async function refreshMarketAssessment({silent=true}={}){
  if(marketAssessmentRefreshInFlight||!state.entryId||!state.data)return false;
  const requestedEntry=state.entryId;
  marketAssessmentRefreshInFlight=true;
  try{
    const result=await api(`api/market-assessment?entry_id=${encodeURIComponent(requestedEntry)}`,{timeoutMs:15000});
    if(requestedEntry!==state.entryId||!state.data)return false;
    if(result?.buy_opportunity)state.data.buy_opportunity=result.buy_opportunity;
    if(result?.buy_opportunity_settings)state.data.buy_opportunity_settings=result.buy_opportunity_settings;
    // The endpoint only recalculates from already cached history + the latest
    // coordinator price. It never triggers an additional external market call.
    renderBuyOpportunity();
    if(state.activeTab==="market")renderBuyOpportunitySettings();
    return true;
  }catch(error){
    if(!silent)toast(errorText(error));
    return false;
  }finally{marketAssessmentRefreshInFlight=false;}
}
function startMarketAssessmentPolling(){
  if(marketAssessmentPollTimer)clearInterval(marketAssessmentPollTimer);
  // The live-price coordinator refreshes independently (default 5 min).
  // Recalculate the visible public assessment from the latest cached price
  // once a minute so no manual button is required and no extra network traffic
  // is created by this UI timer.
  marketAssessmentPollTimer=setInterval(()=>{
    if(document.hidden)return;
    void refreshMarketAssessment({silent:true});
  },60000);
}

function startNetworkPolling(){
  if(networkPollTimer)clearInterval(networkPollTimer);
  let ticks=0;
  // loadData() already schedules one live Tor refresh. Do not immediately send
  // the same request again when boot finishes.
  networkPollTimer=setInterval(()=>{
    if(document.hidden)return;
    ticks += 1;
    refreshNetworkStatus({silent:true});
    // The connection inventory and rotation settings are only visible on the
    // Settings tab and are substantially more expensive than the compact Tor
    // status. Never poll those hidden views in the background.
    if(state.activeTab==="settings"){
      if(ticks % 2 === 0) refreshConnectionInventory({silent:true});
      if(ticks % 2 === 0) loadTorRotationSettings();
    }
  },30000);
}


function renderSecurity() {
  const security=state.data.security||{},owner=Boolean(security.owner),passwordMode=security.encryption_mode==="password";
  $("#sensitiveSensors").checked=Boolean(security.expose_sensitive_sensors);
  const crypto=state.data?.vault_crypto||{},kdf=crypto.kdf||{};
  const cryptoLabel=passwordMode?(crypto.cipher?`${crypto.cipher} · ${crypto.key_bits||256}-bit key · ${crypto.tag_bits||128}-bit tag · AAD`:`AES-256-GCM · 256-bit key · 128-bit tag · AAD`):"OFF";
  const nonceLabel=passwordMode?`${crypto.nonce_bits||96} bit · ${t("cryptoNonceNote")}`:"–";
  const kdfLabel=!passwordMode?"–":kdf.name==="argon2id"?`Argon2id v${kdf.version||19} · m=${Number(kdf.memory_kib||0).toLocaleString()} KiB · t=${kdf.time_cost||0} · p=${kdf.parallelism||0}`:kdf.n?`scrypt (legacy) · N=${Number(kdf.n).toLocaleString()} · r=${kdf.r} · p=${kdf.p}`:String(kdf.name||"–");
  const memoryLabel=passwordMode&&kdf.estimated_memory_mib?`${kdf.estimated_memory_mib} MiB · Salt ${kdf.salt_bits||"–"} bit · ${kdf.current_profile?t("cryptoProfileCurrent"):t("cryptoProfileOld")}`:"–";
  const envelopeLabel=passwordMode&&crypto.envelope_encryption?`Envelope v3 · DEK ${crypto.data_key_bits||256} bit · ${crypto.key_derivation_separation||"HKDF-SHA-512"}`:"–";
  const wrapLabel=passwordMode&&crypto.envelope_encryption?`${crypto.key_wrap||"AES-256-GCM"} · ${crypto.device_bound?t("cryptoDeviceBound"):t("cryptoPortableNote")}`:"–";
  $("#encryptionStatus").innerHTML=[[t("encryptionMode"),security.encryption_mode||"none"],[t("passwordProtected"),cryptoLabel],[t("cryptoNonceNote"),nonceLabel],[t("cryptoKdf"),kdfLabel],[t("cryptoMemory"),memoryLabel],[t("cryptoEnvelope"),envelopeLabel],[t("cryptoKeyWrap"),wrapLabel],[t("unlocked"),security.user_unlocked?"YES":"NO"],[t("privateMode"),security.expose_sensitive_sensors?"OFF":"ON"]].map(([label,value])=>`<div class="tax-stat"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  $("#securityOwnerNote").textContent=owner?t("ownerOnly"):t("notOwner");
  $("#saveAccessButton").classList.toggle("hidden",!owner);$("#saveSensorMode").classList.toggle("hidden",!owner||passwordMode);$("#sensitiveSensors").disabled=!owner||passwordMode;$("#enableEncryptionForm").classList.toggle("hidden",!owner||passwordMode);$("#changePasswordForm").classList.toggle("hidden",!owner||!passwordMode);$("#disableEncryptionButton").classList.toggle("hidden",!owner||!passwordMode);
  if(passwordMode)$("#sensitiveSensors").checked=false;
  if(owner){$("#securityReadOnly").classList.add("hidden");$("#userAccessList").innerHTML=state.securityUsers.map(user=>`<label class="user-access"><input type="checkbox" value="${esc(user.id)}" ${user.allowed?"checked":""} ${user.is_owner?"disabled":""}><span><strong>${esc(user.name)}</strong><small>${user.is_owner?"Owner · ":""}${user.is_admin?"Admin":"User"} · <code>${esc(user.id)}</code></small></span></label>`).join("");}else{$("#userAccessList").innerHTML="";$("#securityReadOnly").textContent=t("notOwner");$("#securityReadOnly").classList.remove("hidden");}
  renderAutoLock();
}
async function loadLogs(){
  const output=$("#appLogOutput");
  output.textContent=t("logLoading");
  try{
    const result=await api(`api/logs?entry_id=${encodeURIComponent(state.entryId)}&limit=500`),rows=result.entries||[];
    output.textContent=rows.length?rows.map(row=>`${row.time||""} ${String(row.level||"").padEnd(7)} ${row.message||""}`).join("\n"):t("logEmpty");
    // Keep chronological order, but open/refresh at the newest entry.
    requestAnimationFrame(()=>{output.scrollTop=output.scrollHeight;});
  }catch(error){
    output.textContent=error.message||String(error);
    requestAnimationFrame(()=>{output.scrollTop=output.scrollHeight;});
  }
}

function updateCsvFileName() {
  const input = $("#csvFileInput"), label = $("#csvFileName");
  if (!label) return;
  label.textContent = input?.files?.[0]?.name || t("noFileSelected");
}
function csvLocalDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function csvIsoDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}
function csvFixed(value, digits) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "";
}
function displayedAmountToBtc(value, unit) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return NaN;
  return String(unit || "BTC").toLowerCase() === "sats" ? number / SATS_PER_BTC : number;
}
function btcToDisplayedAmount(value, unit) {
  const btc = Number(value);
  if (!Number.isFinite(btc)) return "";
  return String(unit || "BTC").toLowerCase() === "sats" ? Math.round(btc * SATS_PER_BTC) : btc;
}
function compactInputNumber(value, digits=8) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  const fixed = number.toFixed(digits);
  // Decimal BTC may safely lose insignificant fractional trailing zeros.
  // Integer sats may not: "20000" must never become "2".
  return digits <= 0 ? fixed : fixed.replace(/\.?0+$/, "");
}
function transactionFeeDisplay(entry) {
  if(entry?.type==="network_fee"){const amount=Math.max(0,Number(entry?.amount_btc||0)),price=Number(entry?.price),currency=String(entry?.currency||""),network=entry?.network==="lightning"?t("lightning"):t("onchain");return `${fmtStack(amount)}${price>0?` · ${fmtFiat(amount*price,currency)}`:""} · ${network}`;}
  const fiat=Math.max(0,Number(entry?.fee||0));return fiat>0?fmtFiat(fiat,entry?.currency):"–";
}
function transactionFiatTotal(type, amountBtc, price, fee=0) {
  const amount = Number(amountBtc), rate = Number(price), charge = Math.max(0, Number(fee) || 0);
  if (!(amount > 0) || !(rate > 0)) return NaN;
  const gross = amount * rate;
  if (type === "purchase" || type === "income") return gross + charge;
  if (type === "sale" || type === "expense") return gross - charge;
  return gross;
}
function transactionPriceFromTotal(type, amountBtc, fiatTotal, fee=0) {
  const amount = Number(amountBtc), total = Number(fiatTotal), charge = Math.max(0, Number(fee) || 0);
  if (!(amount > 0) || !(total > 0)) return NaN;
  const gross = (type === "purchase" || type === "income") ? total - charge : (type === "sale" || type === "expense") ? total + charge : total;
  return gross > 0 ? gross / amount : NaN;
}
function transactionAmountFromTotal(type, price, fiatTotal, fee=0) {
  const rate = Number(price), total = Number(fiatTotal), charge = Math.max(0, Number(fee) || 0);
  if (!(rate > 0) || !(total > 0)) return NaN;
  const gross = (type === "purchase" || type === "income") ? total - charge : (type === "sale" || type === "expense") ? total + charge : total;
  return gross > 0 ? gross / rate : NaN;
}
function transactionControlCheck(type, amountBtc, price, fiatTotal, fee=0) {
  const expected = transactionFiatTotal(type, amountBtc, price, fee), actual = Number(fiatTotal);
  if (!(expected > 0) || !(actual > 0)) return {complete:false, valid:false, expected, actual, difference:NaN, tolerance:NaN};
  const difference = actual - expected;
  const tolerance = Math.max(0.02, Math.abs(expected) * 0.0001);
  return {complete:true, valid:Math.abs(difference) <= tolerance, expected, actual, difference, tolerance};
}
function updateTransactionFiatLabel() {
  const form = $("#transactionForm"), label = $("#transactionFiatTotalLabel");
  if (!form || !label) return;
  const currency = form.querySelector('[name="currency"]')?.value || state.chartCurrency || "Fiat";
  label.textContent = `${currency} · ${t("fiatTotal")}`;
}
function syncTransactionCalculator(changedField="") {
  const form = $("#transactionForm"), status = $("#transactionCalcStatus");
  if (!form || !status) return;
  const type = form.querySelector('[name="type"]')?.value || "purchase";
  if (type === "stack") { status.textContent = ""; return; }
  const amountInput=form.querySelector('[name="amount"]'),unitInput=form.querySelector('[name="amount_unit"]'),priceInput=form.querySelector('[name="price"]'),totalInput=form.querySelector('[name="fiat_total"]'),feeInput=form.querySelector('[name="fee"]');
  const changed = form.querySelector(`[name="${changedField}"]`);
  if (changed && changed.dataset) delete changed.dataset.autoCalculated;
  const fee = Math.max(0, Number(feeInput?.value) || 0);
  let amountBtc = displayedAmountToBtc(amountInput?.value, unitInput?.value), price = Number(priceInput?.value), total = Number(totalInput?.value);
  const amountAuto = amountInput?.dataset.autoCalculated === "1", priceAuto = priceInput?.dataset.autoCalculated === "1", totalAuto = totalInput?.dataset.autoCalculated === "1";
  if ((!(amountBtc > 0) || amountAuto) && price > 0 && total > 0) {
    const calculated = transactionAmountFromTotal(type, price, total, fee);
    if (calculated > 0) { amountInput.value = compactInputNumber(btcToDisplayedAmount(calculated, unitInput.value), unitInput.value === "sats" ? 0 : 8); amountInput.dataset.autoCalculated="1"; amountBtc=calculated; }
  } else if ((!(price > 0) || priceAuto) && amountBtc > 0 && total > 0) {
    const calculated = transactionPriceFromTotal(type, amountBtc, total, fee);
    if (calculated > 0) { priceInput.value=compactInputNumber(calculated, 8); priceInput.dataset.autoCalculated="1"; price=calculated; }
  } else if ((!(total > 0) || totalAuto) && amountBtc > 0 && price > 0) {
    const calculated = transactionFiatTotal(type, amountBtc, price, fee);
    if (calculated > 0) { totalInput.value=calculated.toFixed(2); totalInput.dataset.autoCalculated="1"; total=calculated; }
  }
  const check = transactionControlCheck(type, amountBtc, price, total, fee);
  if (!check.complete) { status.textContent=t("fiatControlMissing"); status.className="storage-note wide transaction-calc-status"; return; }
  const currency=form.querySelector('[name="currency"]')?.value || "";
  if (check.valid) {
    status.textContent=`✓ ${t("fiatControlOk")}: ${fmtFiat(check.actual,currency)}`;
    status.className="storage-note wide transaction-calc-status calc-ok";
  } else {
    status.textContent=`⚠ ${t("fiatControlDifference")}: ${check.difference >= 0 ? "+" : ""}${fmtFiat(check.difference,currency)} · ${t("fiatTotal")}: ${fmtFiat(check.actual,currency)} · ${t("calculated") || "Berechnet"}: ${fmtFiat(check.expected,currency)}`;
    status.className="storage-note wide transaction-calc-status calc-warning";
  }
}
function initializeCsvControlTotal(row) {
  if (!row) return row;
  const supplied = Number(row.fiat_amount ?? row.fiat_total);
  if (supplied > 0) row.fiat_total = supplied;
  else {
    const calculated=transactionFiatTotal(String(row.type||"purchase"),Number(row.amount_btc),Number(row.price),Number(row.fee||0));
    row.fiat_total=calculated>0?Number(calculated.toFixed(8)):0;
  }
  if (!row.amount_unit) row.amount_unit = state.unit === "sats" ? "sats" : "BTC";
  return row;
}
function syncCsvRowCalculator(element, changedField="") {
  if (!element) return;
  const field=name=>element.querySelector(`[data-field="${name}"]`);
  const type=field("type")?.value||"purchase", unit=field("amount_unit")?.value||"BTC";
  const amountInput=field("amount_btc"),priceInput=field("price"),totalInput=field("fiat_total"),feeInput=field("fee");
  const changed=field(changedField); if(changed&&changed.dataset)delete changed.dataset.autoCalculated;
  const fee=Math.max(0,Number(feeInput?.value)||0);
  let amountBtc=displayedAmountToBtc(amountInput?.value,unit),price=Number(priceInput?.value),total=Number(totalInput?.value);
  if ((!(amountBtc>0)||amountInput?.dataset.autoCalculated==="1") && price>0 && total>0) { const calc=transactionAmountFromTotal(type,price,total,fee); if(calc>0){amountInput.value=compactInputNumber(btcToDisplayedAmount(calc,unit),unit==="sats"?0:8);amountInput.dataset.autoCalculated="1";amountBtc=calc;} }
  else if ((!(price>0)||priceInput?.dataset.autoCalculated==="1") && amountBtc>0 && total>0) { const calc=transactionPriceFromTotal(type,amountBtc,total,fee); if(calc>0){priceInput.value=compactInputNumber(calc,8);priceInput.dataset.autoCalculated="1";price=calc;} }
  else if ((!(total>0)||totalInput?.dataset.autoCalculated==="1") && amountBtc>0 && price>0) { const calc=transactionFiatTotal(type,amountBtc,price,fee); if(calc>0){totalInput.value=calc.toFixed(2);totalInput.dataset.autoCalculated="1";total=calc;} }
}
function csvValueFingerprint(row) {
  const type = String(row.type || ""), timestamp = csvIsoDateTime(row.timestamp);
  const depot = String(row.depot_id || ""), amount = csvFixed(row.amount_btc, 8);
  const currency = String(row.currency || "").trim().toUpperCase(), price = csvFixed(row.price, 8);
  const fee = csvFixed(row.fee || 0, 8), feeBtc=csvFixed(row.fee_btc || 0,8);
  if (!["purchase","sale","expense"].includes(type) || !timestamp || !depot || !amount || !fee || !feeBtc) return "";
  if (type !== "expense" && (!currency || !price)) return "";
  return [type,timestamp,depot,amount,currency,price,fee,feeBtc].join("|");
}
function csvImportRefHash(row) {
  const value = String(row.import_ref_hash || "").trim().toLowerCase();
  return /^[0-9a-f]{64}$/.test(value) ? value : "";
}
function markCsvDuplicates(rows) {
  // Existing-ledger identity never needs to be copied into the browser. Core
  // supplies one boolean per preview row; this local pass only catches another
  // duplicate inside the currently open CSV review.
  const pendingRefs=new Set(),pendingValues=new Set();
  rows.forEach(row=>{
    const refHash=csvImportRefHash(row),values=csvValueFingerprint(row);
    let duplicate=Boolean(row.server_duplicate);
    if(refHash){
      if(pendingRefs.has(refHash))duplicate=true;
      pendingRefs.add(refHash);
    }else if(values){
      if(pendingValues.has(values))duplicate=true;
      pendingValues.add(values);
    }
    row.duplicate=duplicate;
    if(duplicate)row.selected=false;
  });
}
function csvDuplicatePayloadRow(row){
  return {
    type:row.type,timestamp:row.timestamp,amount_btc:row.amount_btc,
    currency:row.currency,price:row.price,fee:row.fee||0,included_fee:row.included_fee||0,
    included_fee_estimated:Boolean(row.included_fee_estimated),fee_btc:row.fee_btc||0,
    depot_id:row.depot_id,import_ref_hash:row.import_ref_hash||""
  };
}
async function refreshCsvDuplicatesFromCore(){
  const preview=state.csvImport;if(!preview||preview.busy)return;
  const revision=++csvDuplicateCheckRevision;
  const rows=preview.rows.filter(row=>!row.removed);
  try{
    const result=await api("api/import/duplicates",{method:"POST",body:JSON.stringify({entry_id:state.entryId,rows:rows.map(csvDuplicatePayloadRow)}),timeoutMs:60000});
    if(!state.csvImport||preview!==state.csvImport||revision!==csvDuplicateCheckRevision)return;
    const flags=Array.isArray(result?.duplicates)?result.duplicates:[];
    rows.forEach((row,index)=>{row.server_duplicate=Boolean(flags[index]);});
    refreshCsvReviewVisuals();
  }catch(error){
    console.warn("CSV duplicate check failed",errorText(error));
  }
}
function scheduleCsvDuplicateCheck(){
  if(csvDuplicateCheckTimer)clearTimeout(csvDuplicateCheckTimer);
  csvDuplicateCheckTimer=setTimeout(()=>{csvDuplicateCheckTimer=null;void refreshCsvDuplicatesFromCore();},250);
}
function validateCsvRow(row) {
  const warnings = [];
  if (!['purchase','income','sale','expense'].includes(String(row.type || ''))) warnings.push(t("csvInvalid"));
  if (!(Number(row.amount_btc) > 0)) warnings.push(t("csvAmountRequired"));
  if (row.type !== "expense" && !String(row.currency || "").trim()) warnings.push(t("csvCurrencyRequired"));
  if (row.type !== "expense" && !(Number(row.price) > 0)) warnings.push(t("csvPriceRequired"));
  if (row.type === "expense" && (Boolean(String(row.currency || "").trim()) !== (Number(row.price) > 0))) warnings.push(t("csvPriceRequired"));
  if (!(Number(row.fee || 0) >= 0)) warnings.push(t("csvFeeInvalid"));
  if (!(Number(row.included_fee || 0) >= 0)) warnings.push(t("csvFeeInvalid"));
  const pricedExpense=row.type === "expense" && Boolean(String(row.currency||"").trim()) && Number(row.price)>0;
  if (row.type !== "expense" || pricedExpense) {
    if (!(Number(row.fiat_total) > 0)) warnings.push(t("fiatAmountRequired"));
    else {
      const controlAmount=Number(row.import_hints?.control_amount_btc || row.amount_btc);
      const controlFee=Number(row.fee||0)+(row.import_hints?.control_included_fee===true||row.import_hints?.control_included_fee==="True"?Number(row.included_fee||0):0);
      const control=transactionControlCheck(row.type,controlAmount,Number(row.price),Number(row.fiat_total),controlFee);
      if (control.complete && !control.valid) warnings.push(`${t("fiatControlDifference")}: ${control.difference >= 0 ? "+" : ""}${control.difference.toFixed(2)} ${String(row.currency||"")}`);
    }
  }
  if (!csvIsoDateTime(row.timestamp)) warnings.push(t("csvDateRequired"));
  if (!state.data?.depots?.some(item => item.id === row.depot_id)) warnings.push(t("depot"));
  row.client_warnings = warnings;
  row.valid = warnings.length === 0 && (!row.parser_requires_review || row.edited);
  return row.valid;
}
const CSV_OPTIONAL_FIELD_ORDER = ["order_id", "transaction_id", "address", "ln_invoice", "memo", "transaction_type", "exchange", "trade_group"];
function csvOptionalFieldLabel(key) {
  const labels = {
    order_id:"optionalFieldOrderId", transaction_id:"optionalFieldTransactionId",
    address:"optionalFieldAddress", ln_invoice:"optionalFieldLnInvoice",
    memo:"optionalFieldMemo", transaction_type:"optionalFieldTransactionType",
    exchange:"optionalFieldExchange", trade_group:"optionalFieldTradeGroup"
  };
  return t(labels[key] || key);
}
function csvOptionalFieldKeys(preview=state.csvImport) {
  const available = new Set();
  (preview?.rows || []).forEach(row => Object.entries(row.optional_note_fields || {}).forEach(([key,value]) => {
    if (String(value || "").trim()) available.add(key);
  }));
  return [...available].sort((a,b) => {
    const ai = CSV_OPTIONAL_FIELD_ORDER.indexOf(a), bi = CSV_OPTIONAL_FIELD_ORDER.indexOf(b);
    return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi) || a.localeCompare(b);
  });
}
function csvOptionalSelection(preview=state.csvImport) {
  return new Set(preview?.optional_note_selection || []);
}
function csvOptionalNoteParts(row, preview=state.csvImport) {
  const selected = csvOptionalSelection(preview);
  return CSV_OPTIONAL_FIELD_ORDER
    .filter(key => selected.has(key))
    .map(key => {
      const value = String(row?.optional_note_fields?.[key] || "").trim();
      return value ? `${csvOptionalFieldLabel(key)}: ${value}` : "";
    })
    .filter(Boolean);
}
function csvComposedNote(row, preview=state.csvImport) {
  return [String(row?.note || "").trim(), ...csvOptionalNoteParts(row, preview)]
    .filter(Boolean).join(" · ").slice(0, 2000);
}
function renderCsvOptionalFields() {
  const preview = state.csvImport, box = $("#csvOptionalFields"), choices = $("#csvOptionalFieldChoices");
  if (!box || !choices) return;
  const keys = csvOptionalFieldKeys(preview);
  if (!preview || !keys.length) {
    box.classList.add("hidden"); choices.innerHTML = ""; return;
  }
  box.classList.remove("hidden");
  const selected = csvOptionalSelection(preview);
  choices.innerHTML = keys.map(key => `<label class="import-optional-choice"><input type="checkbox" data-optional-note-field="${esc(key)}" ${selected.has(key) ? "checked" : ""}><span>${esc(csvOptionalFieldLabel(key))}</span></label>`).join("");
  choices.querySelectorAll("[data-optional-note-field]").forEach(input => input.addEventListener("change", event => {
    csvRowsFromModal();
    const next = csvOptionalSelection(preview), key = event.currentTarget.dataset.optionalNoteField;
    if (event.currentTarget.checked) next.add(key); else next.delete(key);
    preview.optional_note_selection = [...next];
    renderCsvImportPreview();
  }));
}
function csvRowsFromModal({selectedOnly=false}={}) {
  const rows = [];
  $$("#csvImportBody tr[data-import-index]").forEach(element => {
    const index = Number(element.dataset.importIndex), source = state.csvImport?.rows?.[index];
    if (!source || source.removed) return;
    const value = name => element.querySelector(`[data-field="${name}"]`)?.value ?? "";
    const row = {
      ...source,
      selected: Boolean(element.querySelector('[data-field="selected"]')?.checked),
      type: value("type"),
      timestamp: csvIsoDateTime(value("timestamp")),
      amount_unit: value("amount_unit") || "BTC",
      amount_btc: displayedAmountToBtc(value("amount_btc"), value("amount_unit") || "BTC"),
      currency: value("currency").trim().toUpperCase(),
      price: Number(value("price")),
      fiat_total: Number(value("fiat_total")),
      fee: Number(value("fee") || 0),
      included_fee: Number(value("included_fee") || 0),
      depot_id: value("depot_id"),
      note: value("note").trim().slice(0, 2000)
    };
    validateCsvRow(row);
    Object.assign(source, row);
    if (!selectedOnly || row.selected) rows.push(row);
  });
  return rows;
}
function updateCsvSelectedCount() {
  const selected = $$('#csvImportBody [data-field="selected"]:checked').length;
  const target = $("#csvSelectedCount");
  if (target) target.textContent = `${selected} ${t("csvSelected")}`;
  const button = $("#csvImportConfirm");
  if (button) {
    const busy = Boolean(state.csvImport?.busy);
    button.disabled = busy;
    button.classList.toggle("import-no-selection", selected === 0 && !busy);
  }
}
function refreshCsvReviewVisuals() {
  if (!state.csvImport) return;
  const activeRows = state.csvImport.rows.filter(row => !row.removed);
  activeRows.forEach(validateCsvRow);
  markCsvDuplicates(activeRows);
  $$("#csvImportBody tr[data-import-index]").forEach(element => {
    const row = state.csvImport.rows[Number(element.dataset.importIndex)];
    if (!row) return;
    element.classList.toggle("import-row-invalid", !row.valid && !row.duplicate);
    element.classList.toggle("import-row-duplicate", Boolean(row.duplicate));
    const checkbox = element.querySelector('[data-field="selected"]');
    if (row.duplicate && checkbox) { checkbox.checked = false; row.selected = false; }
    const messages = row.edited ? (row.client_warnings || []) : [...(row.warnings || []), ...(row.client_warnings || [])];
    const status = row.duplicate ? t("csvDuplicate") : row.valid ? (messages.length ? messages.join(" · ") : t("csvReady")) : (messages.join(" · ") || t("csvInvalid"));
    const target = element.querySelector(".import-status");
    if (target) target.textContent = status;
  });
  updateCsvSelectedCount();
}
function closeCsvImportPreview() {
  if(csvDuplicateCheckTimer){clearTimeout(csvDuplicateCheckTimer);csvDuplicateCheckTimer=null;}
  csvDuplicateCheckRevision += 1;
  state.csvImport = null;
  $("#csvImportModal")?.classList.add("hidden");
  document.body.classList.remove("import-modal-open");
  const body = $("#csvImportBody");
  if (body) body.innerHTML = "";
  const status = $("#csvImportActionStatus");
  if (status) status.textContent = "";
}
function renderCsvImportPreview() {
  const preview = state.csvImport;
  if (!preview) return;
  applyCsvImportHints(preview);
  const activeRows = preview.rows.filter(row => !row.removed);
  activeRows.forEach(validateCsvRow);
  markCsvDuplicates(activeRows);
  const summary = $("#csvImportSummary");
  if (summary) summary.textContent = `${preview.source_label || preview.source} · ${preview.filename} · ${activeRows.length} ${t("csvRecognized")} · ${preview.skipped || 0} ${t("csvSkipped")} · ${activeRows.filter(row => !row.valid).length} ${t("csvNeedsReview")}`;
  const warnings = [...(preview.warnings || [])];
  if (preview.source === "generic") warnings.push(t("csvGenericWarning"));
  warnings.push(t("csvReviewHint"));
  $("#csvImportWarnings").innerHTML = warnings.map(item => `<p class="import-warning">${esc(item)}</p>`).join("");
  renderCsvOptionalFields();
  const depots = state.data?.depots || [];
  const depotOptions = selected => depots.map(item => `<option value="${esc(item.id)}" ${item.id === selected ? "selected" : ""}>${esc(item.name)}</option>`).join("");
  $("#csvImportBody").innerHTML = preview.rows.map((row, index) => {
    if (row.removed) return "";
    initializeCsvControlTotal(row);
    const originalWarnings = row.edited ? (row.client_warnings || []) : [...(row.warnings || []), ...(row.client_warnings || [])];
    const statusText = row.duplicate ? t("csvDuplicate") : row.valid ? (originalWarnings.length ? originalWarnings.join(" · ") : t("csvReady")) : (originalWarnings.join(" · ") || t("csvInvalid"));
    const rowClass = row.duplicate ? "import-row-duplicate" : row.valid ? "" : "import-row-invalid";
    const optionalParts = csvOptionalNoteParts(row, preview);
    const optionalNotePreview = optionalParts.length ? `<small class="import-note-extra">+ ${esc(t("optionalFieldsSelected"))}: ${esc(optionalParts.join(" · "))}</small>` : "";
    return `<tr data-import-index="${index}" class="${rowClass}">
      <td><input data-field="selected" type="checkbox" ${row.selected && !row.duplicate ? "checked" : ""}></td>
      <td><strong>${esc(row.source || preview.source_label || "CSV")}</strong><small>${esc(t("row"))} ${esc(row.source_row || index + 2)}</small></td>
      <td><select data-field="type"><option value="purchase" ${row.type === "purchase" ? "selected" : ""}>${esc(t("purchase"))}</option><option value="sale" ${row.type === "sale" ? "selected" : ""}>${esc(t("sale"))}</option><option value="expense" ${row.type === "expense" ? "selected" : ""}>${esc(t("expense"))}</option></select></td>
      <td><input data-field="timestamp" class="import-date" type="datetime-local" value="${esc(csvLocalDateTime(row.timestamp))}"></td>
      <td><div class="import-amount-pair"><input data-field="amount_btc" class="import-amount" type="number" min="0" step="any" value="${esc(compactInputNumber(btcToDisplayedAmount(row.amount_btc,row.amount_unit),row.amount_unit === "sats" ? 0 : 8))}"><select data-field="amount_unit" class="import-amount-unit" data-previous-unit="${esc(row.amount_unit)}"><option value="BTC" ${row.amount_unit !== "sats" ? "selected" : ""}>BTC</option><option value="sats" ${row.amount_unit === "sats" ? "selected" : ""}>sats</option></select></div></td>
      <td><input data-field="currency" class="import-currency" maxlength="16" value="${esc(row.currency || "")}"></td>
      <td><input data-field="price" class="import-price" type="number" min="0" step="any" value="${esc(row.price ?? "")}"></td>
      <td><input data-field="fiat_total" class="import-fiat-total" type="number" min="0" step="0.01" value="${esc(Number(row.fiat_total)>0?Number(row.fiat_total).toFixed(2):"")}"></td>
      <td><input data-field="fee" class="import-fee" type="number" min="0" step="any" value="${esc(row.fee ?? 0)}"></td>
      <td><input data-field="included_fee" class="import-fee" type="number" min="0" step="any" value="${esc(row.included_fee ?? 0)}" title="${esc(row.included_fee_estimated ? t("includedFeeEstimated") : t("includedFee"))}"></td>
      <td><select data-field="depot_id">${depotOptions(row.depot_id)}</select></td>
      <td><input data-field="note" class="import-note" maxlength="2000" value="${esc(row.note || "")}">${optionalNotePreview}</td>
      <td><span class="import-status">${esc(statusText)}</span></td>
      <td><button class="ghost compact import-remove" type="button" aria-label="${esc(t("remove"))}">×</button></td>
    </tr>`;
  }).join("");
  $$("#csvImportBody [data-field]").forEach(input => {
    const handler=event=>{
      const tr=event.currentTarget.closest("tr"), fieldName=event.currentTarget.dataset.field;
      const index=Number(tr?.dataset.importIndex), row=state.csvImport?.rows?.[index];
      if (row && (fieldName !== "selected" || event.currentTarget.checked)) row.edited=true;
      if (row && fieldName === "note") row.note_user_edited=true;
      if (row && fieldName === "included_fee") row.included_fee_estimated=false;
      if (row && fieldName === "amount_unit") {
        const amountInput=tr?.querySelector('[data-field="amount_btc"]'), previous=event.currentTarget.dataset.previousUnit || row.amount_unit || "BTC", next=event.currentTarget.value || "BTC";
        const btc=displayedAmountToBtc(amountInput?.value,previous);
        if(Number.isFinite(btc)&&btc>0&&amountInput)amountInput.value=compactInputNumber(btcToDisplayedAmount(btc,next),next==="sats"?0:8);
        event.currentTarget.dataset.previousUnit=next;
      }
      if (["amount_btc","amount_unit","price","fiat_total","fee","type"].includes(fieldName)) syncCsvRowCalculator(tr,fieldName);
      csvRowsFromModal();
      refreshCsvReviewVisuals();
      if(["type","timestamp","amount_btc","amount_unit","currency","price","fiat_total","fee","included_fee","depot_id"].includes(fieldName))scheduleCsvDuplicateCheck();
    };
    input.addEventListener(input.matches('input[type="number"]') ? "input" : "change", handler);
  });
  $$("#csvImportBody .import-remove").forEach(button => button.addEventListener("click", event => {
    const index = Number(event.currentTarget.closest("tr")?.dataset.importIndex);
    if (state.csvImport?.rows?.[index]) state.csvImport.rows[index].removed = true;
    renderCsvImportPreview();
  }));
  updateCsvSelectedCount();
  queueCsvHorizontalScrollUpdate();
}
function localImportPrice(currency, timestamp) {
  const code=String(currency||"").toUpperCase(), parsed=chartTimestamp(timestamp), day=Number.isFinite(parsed)?new Date(parsed).toISOString().slice(0,10):String(timestamp||"").slice(0,10);
  const series=state.data?.history?.prices?.[code]||{};
  const exact=Number(series[day]);
  if(Number.isFinite(exact)&&exact>0)return exact;
  const target=Date.parse(`${day}T00:00:00Z`);
  if(Number.isFinite(target)){
    const nearest=Object.entries(series).map(([key,value])=>({distance:Math.abs(Date.parse(`${key}T00:00:00Z`)-target),value:Number(value)})).filter(item=>Number.isFinite(item.distance)&&Number.isFinite(item.value)&&item.value>0).sort((a,b)=>a.distance-b.distance)[0];
    if(nearest&&nearest.distance<=7*86400000)return nearest.value;
  }
  const live=Number(state.data?.prices?.[code]);
  return Number.isFinite(live)&&live>0?live:null;
}
function applyCsvImportHints(preview) {
  if(!preview?.rows)return preview;
  preview.rows.forEach(row=>{
    const hints=row.import_hints||{};
    const localized=String(hints[`localized_note_${state.lang}`]||"").trim();
    if(localized&&!row.note_user_edited&&hints.wavespace_kind!=="card_creation")row.note=localized;
  });
  const cardRows=preview.rows.filter(row=>row.import_hints?.wavespace_kind==="card_creation"&&Number(row.amount_btc)>0);
  if(!cardRows.length)return preview;
  const unclassified=cardRows.filter(row=>!(Number(row.import_hints?.card_price_eur)>0));
  const candidates=unclassified.map(row=>{
    const amount=Number(row.amount_btc),localPrice=localImportPrice("EUR",row.timestamp);
    return {row,amount,localPrice,estimated:Number.isFinite(localPrice)?amount*localPrice:null,target:null};
  });
  if(candidates.length===2){
    const ordered=[...candidates].sort((a,b)=>(a.estimated??a.amount)-(b.estimated??b.amount));
    ordered[0].target=2.99;ordered[1].target=29.99;
  }else{
    candidates.forEach(item=>{
      if(Number.isFinite(item.estimated)){
        const virtualDistance=Math.abs(item.estimated-2.99)/2.99,physicalDistance=Math.abs(item.estimated-29.99)/29.99;
        item.target=virtualDistance<=physicalDistance?2.99:29.99;
      }else item.target=item.amount===Math.min(...candidates.map(entry=>entry.amount))?2.99:29.99;
    });
  }
  candidates.forEach(item=>{
    item.row.import_hints.card_price_eur=String(item.target);
    item.row.import_hints.card_price_source=Number.isFinite(item.localPrice)?"local":"amount";
  });
  cardRows.forEach(row=>{
    const target=Number(row.import_hints?.card_price_eur),amount=Number(row.amount_btc);
    if(!(target>0&&amount>0))return;
    row.type="sale";
    row.currency="EUR";
    row.price=String(target/amount);
    row.fee="0";
    row.import_hints.card_price_applied=true;
    const type=target===29.99?t("wavespacePhysicalCard"):t("wavespaceVirtualCard");
    const source=row.import_hints.card_price_source==="local"?t("wavespaceCardPriceLocal"):t("wavespaceCardPriceCompared");
    if(!row.note_user_edited)row.note=`Wavespace · ${type} · ${t("wavespaceCardCreationFee")}: ${fmtNumber(target,2)} EUR · ${source}`;
  });
  return preview;
}
function updateCsvHorizontalScroll() {
  const wrap=$(".import-table-wrap"),control=$("#csvHorizontalScroll");
  if(!wrap||!control)return;
  const maximum=Math.max(0,Math.ceil(wrap.scrollWidth-wrap.clientWidth));
  control.max=String(maximum);
  control.value=String(Math.max(0,Math.min(maximum,Math.round(wrap.scrollLeft))));
  control.disabled=maximum<1;
  const left=$("#csvScrollLeft"),right=$("#csvScrollRight");
  if(left)left.disabled=maximum<1||wrap.scrollLeft<=1;
  if(right)right.disabled=maximum<1||wrap.scrollLeft>=maximum-1;
}
function queueCsvHorizontalScrollUpdate() {
  requestAnimationFrame(()=>requestAnimationFrame(updateCsvHorizontalScroll));
}
function scrollCsvTable(direction) {
  const wrap=$(".import-table-wrap");
  if(!wrap)return;
  const step=Math.max(280,Math.round(wrap.clientWidth*0.72));
  wrap.scrollBy({left:direction*step,behavior:"smooth"});
  window.setTimeout(updateCsvHorizontalScroll,260);
}

async function previewCsvImport(event) {
  event.preventDefault();
  // CSV parsing and duplicate matching stay in Home Assistant Core. Opening an
  // import no longer forces the complete private ledger into browser memory.
  const input = $("#csvFileInput"), file = input?.files?.[0];
  if (!file) throw new Error(t("noFileSelected"));
  const button = $("#csvPreviewButton"), originalText = button.textContent;
  button.disabled = true; button.textContent = t("csvParsing");
  try {
    const upload = new FormData();
    const depotId = $("#csvDefaultDepot")?.value || state.data?.depots?.[0]?.id || "main";
    upload.append("entry_id", state.entryId);
    upload.append("depot_id", depotId);
    upload.append("file", file, file.name);
    const result = await api("api/import/preview", {method:"POST", body:upload, timeoutMs:60000});
    result.rows = (result.rows || []).map(row => initializeCsvControlTotal({...row, optional_note_fields:{...(row.optional_note_fields || {})}, import_hints:{...(row.import_hints || {})}, depot_id:depotId, server_duplicate:Boolean(row.duplicate), selected:Boolean(row.valid)&&!Boolean(row.duplicate), removed:false, parser_requires_review:!row.valid, edited:false, note_user_edited:false}));
    result.optional_note_selection = [];
    applyCsvImportHints(result);
    state.csvImport = result;
    markCsvDuplicates(state.csvImport.rows);
    input.value = "";
    updateCsvFileName();
    const modal = $("#csvImportModal");
    modal.classList.remove("hidden");
    document.body.classList.add("import-modal-open");
    renderCsvImportPreview();
    modal.scrollTop = 0;
    const card = modal.querySelector(".import-modal-card");
    if(card)card.scrollTop=0;
    queueCsvHorizontalScrollUpdate();
  } finally {
    button.disabled = false; button.textContent = originalText || t("checkCsv");
  }
}
async function confirmCsvImport() {
  const preview=state.csvImport,button=$("#csvImportConfirm"),status=$("#csvImportActionStatus");
  if(!preview||preview.busy)return;
  const rows=csvRowsFromModal({selectedOnly:true});
  if(!rows.length){
    const message=t("csvNoSelection");
    if(status)status.textContent=message;
    toast(message);
    return;
  }
  const invalid=rows.find(row=>!row.valid);
  if(invalid){
    const detail=[...(invalid.client_warnings||[]),...(invalid.warnings||[])].filter(Boolean).join(" · ");
    const message=`${t("invalidImportRow")}: ${invalid.source||"CSV"} ${t("row")} ${invalid.source_row||"?"}${detail?` · ${detail}`:""}`;
    if(status)status.textContent=message;
    toast(message);
    return;
  }
  preview.busy=true;
  const originalText=button?.textContent||t("confirmImport");
  if(button){button.disabled=true;button.textContent=t("csvImporting");}
  if(status)status.textContent=t("csvImportStarting");
  try{
    const result=await service("bulk_import",{
      config_entry_id:state.entryId,
      transactions:rows.map(row=>({type:row.type,timestamp:row.timestamp,amount_btc:row.amount_btc,currency:row.currency,price:row.price,fee:row.fee,included_fee:row.included_fee||0,included_fee_estimated:Boolean(row.included_fee_estimated),depot_id:row.depot_id,note:csvComposedNote(row),fee_btc:row.fee_btc||0,import_ref_hash:row.import_ref_hash||""}))
    },{timeoutMs:300000});
    const imported=Number(result.imported||0),duplicates=Number(result.duplicates||0);
    closeCsvImportPreview();
    toast(`${imported} ${t("csvImported")}${duplicates?` · ${duplicates} ${t("csvDuplicates")}`:""}`);
    await loadData();
  }catch(error){
    preview.busy=false;
    const message=`${t("csvImportFailed")} ${error.message||String(error)}`;
    if(status)status.textContent=message;
    toast(message);
    if(button){button.disabled=false;button.textContent=originalText;}
    updateCsvSelectedCount();
  }
}

function transactionLocalTimestamp(value){
  const date=new Date(value); if(Number.isNaN(date.getTime()))return "";
  return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
}
let historicalPriceCheckTimer=null,historicalPriceCheckRevision=0;
function updateTransactionFieldVisibility(){
  const form=$("#transactionForm");if(!form)return;
  const type=String(form.querySelector('[name="type"]')?.value||"purchase");
  $$(".priced",form).forEach(item=>item.style.display=type==="stack"?"none":"block");
  $$(".fiat-fee-field",form).forEach(item=>item.style.display=["purchase","income","sale","expense"].includes(type)?"block":"none");
  $$(".network-fee-field",form).forEach(item=>item.classList.toggle("hidden",type!=="network_fee"));
  if(type==="network_fee"){const fee=form.querySelector('[name="fee"]');if(fee)fee.value=0;}
}
function historicalWarning(message="",warning=false){
  const box=$("#historicalPriceWarning");if(!box)return;
  box.textContent=message;box.classList.toggle("danger-note",Boolean(warning));
}
function scheduleHistoricalPriceCheck(){
  if(historicalPriceCheckTimer)clearTimeout(historicalPriceCheckTimer);
  historicalPriceCheckTimer=setTimeout(()=>void refreshHistoricalPriceCheck(),350);
}
async function refreshHistoricalPriceCheck(){
  const form=$("#transactionForm");if(!form||!state.entryId)return;
  const revision=++historicalPriceCheckRevision,type=String(form.querySelector('[name="type"]')?.value||"purchase");
  if(type==="stack"){historicalWarning();return;}
  const rawTime=form.querySelector('[name="timestamp"]')?.value,currency=String(form.querySelector('[name="currency"]')?.value||"").toUpperCase();
  const priceInput=form.querySelector('[name="price"]'),amountInput=form.querySelector('[name="amount"]'),unitInput=form.querySelector('[name="amount_unit"]');
  if(!rawTime||!currency){historicalWarning();return;}
  const date=new Date(rawTime);if(Number.isNaN(date.getTime())){historicalWarning();return;}
  try{
    const result=await api(`api/history/reference-price?entry_id=${encodeURIComponent(state.entryId)}&currency=${encodeURIComponent(currency)}&timestamp=${encodeURIComponent(date.toISOString())}`,{timeoutMs:30000});
    if(revision!==historicalPriceCheckRevision)return;
    const reference=Number(result?.price),available=Boolean(result?.available)&&Number.isFinite(reference)&&reference>0;
    if(!available){historicalWarning(t("historicalReferenceUnavailable"),false);return;}
    if(type==="network_fee"){
      if(!(Number(priceInput?.value)>0)||priceInput?.dataset.autoHistorical==="1"){
        priceInput.value=String(reference);priceInput.dataset.autoHistorical="1";syncTransactionCalculator("price");
      }
      const amountBtc=displayedAmountToBtc(amountInput?.value,unitInput?.value),fiat=Number.isFinite(amountBtc)&&amountBtc>0?amountBtc*reference:NaN;
      const target=$("#networkFeeFiatEstimate");if(target)target.textContent=`${t("networkFeeAutoPrice")}: ${fmtFiat(reference,currency)} / BTC${Number.isFinite(fiat)?` · ${t("networkFeeValue")}: ${fmtFiat(fiat,currency)}`:""}`;
      historicalWarning();return;
    }
    const entered=Number(priceInput?.value);if(!(entered>0)){historicalWarning();return;}
    const deviation=(entered/reference-1)*100;
    if(Math.abs(deviation)>=10){
      const side=deviation>=0?t("aboveReference"):t("belowReference");
      historicalWarning(`⚠ ${t("historicalPriceWarning")}: ${Math.abs(deviation).toFixed(1)} % ${side} · ${t("enteredPrice")}: ${fmtFiat(entered,currency)} / BTC · ${t("historicalReference")}: ${fmtFiat(reference,currency)} / BTC`,true);
    }else historicalWarning();
  }catch(_error){if(revision===historicalPriceCheckRevision)historicalWarning(t("historicalReferenceUnavailable"),false);}
}
function markManualHistoricalPrice(){const input=$("#transactionForm [name=price]");if(input)delete input.dataset.autoHistorical;}
function resetTransactionEditMode({resetForm=true}={}){
  const form=$("#transactionForm"); if(!form)return;
  state.editingEntryId="";
  if(resetForm)form.reset();
  const type=form.querySelector('[name="type"]');
  if(type){type.disabled=false;if(!["purchase","income","sale","expense","network_fee","stack"].includes(type.value))type.value="purchase";}
  $("#transactionFormTitle").textContent=t("newEntry");
  $("#transactionSubmit").textContent=t("saveEntry");
  $("#transactionCancelEdit").classList.add("hidden");
  form.querySelectorAll('[data-auto-calculated]').forEach(item=>delete item.dataset.autoCalculated);
  if(resetForm){setDefaultDate();const unit=form.querySelector('[name="amount_unit"]');unit.value=state.unit;unit.dataset.previousUnit=state.unit;}
  updateTransactionFieldVisibility();
  updateTransactionFiatLabel();syncTransactionCalculator();scheduleHistoricalPriceCheck();
}
function beginEditEntry(entryId){
  const entry=(state.data?.entries||[]).find(item=>item.id===entryId); if(!entry)return;
  const form=$("#transactionForm"); state.editingEntryId=entryId;
  const type=form.querySelector('[name="type"]');
  type.disabled=false;type.value=entry.type;
  form.querySelector('[name="depot_id"]').value=entry.depot_id||"main";
  const unit=form.querySelector('[name="amount_unit"]');unit.value=state.unit;unit.dataset.previousUnit=state.unit;
  form.querySelector('[name="amount"]').value=compactInputNumber(btcToDisplayedAmount(Number(entry.amount_btc||0),state.unit),state.unit==="sats"?0:8);
  const currency=form.querySelector('[name="currency"]'); if(entry.currency&&!([...currency.options].some(o=>o.value===entry.currency)))currency.insertAdjacentHTML("beforeend",`<option value="${esc(entry.currency)}">${esc(entry.currency)}</option>`); if(entry.currency)currency.value=entry.currency;
  form.querySelector('[name="price"]').value=entry.price||"";
  form.querySelector('[name="fee"]').value=entry.type==="network_fee"?0:(entry.fee||0);
  const network=form.querySelector('[name="network"]');if(network)network.value=entry.network||"onchain";
  const total=entry.price?transactionFiatTotal(entry.type,Number(entry.amount_btc||0),Number(entry.price||0),Number(entry.fee||0)):NaN;
  form.querySelector('[name="fiat_total"]').value=Number.isFinite(total)&&total>0?Number(total).toFixed(2):"";
  form.querySelector('[name="timestamp"]').value=transactionLocalTimestamp(entry.timestamp);
  form.querySelector('[name="note"]').value=entry.note||"";
  form.querySelectorAll('[data-auto-calculated]').forEach(item=>delete item.dataset.autoCalculated);
  $("#transactionFormTitle").textContent=t("editEntry");
  $("#transactionSubmit").textContent=t("saveChanges");
  $("#transactionCancelEdit").classList.remove("hidden");
  updateTransactionFieldVisibility();
  updateTransactionFiatLabel();syncTransactionCalculator();scheduleHistoricalPriceCheck();
  form.scrollIntoView({behavior:"smooth",block:"start"}); setTimeout(()=>form.querySelector('[name="amount"]')?.focus(),250);
}

function openDeleteEntryDialog(entryId){
  const entry=(state.data?.entries||[]).find(item=>String(item.id)===String(entryId));
  if(!entry)return;
  state.pendingDeleteEntryId=String(entry.id);
  const modal=$("#deleteEntryModal");
  modal.dataset.working="0";
  $("#deleteEntryMessage").textContent=t("deleteEntryText");
  const typeLabel=t(entry.type)||entry.type;
  $("#deleteEntryDetails").innerHTML=`<div><span>${esc(t("dateTime"))}</span><strong>${esc(fmtDateTime(entry.timestamp))}</strong></div><div><span>${esc(t("type"))}</span><strong>${esc(typeLabel)}</strong></div><div><span>${esc(t("amount"))}</span><strong>${privateHtml(fmtStack(entry.amount_btc))}</strong></div><div><span>${esc(t("depot"))}</span><strong>${esc(depotName(entry.depot_id))}</strong></div>`;
  $("#deleteEntryConfirm").disabled=false;
  $("#deleteEntryConfirm").textContent=t("deleteEntryNow");
  modal.classList.remove("hidden");
  document.body.classList.add("import-modal-open");
  $("#deleteEntryCancel")?.focus();
}
function closeDeleteEntryDialog(){
  const modal=$("#deleteEntryModal");
  if(!modal||modal.dataset.working==="1")return;
  modal.classList.add("hidden");
  state.pendingDeleteEntryId="";
  if($("#deleteAllModal")?.classList.contains("hidden")&&!state.csvImport)document.body.classList.remove("import-modal-open");
}
async function confirmDeleteEntry(){
  const entryId=state.pendingDeleteEntryId,modal=$("#deleteEntryModal"),button=$("#deleteEntryConfirm");
  if(!entryId||!modal)return;
  modal.dataset.working="1";
  button.disabled=true;
  button.textContent=t("deleteEntryWorking");
  try{
    await service("delete_entry",{config_entry_id:state.entryId,ledger_entry_id:entryId});
    modal.dataset.working="0";
    modal.classList.add("hidden");
    state.pendingDeleteEntryId="";
    document.body.classList.remove("import-modal-open");
    await loadData();
  }catch(error){
    modal.dataset.working="0";
    button.disabled=false;
    button.textContent=t("deleteEntryNow");
    toast(error.message||String(error));
  }
}

function renderDeleteAllDialog(step=1,{working=false,message=""}={}) {
  const modal=$("#deleteAllModal"),ackRow=$("#deleteAllAcknowledgeRow"),ack=$("#deleteAllAcknowledge"),next=$("#deleteAllNext"),finalButton=$("#deleteAllFinal"),cancel=$("#deleteAllCancel"),close=$("#deleteAllClose");
  if(!modal)return;
  modal.dataset.step=String(step);
  $("#deleteAllStep").textContent=step===1?t("deleteAllStepBackup"):t("deleteAllStepFinal");
  $("#deleteAllMessage").textContent=message||(step===1?t("deleteAllBackupText"):t("deleteAllFinalText"));
  ackRow.classList.toggle("hidden",step!==2);
  next.classList.toggle("hidden",step!==1);
  finalButton.classList.toggle("hidden",step!==2);
  next.textContent=t("deleteAllBackupContinue");
  finalButton.textContent=working?t("deleteAllWorking"):t("deleteAllNow");
  if(step===1)ack.checked=false;
  finalButton.disabled=working||!ack.checked;
  [next,cancel,close].forEach(button=>button.disabled=working);
}
function openDeleteAllDialog(){
  if(!state.data?.security?.owner||!(state.data?.entries||[]).length)return;
  renderDeleteAllDialog(1);
  $("#deleteAllModal").classList.remove("hidden");
  document.body.classList.add("import-modal-open");
  $("#deleteAllNext")?.focus();
}
function closeDeleteAllDialog(){
  const modal=$("#deleteAllModal");
  if(!modal||modal.dataset.working==="1")return;
  modal.classList.add("hidden");
  document.body.classList.remove("import-modal-open");
}
async function deleteAllLedgerEntriesCompat(){
  const original=[...(state.data?.entries||[])];
  try{
    return await service("delete_all_entries",{config_entry_id:state.entryId});
  }catch(firstError){
    await loadData();
    let remaining=[...(state.data?.entries||[])];
    if(!remaining.length)return {deleted:original.length,fallback:true};
    renderDeleteAllDialog(2,{working:true,message:t("deleteAllFallback")});
    const priority=item=>["sale","expense"].includes(item.type)?0:1;
    remaining.sort((a,b)=>priority(a)-priority(b)||String(b.timestamp||"").localeCompare(String(a.timestamp||"")));
    let deleted=Math.max(0,original.length-remaining.length);
    for(const item of remaining){
      try{
        await service("delete_entry",{config_entry_id:state.entryId,ledger_entry_id:item.id});
        deleted+=1;
      }catch(error){
        await loadData();
        if((state.data?.entries||[]).some(entry=>entry.id===item.id))throw error;
      }
    }
    return {deleted,fallback:true};
  }
}
async function confirmDeleteAllEntries(){
  const modal=$("#deleteAllModal");
  if(!$("#deleteAllAcknowledge")?.checked)return;
  modal.dataset.working="1";
  renderDeleteAllDialog(2,{working:true});
  try{
    const result=await deleteAllLedgerEntriesCompat();
    modal.dataset.working="0";
    modal.classList.add("hidden");
    document.body.classList.remove("import-modal-open");
    toast(`${t("allEntriesDeleted")} (${Number(result.deleted||0)})`);
    await loadData();
  }catch(error){
    modal.dataset.working="0";
    renderDeleteAllDialog(2,{message:`${t("deleteAllFailed")} ${error.message||error}`});
  }
}

function setDefaultDate(){const input=$("#transactionForm input[name=timestamp]"),now=new Date(Date.now()-new Date().getTimezoneOffset()*60000);input.value=now.toISOString().slice(0,16);}

$("#langButton").onclick=()=>{state.lang=state.lang==="de"?"en":"de";applyLanguage();};
$("#themeButton").onclick=()=>{state.theme=state.theme==="dark"?"light":"dark";applyTheme();if(state.activeTab==="overview")renderChart();};
$("#unitButton").onclick=()=>{state.unit=state.unit==="BTC"?"sats":"BTC";applyUnit();};
$("#refreshButton").onclick=()=>loadData().catch(error=>toast(error.message));
$("#leakTestButton").onclick=async event=>{
  event.preventDefault();
  event.stopPropagation();
  activateTab("settings", {store:true});
  await requestTorIdentity({withLeakTest:true});
};
$("#newTorIdentityButton").onclick=async event=>{event.preventDefault();activateTab("settings",{store:true});await requestTorIdentity({withLeakTest:false});};
$("#saveTorRotationButton").onclick=async()=>{
  const button=$("#saveTorRotationButton"), result=$("#torRotationResult");
  button.disabled=true;
  try{
    state.torRotation=await api("api/tor/rotation-settings",{method:"POST",body:JSON.stringify({entry_id:state.entryId,enabled:$("#torRotationEnabled").checked,interval_minutes:Number($("#torRotationInterval").value)}),timeoutMs:10000});
    renderTorRotation();renderNetworkStatus();
    result.textContent=t("rotationSaved");result.classList.add("positive");result.classList.remove("negative");
  }catch(error){result.textContent=localizeNetworkError(error.message||String(error));result.classList.add("negative");result.classList.remove("positive");}
  finally{button.disabled=!state.data?.security?.owner;}
};
$("#discreetMode").onchange=event=>applyDiscreetMode(event.target.checked);
$("#privacyButton").onclick=()=>applyDiscreetMode(!state.discreet);
$("#portfolioSelect").onchange=async event=>{state.entryId=event.target.value;state.halvings=[];state.halvingInfo=null;state.halvingsEntryId="";state.halvingsError="";state.walletWatch=null;state.walletWatchLoading=false;state.walletWatchTxOverviews={};state.walletWatchOpenTxDetails.clear();bitcoinNetworkRefreshAt=0;localStorage.setItem("bst_entry",state.entryId);initWalletWatchPanelToggles();await loadData();await loadTorRotationSettings();if(state.activeTab==="walletwatch"&&!state.data?.locked)await loadWalletWatch();};
async function reloadSelectedChartRange(){
  // Every range selection performs a real source refresh for the selected
  // resolution. The local cache accelerates rendering but never prevents the
  // newest tail from being requested. Intraday tiers refresh exact OHLC
  // candles; daily/long ranges run the incremental daily sync (not a full
  // redownload when the durable cache is already complete).
  await loadData();
  if(!state.data||state.data.locked)return;
  await ensureDashboardSection("chart");
  await refreshLivePrice({silent:true});
  const interval=chartIntervalMinutesForRange(),days=displayDaysForRange();
  if(interval<1440&&days>0&&days<=731){
    await ensureIntradayHistory({force:true,interactive:false});
    return;
  }
  try{
    const result=await service("sync_history",{config_entry_id:state.entryId},{timeoutMs:300000});
    if(result?.errors?.length)console.warn("Bitcoin Stack automatic range history refresh notes",result.errors);
  }catch(error){
    // Keep the already cached chart usable when a provider/Tor request fails.
    // The next range selection/manual refresh retries automatically.
    console.warn("Bitcoin Stack automatic range history refresh failed",errorText(error));
  }
  await loadData();
  if(!state.data||state.data.locked)return;
  await ensureDashboardSection("chart");
  await refreshLivePrice({silent:true});
  invalidateDerivedCaches();
  if(state.activeTab==="overview")renderOverview();
}
$("#historyRange").onchange=async event=>{state.historyRange=event.target.value;localStorage.setItem("bst_history_range",state.historyRange);await reloadSelectedChartRange();};
if($("#refreshChartPrices")) $("#refreshChartPrices").onclick=refreshChartPrices;
if($("#chartMilestonesButton")) $("#chartMilestonesButton").onclick=()=>{state.showMilestones=!state.showMilestones;localStorage.setItem("bst_chart_milestones",state.showMilestones?"1":"0");updateChartMarkerButtons();renderChart();};
if($("#chartHalvingsButton")) $("#chartHalvingsButton").onclick=()=>{state.showHalvings=!state.showHalvings;localStorage.setItem("bst_chart_halvings",state.showHalvings?"1":"0");updateChartMarkerButtons();if(state.showHalvings&&!state.halvings.length)void loadHalvings();renderChart();};
$("#chartCurrency").onchange=event=>{state.chartCurrency=event.target.value;localStorage.setItem("bst_chart_currency",state.chartCurrency);renderOverview();};
$("#chartMode").onchange=event=>{state.chartMode=String(event.target.value||"price");if(state.chartMode==="price_market")void ensureChartMarketAssessmentHistory();renderChart();};
$("#chartScaleLeftButton").onclick=()=>{const button=$("#chartScaleLeftButton");if(button.disabled)return;setChartAxisScale(0,chartAxisScale(0)==="linear"?"log":"linear");renderChart();};
$("#chartScaleRightButton").onclick=()=>{const button=$("#chartScaleRightButton");if(button.disabled)return;setChartAxisScale(1,chartAxisScale(1)==="linear"?"log":"linear");renderChart();};
$("#overlayOpacity").oninput=event=>{state.overlayOpacity=Number(event.target.value);localStorage.setItem("bst_overlay_opacity",String(state.overlayOpacity));if($("#overlayOpacityValue"))$("#overlayOpacityValue").textContent=`${state.overlayOpacity} %`;scheduleChartRender();};
$("#ledgerSearch").oninput=()=>{state.ledgerPage=1;renderLedger();};
$("#ledgerPeriodFilter").onchange=event=>{state.ledgerPeriodFilter=event.target.value||"all";state.ledgerPage=1;localStorage.setItem("bst_ledger_period_filter",state.ledgerPeriodFilter);renderLedger();};
$("#deleteAllEntries").onclick=openDeleteAllDialog;
$$('.tabs button').forEach(button=>button.onclick=event=>{event.preventDefault();activateTab(button.dataset.tab,{store:true,loadLog:true});});
$("#refreshLogs").onclick=()=>loadLogs();
$("#downloadLogs").onclick=async()=>{try{await downloadApi(`api/logs/download?entry_id=${encodeURIComponent(state.entryId)}`,{},"bitcoin-stack-tracker-app-log.jsonl");}catch(error){toast(error.message||String(error));}};
$("#clearLogs").onclick=async()=>{if(!confirm(t("confirmClearLogs")))return;await api("api/logs/clear",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({entry_id:state.entryId})});toast(t("logCleared"));await loadLogs();};

$("#csvFileInput").onchange=updateCsvFileName;
$("#csvImportForm").onsubmit=event=>previewCsvImport(event).catch(error=>toast(error.message||String(error)));
$("#csvImportClose").onclick=closeCsvImportPreview;
$("#csvImportCancel").onclick=closeCsvImportPreview;
$("#csvDeselectAll").onclick=()=>{$$('#csvImportBody [data-field="selected"]').forEach(item=>item.checked=false);csvRowsFromModal();updateCsvSelectedCount();};
$("#csvSelectValid").onclick=()=>{csvRowsFromModal();state.csvImport?.rows?.forEach(row=>{if(!row.removed)row.selected=Boolean(row.valid&&!row.duplicate);});renderCsvImportPreview();};
$("#csvImportConfirm").addEventListener("click",event=>{event.preventDefault();event.stopPropagation();confirmCsvImport();});
$("#csvOptionalFieldsClear").onclick=()=>{if(!state.csvImport)return;csvRowsFromModal();state.csvImport.optional_note_selection=[];renderCsvImportPreview();};
$("#csvImportModal").addEventListener("click",event=>{if(event.target.id==="csvImportModal")closeCsvImportPreview();});
$("#csvHorizontalScroll").addEventListener("input",event=>{const wrap=$(".import-table-wrap");if(wrap){wrap.scrollLeft=Number(event.currentTarget.value);updateCsvHorizontalScroll();}});
$("#csvScrollLeft").addEventListener("click",event=>{event.preventDefault();scrollCsvTable(-1);});
$("#csvScrollRight").addEventListener("click",event=>{event.preventDefault();scrollCsvTable(1);});
$(".import-table-wrap").addEventListener("scroll",updateCsvHorizontalScroll,{passive:true});
// Global resize intentionally does not synchronously measure the hidden CSV table.
$("#deleteEntryClose").onclick=closeDeleteEntryDialog;
$("#deleteEntryCancel").onclick=closeDeleteEntryDialog;
$("#deleteEntryConfirm").onclick=()=>confirmDeleteEntry();
$("#deleteEntryModal").addEventListener("click",event=>{if(event.target.id==="deleteEntryModal")closeDeleteEntryDialog();});
$("#deleteAllClose").onclick=closeDeleteAllDialog;
$("#deleteAllCancel").onclick=closeDeleteAllDialog;
$("#deleteAllNext").onclick=()=>{renderDeleteAllDialog(2);$("#deleteAllAcknowledge")?.focus();};
$("#deleteAllAcknowledge").onchange=event=>{$("#deleteAllFinal").disabled=!event.currentTarget.checked;};
$("#deleteAllFinal").onclick=()=>confirmDeleteAllEntries();
$("#deleteAllModal").addEventListener("click",event=>{if(event.target.id==="deleteAllModal")closeDeleteAllDialog();});
window.addEventListener("keydown",event=>{if(event.key!=="Escape")return;if(state.csvImport)closeCsvImportPreview();else if(!$("#deleteEntryModal")?.classList.contains("hidden"))closeDeleteEntryDialog();else if(!$("#deleteAllModal")?.classList.contains("hidden"))closeDeleteAllDialog();});

$("#transactionForm select[name=type]").onchange=()=>{
  updateTransactionFieldVisibility();updateTransactionFiatLabel();syncTransactionCalculator("type");scheduleHistoricalPriceCheck();
};
$("#transactionForm select[name=currency]").addEventListener("change",()=>{updateTransactionFiatLabel();syncTransactionCalculator("currency");});
["amount","price","fiat_total","fee"].forEach(name=>$("#transactionForm [name="+name+"]")?.addEventListener("input",event=>{if(name==="price")markManualHistoricalPrice();syncTransactionCalculator(event.currentTarget.name);scheduleHistoricalPriceCheck();}));
$("#transactionForm select[name=amount_unit]").addEventListener("change",event=>{
  const input=$("#transactionForm [name=amount]"),previous=event.currentTarget.dataset.previousUnit||"BTC",next=event.currentTarget.value||"BTC",btc=displayedAmountToBtc(input?.value,previous);
  if(Number.isFinite(btc)&&btc>0&&input)input.value=compactInputNumber(btcToDisplayedAmount(btc,next),next==="sats"?0:8);
  event.currentTarget.dataset.previousUnit=next;syncTransactionCalculator("amount_unit");
});
$("#transactionForm [name=timestamp]")?.addEventListener("change",scheduleHistoricalPriceCheck);
$("#transactionForm [name=currency]")?.addEventListener("change",scheduleHistoricalPriceCheck);
$("#transactionForm [name=amount_unit]")?.addEventListener("change",scheduleHistoricalPriceCheck);
$("#transactionForm [name=network]")?.addEventListener("change",scheduleHistoricalPriceCheck);
$("#transactionCancelEdit").onclick=()=>resetTransactionEditMode();
$("#transactionForm").onsubmit=async event=>{
  event.preventDefault();const form=new FormData(event.target),existing=state.editingEntryId?(state.data?.entries||[]).find(item=>item.id===state.editingEntryId):null,type=String(form.get("type")||"purchase");
  const amountBtc=displayedAmountToBtc(form.get("amount"),form.get("amount_unit"));
  if(type!=="stack"){
    const price=Number(form.get("price")),fiatTotal=Number(form.get("fiat_total")),fee=type==="network_fee"?0:Number(form.get("fee")||0);
    if(type==="network_fee"){if(!(amountBtc>0)||!(price>0)){toast(t("fiatControlBlocked"));scheduleHistoricalPriceCheck();return;}}
    else {const control=transactionControlCheck(type,amountBtc,price,fiatTotal,fee);if(!control.complete||!control.valid){toast(t("fiatControlBlocked"));syncTransactionCalculator();return;}}
  }
  const payload={config_entry_id:state.entryId,type,amount:Number(form.get("amount")),amount_unit:form.get("amount_unit"),timestamp:form.get("timestamp")?new Date(form.get("timestamp")).toISOString():undefined,note:form.get("note")||"",depot_id:form.get("depot_id")};
  if(type!=="stack")Object.assign(payload,{currency:form.get("currency")||"",price:Number(form.get("price")||0)});
  if(["purchase","income","sale","expense"].includes(type))Object.assign(payload,{fee:Number(form.get("fee")||0),fee_btc:0,fee_btc_affects_stack:false});
  if(type==="network_fee")payload.network=form.get("network")||"onchain";
  if(existing){payload.ledger_entry_id=existing.id;await service("update_entry",payload);resetTransactionEditMode();toast(t("entryUpdated"));await loadData();return;}
  delete payload.type;
  const action=type==="purchase"?"add_purchase":type==="income"?"add_income":type==="sale"?"add_sale":type==="expense"?"add_expense":type==="network_fee"?"add_network_fee":"add_stack";
  await service(action,payload);resetTransactionEditMode();toast(t("entrySaved"));await loadData();
};
$("#depotForm").onsubmit=async event=>{event.preventDefault();await service("add_depot",{config_entry_id:state.entryId,depot_name:new FormData(event.target).get("depot_name")});event.target.reset();await loadData();};
$("#goalForm").onsubmit=async event=>{event.preventDefault();const form=new FormData(event.target);await service("add_goal",{config_entry_id:state.entryId,goal_name:form.get("goal_name"),goal:Number(form.get("goal")),goal_unit:form.get("goal_unit"),depot_id:form.get("depot_id"),currency:form.get("currency")});event.target.reset();$("#goalForm select[name=goal_unit]").value=state.unit;toast(t("goalSaved"));await loadData();};
$("#taxForm").onsubmit=async event=>{event.preventDefault();const form=new FormData(event.target);await service("set_tax_settings",{config_entry_id:state.entryId,long_term_days:Number(form.get("long_term_days")),tax_note:form.get("tax_note")});toast(t("ruleSaved"));await loadData();};
async function saveHistorySettings(event){
  if(event){event.preventDefault();event.stopPropagation();}
  activateTab("settings", {store:true});
  const button=$("#saveHistorySettingsButton");
  const enabled=$("#historyEnabled").checked;
  const autoSync=enabled && $("#historyAutoSync").checked;
  button.disabled=true;
  try{
    const result=await service("set_history_settings",{
      config_entry_id:state.entryId,
      enabled,
      auto_sync:autoSync
    });
    state.data.history={
      ...(state.data.history||{}),
      enabled:Boolean(result.history_enabled ?? enabled),
      auto_sync:Boolean(result.history_auto_sync ?? autoSync),
      auto_sync_runtime_active:Boolean(result.history_timer_active ?? autoSync),
      tor_proxy:result.history_tor_proxy || $("#historyTorProxy").value,
      public_route:result.public_history_route || state.data.history?.public_route || "Tor only"
    };
    renderHistorySettings();
    const saveResult=$("#historySaveResult");
    saveResult.textContent=t("historySettingsSaved");
    saveResult.classList.add("positive");
    saveResult.classList.remove("negative");
    toast(t("historySettingsSaved"));
  }catch(error){
    const saveResult=$("#historySaveResult");
    saveResult.textContent=error.message||String(error);
    saveResult.classList.add("negative");
    saveResult.classList.remove("positive");
    toast(error.message||String(error));
  }finally{
    button.disabled=!state.data?.security?.owner;
  }
}
$("#buyOpportunitySettingsForm").onsubmit=saveBuyOpportunitySettings;
$("#resetBuyOpportunitySettingsButton").onclick=resetBuyOpportunitySettings;
$("#openMarketAssessment").onclick=()=>activateTab("market",{store:true,loadLog:false});
$("#buyOpportunityProfile").onchange=event=>{const preset=BUY_OPPORTUNITY_PRESETS[event.target.value];if(preset)setBuyOpportunityWeightInputs(preset);};
if($("#marketAssessmentHistoryRange"))$("#marketAssessmentHistoryRange").onchange=event=>{state.marketAssessmentHistoryRange=String(event.target.value||"3y");localStorage.setItem("bst_market_assessment_history_range",state.marketAssessmentHistoryRange);state.marketAssessmentHistory=null;void loadMarketAssessmentHistory({force:true});};
if($("#marketAssessmentHistoryRefresh"))$("#marketAssessmentHistoryRefresh").onclick=()=>{state.marketAssessmentHistory=null;void loadMarketAssessmentHistory({force:true});};
if($("#marketAssessmentHistoryPriceOverlay"))$("#marketAssessmentHistoryPriceOverlay").onchange=event=>{state.marketAssessmentHistoryPriceOverlay=Boolean(event.target.checked);localStorage.setItem("bst_market_assessment_history_price_overlay",state.marketAssessmentHistoryPriceOverlay?"1":"0");renderMarketAssessmentHistory();};
if($("#marketAssessmentHistoryPriceOpacity"))$("#marketAssessmentHistoryPriceOpacity").oninput=event=>{state.marketAssessmentHistoryPriceOpacity=Math.max(0,Math.min(100,Number(event.target.value)||0));localStorage.setItem("bst_market_assessment_history_price_opacity",String(state.marketAssessmentHistoryPriceOpacity));if($("#marketAssessmentHistoryPriceOpacityValue"))$("#marketAssessmentHistoryPriceOpacityValue").textContent=`${Math.round(state.marketAssessmentHistoryPriceOpacity)} %`;renderMarketAssessmentHistory();};
if($("#marketAssessmentHistoryPriceScale"))$("#marketAssessmentHistoryPriceScale").onchange=event=>{state.marketAssessmentHistoryPriceScale=String(event.target.value||"log")==="linear"?"linear":"log";localStorage.setItem("bst_market_assessment_history_price_scale",state.marketAssessmentHistoryPriceScale);renderMarketAssessmentHistory();};
if($("#marketAssessmentHistorySmoothing"))$("#marketAssessmentHistorySmoothing").onchange=event=>{state.marketAssessmentHistorySmoothing=[1,3,5,7,14,30].includes(Number(event.target.value))?Number(event.target.value):5;localStorage.setItem("bst_market_assessment_history_smoothing",String(state.marketAssessmentHistorySmoothing));invalidateDerivedCaches();renderMarketAssessmentHistory();if(state.activeTab==="overview"&&state.chartMode==="price_market")renderChart();};
if($("#marketAssessmentHistoryResetDisplay"))$("#marketAssessmentHistoryResetDisplay").onclick=resetMarketAssessmentChartDisplayDefaults;
for(const input of $$("#buyOpportunitySettingsForm input[name^=weight_]")){input.oninput=()=>{$("#buyOpportunityProfile").value="custom";};}
$("#historySettingsForm").onsubmit=saveHistorySettings;
$("#saveHistorySettingsButton").onclick=saveHistorySettings;
$("#historyEnabled").onchange=()=>{$("#historyAutoSync").disabled=!$("#historyEnabled").checked||!state.data.security?.owner;if(!$("#historyEnabled").checked)$("#historyAutoSync").checked=false;};
$("#syncButton").onclick=async()=>{const button=$("#syncButton"),resultBox=$("#actionResult");button.disabled=true;resultBox.textContent=t("historySyncRunning");try{const result=await service("sync_history",{config_entry_id:state.entryId},{timeoutMs:300000});resultBox.textContent=`${t("syncDone")}: ${historyCountSummary(result.cached_daily_values||{})}${result.errors?.length?` · ${result.errors.join(" · ")}`:""}`;resultBox.className=`result ${result.errors?.length?"negative":"positive"}`;await loadData();await ensureIntradayHistory({force:true,interactive:false});}catch(error){resultBox.textContent=errorText(error);resultBox.className="result negative";toast(errorText(error));}finally{button.disabled=!state.data?.history?.enabled;}};
$("#exportButton").onclick=async()=>{try{await downloadApi(`api/download?entry_id=${encodeURIComponent(state.entryId)}&delimiter=${encodeURIComponent(";")}`,{},"bitcoin-stack-export.zip");const note=String(state.data.tax_settings.note||"").trim();const disclaimer=note?`${note} · ${t("holdingDisclaimer")}`:t("holdingDisclaimer");$("#actionResult").innerHTML=`<strong>${esc(t("exportCreated"))}</strong><br><small>${esc(disclaimer)}</small>`;}catch(error){toast(error.message||String(error));}};
$("#accessForm").onsubmit=async event=>{event.preventDefault();const allowed=$$("#userAccessList input:checked").map(item=>item.value);await service("set_allowed_users",{config_entry_id:state.entryId,allowed_user_ids:allowed});toast(t("accessSaved"));await loadData();};
$("#saveSensorMode").onclick=async()=>{if($("#sensitiveSensors").checked&&!confirm(t("sensorWarning")))return;await service("set_sensitive_sensors",{config_entry_id:state.entryId,enabled:$("#sensitiveSensors").checked});toast(t("sensorModeSaved"));setTimeout(()=>location.reload(),900);};
$("#autoLockMinutes").oninput=event=>{
  const value=Number(event.target.value);
  if(![0,5,15,30,60,120].includes(value))return;
  state.autoLockMinutes=value;
  localStorage.setItem("bst_auto_lock_minutes",String(value));
  state.lastActivityAt=Date.now();
  localStorage.setItem("bst_last_activity_at",String(state.lastActivityAt));
  renderAutoLock();
  scheduleAutoLock();
  void syncCoreAutoLock({touch:true,silent:false});
};
$("#refreshConnectionsButton").onclick=async()=>{await refreshConnectionInventory({silent:false,refreshLive:true});await refreshNetworkStatus({force:true,silent:true});renderConnections();};
$("#unlockForm").onsubmit=async event=>{event.preventDefault();const input=event.target.elements.password;let password=String(input?.value||"");if(input)input.value="";try{await hardenedUnlock(password);state.lastActivityAt=Date.now();await loadData();if(!state.data?.locked&&state.data?.security?.owner&&!state.walletWatch&&!state.walletWatchLoading)await loadWalletWatch();await syncCoreAutoLock({touch:true,silent:false});}finally{password="";event.target.reset();}};
$("#lockButton").onclick=async()=>{await service("lock_vault",{config_entry_id:state.entryId});state.lastActivityAt=Date.now();await loadData();};
$("#enableEncryptionForm").onsubmit=async event=>{event.preventDefault();const form=new FormData(event.target);let password=String(form.get("password")||""),confirmPassword=String(form.get("password_confirm")||"");event.target.reset();try{if(password!==confirmPassword)throw new Error(t("passwordMismatch"));await hardenedEnableEncryption(password);toast(t("encryptionChanged"));setTimeout(()=>location.reload(),900);}finally{password="";confirmPassword="";form.delete("password");form.delete("password_confirm");}};
$("#disableEncryptionButton").onclick=async()=>{if(!confirm(t("confirmDisableEncryption")))return;await hardenedDisableEncryption();toast(t("encryptionChanged"));setTimeout(()=>location.reload(),900);};
$("#changePasswordForm").onsubmit=async event=>{event.preventDefault();const form=new FormData(event.target);let currentPassword=String(form.get("current_password")||""),newPassword=String(form.get("new_password")||""),confirmPassword=String(form.get("new_password_confirm")||"");event.target.reset();try{if(newPassword!==confirmPassword)throw new Error(t("passwordMismatch"));await hardenedChangePassword(currentPassword,newPassword);toast(t("passwordChanged"));}finally{currentPassword="";newPassword="";confirmPassword="";form.delete("current_password");form.delete("new_password");form.delete("new_password_confirm");}};
$("#backupFileInput").onchange=updateBackupFileName;
$("#backupForm").onsubmit=async event=>{event.preventDefault();const form=new FormData(event.target);let password=String(form.get("password")||""),confirmPassword=String(form.get("password_confirm")||"");event.target.reset();try{if(password!==confirmPassword)throw new Error(t("passwordMismatch"));await downloadApi(`api/backup?entry_id=${encodeURIComponent(state.entryId)}`,{method:"POST",headers:{"Content-Type":"text/plain; charset=utf-8"},body:password,timeoutMs:180000},"bitcoin-stack-backup.bstbackup");$("#backupResult").textContent=`${t("backupCreated")} · ${t("backupCreatedHealth")}`;await loadBackupHealth();}finally{password="";confirmPassword="";form.delete("password");form.delete("password_confirm");}};
$("#restoreForm").onsubmit=async event=>{event.preventDefault();if(!confirm(t("confirmRestore")))return;const form=new FormData(event.target),upload=new FormData();upload.append("password",form.get("password"));upload.append("backup",form.get("backup"));event.target.reset();updateBackupFileName();try{const result=await api(`api/restore?entry_id=${encodeURIComponent(state.entryId)}`,{method:"POST",body:upload,timeoutMs:180000});$("#backupResult").textContent=`${t("backupRestored")}: ${result.entries||0} entries`;await loadData();await loadBackupHealth();}finally{upload.delete("password");upload.delete("backup");form.delete("password");form.delete("backup");}};
$("#fiatFreeMode").onchange=event=>applyFiatFreeMode(event.target.checked,state.satsPerFiat);
$("#satsPerFiatMode").onchange=event=>applyFiatFreeMode(state.fiatFree,event.target.checked);
$("#saveBackupHealth").onclick=saveBackupHealthSettings;
$("#markRestoreTest").onclick=markRestoreTest;
$$('.tabs button[data-tab="settings"]').forEach(button=>button.addEventListener("click",()=>loadBackupHealth()));
$("#portfolioSelect").addEventListener("change",()=>setTimeout(loadBackupHealth,250));
window.addEventListener("storage",event=>{if(event.key==="bst_last_activity_at"){state.lastActivityAt=sharedLastActivity();scheduleAutoLock();}else if(event.key==="bst_auto_lock_minutes"){const value=Number(event.newValue);if([0,5,15,30,60,120].includes(value)){state.autoLockMinutes=value;scheduleAutoLock();}}});
for(const activityEvent of ["pointerdown","keydown","touchstart","input"]){window.addEventListener(activityEvent,recordUserActivity,{passive:true});}
document.addEventListener("visibilitychange",()=>{if(!document.hidden&&state.entryId){void refreshNetworkStatus({silent:true});if(state.activeTab==="settings")void refreshConnectionInventory({silent:true});}});
const compactTableMedia=window.matchMedia("(max-width: 760px)");
const refreshCompactTableLayout=()=>{if(!state.data||state.data.locked)return;if(state.activeTab==="ledger")renderLedger();else if(state.activeTab==="tax")renderTax();};
if(typeof compactTableMedia.addEventListener==="function")compactTableMedia.addEventListener("change",refreshCompactTableLayout);
else if(typeof compactTableMedia.addListener==="function")compactTableMedia.addListener(refreshCompactTableLayout);
window.addEventListener("unhandledrejection",event=>toast(errorText(event.reason)));
window.addEventListener("resize",scheduleViewportSettledWork,{passive:true});


/* semantic Wavespace event grouping, card sales and variable row counts */
function fmtFiat(value, currency) {
  if (state.fiatFree) return "–";
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  try { return new Intl.NumberFormat(state.lang === "de" ? "de-DE" : "en-US", {style:"currency",currency,maximumFractionDigits:2}).format(Number(value)); }
  catch { return `${fmtNumber(value,2)} ${currency}`; }
}
function signedFiat(value, currency) {
  if (state.fiatFree) return "–";
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  const number = Number(value), sign = number > 0 ? "+" : number < 0 ? "−" : "±";
  return `${sign}${fmtFiat(Math.abs(number), currency)}`;
}
function fmtSatsPerFiat(price, currency) {
  const value = Number(price);
  if (!Number.isFinite(value) || value <= 0) return "–";
  return `${fmtNumber(SATS_PER_BTC / value, 0)} sats/${currency}`;
}
function applyFiatFreeMode(enabled, satsPerFiat = state.satsPerFiat) {
  state.fiatFree = Boolean(enabled);
  state.satsPerFiat = Boolean(satsPerFiat);
  localStorage.setItem("bst_fiat_free_mode", state.fiatFree ? "1" : "0");
  localStorage.setItem("bst_sats_per_fiat", state.satsPerFiat ? "1" : "0");
  document.body.classList.toggle("fiat-free-mode", state.fiatFree);
  const toggle = $("#fiatFreeMode"), satsToggle = $("#satsPerFiatMode");
  if (toggle) toggle.checked = state.fiatFree;
  if (satsToggle) {
    satsToggle.checked = state.satsPerFiat;
    satsToggle.disabled = !state.fiatFree;
  }
  updateFiatFreeChartOptions();
  if (state.data && !state.data.locked) renderAll();
}
function updateFiatFreeChartOptions() {
  const select = $("#chartMode");
  if (!select) return;
  const allowed = state.fiatFree
    ? new Set(state.satsPerFiat ? ["price","stack","price_stack","price_market"] : ["stack"])
    : null;
  [...select.options].forEach(option => {
    option.hidden = Boolean(allowed && !allowed.has(option.value));
    option.disabled = Boolean(allowed && !allowed.has(option.value));
  });
  if (allowed && !allowed.has(select.value)) {
    select.value = state.satsPerFiat ? "price_stack" : "stack";
    state.chartMode = select.value;
    localStorage.setItem("bst_chart_mode", state.chartMode);
  }
}
function longRangeUniformStepDays(values) {
  const points = sortedNumericPoints(filterSeriesToSelectedStart(values || {}));
  if (points.length < 2) return 1;
  const dayMs = 86400000;
  const first = chartTimestamp(points[0].day), last = chartTimestamp(points.at(-1).day);
  const spanDays = Math.max(1, Math.ceil((last - first) / dayMs));
  // Keep roughly <=520 representative closes. In addition, inspect the 85th
  // percentile of the source spacing. If the older cache is typically weekly,
  // the recent daily section is therefore compacted to weekly too.
  const gaps = [];
  for (let index=1; index<points.length; index++) {
    const gap = (chartTimestamp(points[index].day) - chartTimestamp(points[index-1].day)) / dayMs;
    if (Number.isFinite(gap) && gap > 0 && gap <= 45) gaps.push(gap);
  }
  gaps.sort((a,b)=>a-b);
  const p85 = gaps.length ? gaps[Math.min(gaps.length-1, Math.floor((gaps.length-1)*0.85))] : 1;
  const bySpan = Math.max(1, Math.ceil(spanDays / 520));
  return Math.max(1, Math.min(30, Math.ceil(Math.max(bySpan,p85))));
}

function resampleLongRangeUniform(values) {
  const source = sortedNumericPoints(filterSeriesToSelectedStart(values || {}));
  if (source.length < 2) return Object.fromEntries(source.map(item=>[item.day,item.value]));
  const stepDays = longRangeUniformStepDays(values), dayMs = 86400000, bucketMs = stepDays * dayMs;
  const firstMs = chartTimestamp(source[0].day);
  const origin = Math.floor(firstMs / dayMs) * dayMs;
  const buckets = new Map();
  for (const point of source) {
    const timestamp = chartTimestamp(point.day);
    if (!Number.isFinite(timestamp)) continue;
    const bucket = Math.floor((timestamp - origin) / bucketMs);
    const previous = buckets.get(bucket);
    if (!previous || timestamp >= previous.timestamp) buckets.set(bucket,{timestamp,value:point.value});
  }
  const result = {};
  for (const [bucket,item] of [...buckets.entries()].sort((a,b)=>a[0]-b[0])) {
    // Keep the representative close on its real observation day. Moving the
    // value to the synthetic bucket end visually shifts market moves in time.
    const key = new Date(item.timestamp).toISOString().slice(0,10);
    result[key] = item.value;
  }
  // Max must visibly begin at the oldest real cached market close, not at the
  // end of the first multi-day display bucket. This is only a boundary point;
  // the rest of the long chart stays uniformly compacted.
  if (state.historyRange === "max" && source.length) result[source[0].day] = source[0].value;
  return Object.fromEntries(Object.entries(result).sort((a,b)=>chartTimestamp(a[0])-chartTimestamp(b[0])));
}

function sortedNumericPoints(values) {
  if (values && typeof values === "object" && !Array.isArray(values)) {
    const cached = sortedNumericPointCache.get(values);
    if (cached) return cached;
  }
  const points = Object.entries(values || {})
    .map(([day,value]) => ({day,value:Number(value),time:seriesValuationTimestamp(day)}))
    .filter(item => Number.isFinite(item.time) && Number.isFinite(item.value))
    .sort((a,b) => a.time - b.time);
  if (values && typeof values === "object" && !Array.isArray(values)) sortedNumericPointCache.set(values,points);
  return points;
}
function periodContext(currency) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const cacheKey = derivedCacheKey("periodContext",selectedCurrency,state.historyRange);
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const values = analyticsValues(selectedCurrency), portfolio = sortedNumericPoints(values.portfolio), price = sortedNumericPoints(values.price);
  const source = portfolio.length >= 2 ? portfolio : price;
  const result = source.length < 2
    ? {values,days:[],startDay:null,endDay:null}
    : {values,days:source.map(item=>item.day),startDay:source[0].day,endDay:source.at(-1).day};
  derivedCache.set(cacheKey,result);
  return result;
}
function valueOnOrBeforePoints(points, when) {
  const target = typeof when === "number" ? when : chartTimestamp(when);
  if (!Number.isFinite(target) || !points?.length) return null;
  let low = 0, high = points.length - 1, found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (points[middle].time <= target) { found = middle; low = middle + 1; }
    else high = middle - 1;
  }
  return found >= 0 ? points[found].value : null;
}
function valueOnOrBefore(series, when) {
  return valueOnOrBeforePoints(sortedNumericPoints(series),when);
}

function entryExternalFlowWithMarketPrice(entry, currency, marketPrice) {
  const amount = Number(entry.amount_btc || 0), timestamp = String(entry.timestamp || "");
  if (!Number.isFinite(amount) || amount <= 0 || !Number.isFinite(chartTimestamp(timestamp))) return 0;
  const sameCurrency = String(entry.currency || "").toUpperCase() === String(currency || "").toUpperCase();
  const transactionPrice = Number(entry.price), fee = Math.max(0,Number(entry.fee || 0));
  if (entry.type === "purchase" || entry.type === "income") {
    if (sameCurrency && Number.isFinite(transactionPrice) && transactionPrice > 0) return amount * transactionPrice + (Number.isFinite(fee) ? fee : 0);
    return Number.isFinite(marketPrice) ? amount * marketPrice : 0;
  }
  if (entry.type === "sale") {
    if (sameCurrency && Number.isFinite(transactionPrice) && transactionPrice > 0) return -(amount * transactionPrice - (Number.isFinite(fee) ? fee : 0));
    return Number.isFinite(marketPrice) ? -(amount * marketPrice) : 0;
  }
  if (entry.type === "stack") return Number.isFinite(marketPrice) ? amount * marketPrice : 0;
  if (entry.type === "expense") {
    if (sameCurrency && Number.isFinite(transactionPrice) && transactionPrice > 0) return -(amount * transactionPrice - (Number.isFinite(fee) ? fee : 0));
    return Number.isFinite(marketPrice) ? -(amount * marketPrice) : 0;
  }
  return 0;
}
function entryExternalFlow(entry, currency, priceSeries) {
  const marketPrice = valueOnOrBefore(priceSeries,entry?.timestamp);
  return entryExternalFlowWithMarketPrice(entry,currency,marketPrice);
}
function externalFlowEvents(currency, priceSeries) {
  return performanceLedgerEvents(currency,priceSeries)
    .filter(item => Number.isFinite(item.externalFlow) && item.externalFlow !== 0)
    .map(item => ({time:item.time,flow:item.externalFlow,entry:item.entry,sequence:item.sequence}));
}
function performanceLedgerEvents(currency, priceSeries) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const cacheKey = derivedCacheKey("performanceLedgerEvents",selectedCurrency,state.historyRange);
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const pricePoints = sortedNumericPoints(priceSeries);
  const events = chartLedgerEntries().map((entry,sourceSequence) => {
    const time = chartTimestamp(entry?.timestamp), amount = Math.max(0,Number(entry?.amount_btc || 0));
    const kind = String(entry?.type || "");
    if (!Number.isFinite(time) || !(amount > 0) || !["purchase","income","stack","sale","expense","network_fee"].includes(kind)) return null;
    let btcDelta = ["purchase","income","stack"].includes(kind) ? amount : -amount;
    if(kind!=="network_fee" && entry?.fee_btc_affects_stack)btcDelta-=Math.max(0,Number(entry?.fee_btc||0));
    const sameCurrency = String(entry?.currency || "").toUpperCase() === selectedCurrency;
    const transactionPrice = Number(entry?.price);
    const marketPrice = valueOnOrBeforePoints(pricePoints,time);
    const valuationPrice = sameCurrency && ["purchase","income","sale","expense","network_fee"].includes(kind) && Number.isFinite(transactionPrice) && transactionPrice > 0
      ? transactionPrice
      : marketPrice;
    const externalFlow = entryExternalFlowWithMarketPrice(entry,selectedCurrency,marketPrice);
    return {time,btcDelta,externalFlow,valuationPrice,kind,entry,sourceSequence};
  }).filter(Boolean).sort((a,b)=>a.time-b.time || Number(["sale","expense","network_fee"].includes(a.kind))-Number(["sale","expense","network_fee"].includes(b.kind)) || a.sourceSequence-b.sourceSequence);
  const result = events.map((event,sequence)=>({...event,sequence}));
  derivedCache.set(cacheKey,result);
  return result;
}

function performancePricePoints(priceSeries) {
  return sortedNumericPoints(priceSeries).map(item => ({time:item.time,value:item.value,key:item.day}));
}
function twrAnalysis(currency) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const cacheKey = derivedCacheKey("twrAnalysis",selectedCurrency,state.historyRange);
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const context = periodContext(selectedCurrency), math = globalThis.BSTPerformanceMath;
  if (!math || !context.startDay) { derivedCache.set(cacheKey,null); return null; }
  const calculated = math.timeWeightedReturn(performancePricePoints(context.values.price),performanceLedgerEvents(selectedCurrency,context.values.price));
  if (!calculated) { derivedCache.set(cacheKey,null); return null; }
  const result = {
    percent: calculated.percent,
    index: calculated.index || {},
    startDay: Number.isFinite(calculated.startTime) ? new Date(calculated.startTime).toISOString() : context.startDay,
    endDay: Number.isFinite(calculated.endTime) ? new Date(calculated.endTime).toISOString() : context.endDay,
    calculatedDays: calculated.calculatedPeriods || 0,
    invalid: Boolean(calculated.invalid),
    reason: calculated.reason || null,
  };
  derivedCache.set(cacheKey,result);
  return result;
}

function xnpv(rate, flows) {
  const math = globalThis.BSTPerformanceMath;
  if (!math) return Number.NaN;
  return math.xnpv(rate,(flows || []).map(item=>({time:item.date instanceof Date?item.date.getTime():Number(item.time),amount:Number(item.amount)})));
}
function xirrSolveDetailed(flows) {
  const math = globalThis.BSTPerformanceMath;
  if (!math) return {rate:null,roots:[],ambiguous:false};
  return math.xirrSolveDetailed((flows || []).map(item=>({time:item.date instanceof Date?item.date.getTime():Number(item.time),amount:Number(item.amount)})));
}
function xirrSolve(flows) { return xirrSolveDetailed(flows).rate; }
function xirrAnalysis(currency) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const cacheKey = derivedCacheKey("xirrAnalysis",selectedCurrency,state.historyRange);
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const context=periodContext(selectedCurrency), portfolio=sortedNumericPoints(context.values.portfolio);
  if(portfolio.length<2){derivedCache.set(cacheKey,null);return null;}
  const start=portfolio[0],end=portfolio.at(-1),startTime=start.time,endTime=end.time,flows=[];
  if(!Number.isFinite(startTime)||!Number.isFinite(endTime)||endTime<=startTime){derivedCache.set(cacheKey,null);return null;}
  const fxRequired=chartLedgerEntries().some(entry=>{
    const time=chartTimestamp(entry?.timestamp),kind=String(entry?.type||""),entryCurrency=String(entry?.currency||"").toUpperCase();
    return Number.isFinite(time)&&time>startTime&&time<=endTime&&["purchase","income","sale","expense"].includes(kind)&&entryCurrency&&entryCurrency!==selectedCurrency;
  });
  if(fxRequired){const result={percent:null,startDay:start.day,endDay:end.day,flowCount:0,ambiguous:false,rootCount:0,reason:"fx_required"};derivedCache.set(cacheKey,result);return result;}
  if(start.value>0)flows.push({date:new Date(startTime),amount:-start.value});
  for(const event of externalFlowEvents(selectedCurrency,context.values.price)){
    if(event.time<=startTime||event.time>endTime)continue;
    flows.push({date:new Date(event.time),amount:-event.flow});
  }
  if(end.value>0)flows.push({date:new Date(endTime),amount:end.value});
  const solved=xirrSolveDetailed(flows);
  const result={percent:solved.rate===null?null:solved.rate*100,startDay:start.day,endDay:end.day,flowCount:flows.length,ambiguous:solved.ambiguous,rootCount:solved.roots.length};
  derivedCache.set(cacheKey,result);
  return result;
}

function cashflowAdjustedPortfolioChange(currency) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const cacheKey = derivedCacheKey("cashflowAdjustedPortfolioChange",selectedCurrency,state.historyRange);
  if (derivedCache.has(cacheKey)) return derivedCache.get(cacheKey);
  const context=periodContext(selectedCurrency), points=sortedNumericPoints(context.values.portfolio);
  if(points.length<2){derivedCache.set(cacheKey,null);return null;}
  const start=points[0],end=points.at(-1),startTime=start.time,endTime=end.time;
  const events=externalFlowEvents(selectedCurrency,context.values.price).filter(item=>item.time>startTime&&item.time<=endTime);
  const flow=events.reduce((sum,item)=>sum+item.flow,0);
  const absolute=end.value-start.value-flow;
  const twr=twrAnalysis(selectedCurrency);
  const result={startDay:start.day,endDay:end.day,start:start.value,end:end.value,absolute,percent:twr?.percent ?? null,externalFlow:flow};
  derivedCache.set(cacheKey,result);
  return result;
}

function maximumDrawdown(values) {
  const math = globalThis.BSTPerformanceMath;
  if (!math) return null;
  const result = math.maximumDrawdown(sortedNumericPoints(values).map(item=>({time:item.time,value:item.value,key:item.day})));
  if (!result) return null;
  return {
    current:result.current,maximum:result.maximum,
    peakDay:new Date(result.peakTime).toISOString(),troughDay:new Date(result.troughTime).toISOString(),
    periodPeakDay:new Date(result.periodPeakTime).toISOString(),endDay:new Date(result.endTime).toISOString(),
    daysSinceAth:Number(result.daysSincePeriodPeak||0),longestRecoveryDays:Number(result.longestRecoveryDays||0),
  };
}
function analysisCard(label,value,sub="",css="") {
  return `<article class="analysis-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong>${sub?`<small>${sub}</small>`:""}</article>`;
}
function renderReturnAnalytics(currency) {
  const element=$("#returnAnalytics");if(!element)return;
  const twr=twrAnalysis(currency),xirr=xirrAnalysis(currency),metric=state.data?.metrics?.currencies?.[String(currency||"").toUpperCase()]||{},cagr=metric.btc_cagr||{};
  const twrCss=(twr?.percent||0)>0?"positive":(twr?.percent||0)<0?"negative":"";
  const xirrCss=(xirr?.percent||0)>0?"positive":(xirr?.percent||0)<0?"negative":"";
  const cagrCss=(Number(cagr.percent)||0)>0?"positive":(Number(cagr.percent)||0)<0?"negative":"";
  const days=twr?.startDay&&twr?.endDay?Math.max(0,(chartTimestamp(twr.endDay)-chartTimestamp(twr.startDay))/86400000):0;
  const cagrSub=cagr.start_at?`${esc(fmtDate(cagr.start_at))} → ${esc(fmtDate(new Date().toISOString()))} · ${esc(t("btcCagrHint"))}`:esc(t("btcCagrHint"));
  element.innerHTML=`<div class="return-head"><div><span class="kicker">TWR · XIRR · CAGR</span><h3>${esc(t("trueReturn"))}</h3></div><small>${esc(t("twrHint"))}</small></div><div class="analysis-grid return-grid">${analysisCard(t("twrLong"),twr?.percent==null?t("unavailableReturn"):signedPercent(twr.percent),twr?`${esc(fmtDate(twr.startDay))} → ${esc(fmtDate(twr.endDay))}`:"",twrCss)}${analysisCard(t("xirrLong"),xirr?.ambiguous?t("ambiguousReturn"):(xirr?.percent==null?t("unavailableReturn"):signedPercent(xirr.percent)),xirr?.reason==="fx_required"?esc(t("xirrFxRequired")):`${esc(t("xirr"))}${days<30?` · ${esc(t("shortRangeXirr"))}`:""}`,xirrCss)}${analysisCard(t("btcCagr"),cagr.percent==null?t("unavailableReturn"):signedPercent(Number(cagr.percent)),cagrSub,cagrCss)}</div>`;
}
function purchasesForPeriod(currency) {
  const context=periodContext(currency);
  if(!context.startDay)return {all:[],matching:[],context};
  let startTime=chartTimestamp(context.startDay),endTime=chartTimestamp(context.endDay);
  if(state.historyRange==="first_purchase"){
    const first=chartLedgerEntries().filter(entry=>entry?.type==="purchase").map(entry=>chartTimestamp(entry?.timestamp)).filter(Number.isFinite).sort((a,b)=>a-b)[0];
    if(Number.isFinite(first))startTime=first;
  }
  const all=chartLedgerEntries().filter(entry=>{const time=chartTimestamp(entry?.timestamp);return entry.type==="purchase"&&Number.isFinite(time)&&time>=startTime&&time<=endTime;});
  return {all,matching:all.filter(entry=>String(entry.currency||"").toUpperCase()===currency),context};
}
function addPersonalYears(date, years) {
  const next = new Date(date.getTime());
  const month = next.getUTCMonth(), day = next.getUTCDate();
  next.setUTCFullYear(next.getUTCFullYear() + years);
  if (next.getUTCMonth() !== month) next.setUTCDate(0);
  else next.setUTCDate(day);
  return next;
}
function personalMonthsStarted(start, end) {
  if (!(start instanceof Date) || !(end instanceof Date) || end < start) return 0;
  let months = (end.getUTCFullYear() - start.getUTCFullYear()) * 12 + end.getUTCMonth() - start.getUTCMonth();
  const boundary = new Date(start.getTime());
  boundary.setUTCMonth(boundary.getUTCMonth() + months);
  if (boundary > end) months -= 1;
  return Math.max(1, months + 1);
}
function dcaPersonalYearCards(currency) {
  const entries = chartLedgerEntries().map(entry => ({...entry, time:new Date(entry.timestamp || "").getTime()})).filter(entry => Number.isFinite(entry.time)).sort((a,b)=>a.time-b.time);
  const purchases = entries.filter(entry => entry.type === "purchase" && String(entry.currency || "").toUpperCase() === currency);
  if (!purchases.length) return [];
  const start = new Date(purchases[0].time), now = new Date();
  const outlay = rows => rows.reduce((sum,entry) => {
    const amount=Number(entry.amount_btc||0),price=Number(entry.price||0),fee=Number(entry.fee||0);
    return sum + (Number.isFinite(amount)&&amount>0&&Number.isFinite(price)&&price>0 ? amount*price : 0) + (Number.isFinite(fee)&&fee>0 ? fee : 0);
  },0);
  const allInvested = outlay(purchases);
  const allMonths = personalMonthsStarted(start, now);
  const cards = [analysisCard(t("monthlySavingsOverall"), allMonths > 0 ? `${fmtFiat(allInvested / allMonths,currency)} ${t("perMonth")}` : "–", `${esc(fmtDate(start.toISOString()))} → ${esc(fmtDate(now.toISOString()))} · ${allMonths} ${esc(t("monthsCount"))}`)];
  let year = 1;
  while (year <= 100) {
    const periodStart = addPersonalYears(start, year - 1);
    if (periodStart > now) break;
    const nominalEnd = addPersonalYears(start, year);
    const periodEnd = nominalEnd < now ? nominalEnd : now;
    const rows = purchases.filter(entry => entry.time >= periodStart.getTime() && entry.time < nominalEnd.getTime());
    const invested = outlay(rows);
    const months = nominalEnd <= now ? 12 : personalMonthsStarted(periodStart, periodEnd);
    const label = `${year}. ${t("personalSavingsYear")}${nominalEnd > now ? ` · ${t("ongoing")}` : ""}`;
    const endLabel = nominalEnd <= now ? new Date(nominalEnd.getTime()-1).toISOString() : periodEnd.toISOString();
    const visiblePurchaseCount = state.discreet ? "***" : fmtNumber(rows.length,0);
    cards.push(analysisCard(label, months > 0 ? `${fmtFiat(invested / months,currency)} ${t("perMonth")}` : "–", `${esc(fmtDate(periodStart.toISOString()))} → ${esc(fmtDate(endLabel))} · ${esc(visiblePurchaseCount)} ${esc(t("purchasesInRange"))}`));
    year += 1;
  }
  return cards;
}

function effectivePurchaseUnitCost(entry) {
  const amount=Number(entry?.amount_btc||0),price=Number(entry?.price||0),fee=Math.max(0,Number(entry?.fee||0));
  if(!(amount>0)||!(price>0))return Number.POSITIVE_INFINITY;
  return (amount*price+(Number.isFinite(fee)?fee:0))/amount;
}
function renderDcaAnalytics(currency) {
  const element=$("#dcaAnalytics"),note=$("#dcaNote");if(!element)return;
  const {all,matching}=purchasesForPeriod(currency);
  if(!all.length){element.innerHTML=`<p class="storage-note">${esc(t("noPurchasesRange"))}</p>`;if(note)note.textContent="";return;}
  const totalBtc=all.reduce((sum,item)=>sum+Number(item.amount_btc||0),0);
  if(state.fiatFree){
    const cards=[analysisCard(t("purchaseCount"),fmtNumber(all.length,0)),analysisCard(t("acquiredStack"),fmtStack(totalBtc))];
    if(state.satsPerFiat&&matching.length){
      const gross=matching.reduce((sum,item)=>sum+Number(item.amount_btc||0)*Number(item.price||0),0),fees=matching.reduce((sum,item)=>sum+Number(item.fee||0),0),btc=matching.reduce((sum,item)=>sum+Number(item.amount_btc||0),0);
      const sorted=[...matching].sort((a,b)=>effectivePurchaseUnitCost(a)-effectivePurchaseUnitCost(b));
      cards.push(analysisCard(t("averageSatsPerFiat"),gross+fees>0?`${fmtNumber(btc*SATS_PER_BTC/(gross+fees),0)} sats/${currency}`:"–"));
      cards.push(analysisCard(t("bestPurchase"),fmtSatsPerFiat(effectivePurchaseUnitCost(sorted[0]),currency),esc(fmtDate(sorted[0].timestamp))));
      cards.push(analysisCard(t("worstPurchase"),fmtSatsPerFiat(effectivePurchaseUnitCost(sorted.at(-1)),currency),esc(fmtDate(sorted.at(-1).timestamp))));
    }
    element.innerHTML=cards.join("");if(note)note.textContent=all.length!==matching.length?t("differentCurrenciesOmitted"):"";return;
  }
  if(!matching.length){element.innerHTML=`<p class="storage-note">${esc(t("noPurchasesRange"))}</p>`;if(note)note.textContent=t("differentCurrenciesOmitted");return;}
  const btc=matching.reduce((sum,item)=>sum+Number(item.amount_btc||0),0),gross=matching.reduce((sum,item)=>sum+Number(item.amount_btc||0)*Number(item.price||0),0),fees=matching.reduce((sum,item)=>sum+Number(item.fee||0),0),invested=gross+fees;
  const sorted=[...matching].sort((a,b)=>effectivePurchaseUnitCost(a)-effectivePurchaseUnitCost(b)),best=sorted[0],worst=sorted.at(-1);
  element.innerHTML=[
    analysisCard(t("purchasesInRange"),fmtNumber(matching.length,0),privateHtml(fmtStack(btc))),
    analysisCard(t("weightedAveragePrice"),btc>0?fmtFiat(gross/btc,currency):"–"),
    analysisCard(t("averageSatsPerFiat"),invested>0?`${fmtNumber(btc*SATS_PER_BTC/invested,0)} sats/${currency}`:"–"),
    analysisCard(t("investedFiat"),fmtFiat(invested,currency)),
    analysisCard(t("feeRatio"),gross>0?`${fmtNumber(fees/gross*100,2)} %`:"–",privateHtml(fmtFiat(fees,currency))),
    analysisCard(t("breakEvenPrice"),btc>0?fmtFiat(invested/btc,currency):"–"),
    analysisCard(t("bestPurchase"),fmtFiat(effectivePurchaseUnitCost(best),currency),`${esc(fmtDate(best.timestamp))} · ${privateHtml(fmtStack(best.amount_btc))}`),
    analysisCard(t("worstPurchase"),fmtFiat(effectivePurchaseUnitCost(worst),currency),`${esc(fmtDate(worst.timestamp))} · ${privateHtml(fmtStack(worst.amount_btc))}`),
    ...dcaPersonalYearCards(currency)
  ].join("");
  if(note)note.textContent=all.length!==matching.length?t("differentCurrenciesOmitted"):"";
}
function drawdownCard(title,data) {
  if(!data)return analysisCard(title,t("unavailableReturn"));
  const css=data.maximum<0?"negative":"";
  return `<article class="drawdown-card"><span>${esc(title)}</span><div><small>${esc(t("periodHighDistance"))}</small><strong class="${data.current<0?"negative":""}">${privateHtml(signedPercent(data.current))}</strong></div><div><small>${esc(t("maximumDrawdown"))}</small><strong class="${css}">${privateHtml(signedPercent(data.maximum))}</strong></div><div><small>${esc(t("daysSinceAth"))}</small><strong>${privateHtml(fmtNumber(data.daysSinceAth||0,0))}</strong></div><div><small>${esc(t("longestRecovery"))}</small><strong>${privateHtml(`${fmtNumber(data.longestRecoveryDays||0,0)} d`)}</strong></div><small>${esc(t("peak"))}: ${esc(fmtDate(data.peakDay))} · ${esc(t("trough"))}: ${esc(fmtDate(data.troughDay))} · ${esc(t("completedRecoveryHint"))}</small></article>`;
}
function renderDrawdownAnalytics(currency) {
  const element=$("#drawdownAnalytics");if(!element)return;
  const context=periodContext(currency),twr=twrAnalysis(currency);
  element.innerHTML=drawdownCard(t("bitcoinDrawdown"),maximumDrawdown(context.values.price))+drawdownCard(t("portfolioDrawdown"),maximumDrawdown(twr?.index||{}));
}
function metricCurrency(currency){return state.data?.metrics?.currencies?.[String(currency||"").toUpperCase()]||{};}
function renderStackingVelocityAnalytics(){
  const element=$("#stackingVelocityAnalytics");if(!element)return;
  const metrics=state.data?.metrics?.stacking_speed||{};
  const card=(label,item)=>analysisCard(label,item?`${signedNumber(Number(item.avg_sats_per_day||0),0)} sats/${state.lang==="de"?"Tag":"day"}`:"–",item?`${esc(t("avgPerMonth"))}: ${privateHtml(`${signedNumber(Number(item.avg_sats_per_month||0),0)} sats`)}`:"");
  element.innerHTML=[card(t("last30Days"),metrics["30d"]),card(t("last365Days"),metrics["365d"]),card(t("sinceStart"),metrics.since_start)].join("");
}
function renderFeeAnalytics(currency){
  const element=$("#feeAnalytics");if(!element)return;
  const fees=metricCurrency(currency).fees||{};
  const btcSats=Number(fees.btc_sats||0),incomplete=Boolean(fees.btc_data_incomplete);
  const btcValue=btcSats>0?`${fmtNumber(btcSats,0)} sats`:(incomplete?"–":"0 sats");
  const btcHint=incomplete?t("btcFeeLegacyIncomplete"):t("btcFeeIncludesOnchain");
  const included=Number(fees.included_fiat||0),estimatedIncluded=Number(fees.included_estimated_fiat||0);
  const includedHint=included>0?` · ${esc(t("includedFees"))}: ${privateHtml(fmtFiat(included,currency))}${estimatedIncluded>0?` · ${esc(t("estimatedIncludedFees"))}: ${privateHtml(fmtFiat(estimatedIncluded,currency))}`:""}`:"";
  element.innerHTML=[
    analysisCard(t("totalFees"),fmtFiat(Number(fees.total_fiat_equivalent!=null?fees.total_fiat_equivalent:(fees.total_fiat||0)),currency),`${esc(t("feeRatio"))}: ${privateHtml(`${fmtNumber(Number(fees.ratio_percent||0),3)} %`)}${includedHint}`),
    analysisCard(t("btcFees"),btcValue,esc(btcHint)),
    analysisCard(t("purchaseFeeRate"),`${fmtNumber(Number(fees.purchase_ratio_percent||0),3)} %`,esc(t("weightedByVolume"))),
    analysisCard(t("dispositionFeeRate"),`${fmtNumber(Number(fees.disposition_ratio_percent||0),3)} %`,esc(t("weightedByVolume")))
  ].join("");
}
function renderHodlBenchmark(currency){
  const element=$("#hodlBenchmarkAnalytics");if(!element)return;
  const benchmark=metricCurrency(currency).hodl_benchmark||{};
  if(!benchmark.complete||!benchmark.valid){element.innerHTML=`<p class="storage-note">${esc(t("hodlUnavailableMixedFiat"))}</p>`;return;}
  const diff=Number(benchmark.difference_btc||0),pct=Number(benchmark.strategy_vs_hodl_percent||0),css=diff>0?"positive":diff<0?"negative":"";
  element.innerHTML=[
    analysisCard(t("yourStack"),fmtStack(Number(benchmark.actual_btc||0)),state.fiatFree?"":privateHtml(fmtFiat(Number(benchmark.actual_value||0),currency))),
    analysisCard(t("hodlStack"),fmtStack(Number(benchmark.benchmark_btc||0)),state.fiatFree?"":privateHtml(fmtFiat(Number(benchmark.benchmark_value||0),currency))),
    analysisCard(t("difference"),state.unit==="sats"?`${signedNumber(diff*SATS_PER_BTC,0)} sats`:`${signedNumber(diff,8)} BTC`,"",css),
    analysisCard(t("strategyVsHodl"),signedPercent(pct),esc(t("hodlBenchmarkHint")),css)
  ].join("");
}
function renderAdvancedAnalytics(currency){renderReturnAnalytics(currency);renderStackingVelocityAnalytics();renderFeeAnalytics(currency);renderHodlBenchmark(currency);renderDcaAnalytics(currency);renderDrawdownAnalytics(currency);}
function chartSeries(mode,currency){
  const cacheKey=derivedCacheKey("chartSeries",mode,currency,state.unit,state.lang,state.fiatFree?"fiat-free":"fiat",state.satsPerFiat?"sats-per-fiat":"plain");
  if(derivedCache.has(cacheKey))return derivedCache.get(cacheKey);
  const values=chartValues(currency),stack=Object.fromEntries(Object.entries(values.stackBtc).map(([day,value])=>[day,rawUnitValue(value)]));
  const stackSeries=(extra={})=>({key:"stack",label:`${t("stackHistory")} ${state.unit}`,unit:state.unit,values:stack,format:value=>state.unit==="sats"?`${fmtNumber(value,0)} sats`:`${fmtNumber(value,8)} BTC`,...extra});
  const marketScoreSeries=(extra={})=>({key:"market_assessment",label:`${t("marketAssessment")} · ${marketAssessmentSmoothingLabel()}`,unit:"score",values:chartMarketAssessmentOverlayValues(values.price),format:value=>`${fmtNumber(value,1)} / 100`,forceLinear:true,publicValue:true,...extra});
  if(state.fiatFree){
    const satsPrice=Object.fromEntries(Object.entries(values.price).filter(([,value])=>Number(value)>0).map(([day,value])=>[day,SATS_PER_BTC/Number(value)]));
    const satsSeries=(extra={})=>({key:"sats_per_fiat",label:`${t("satsPerFiat")} ${currency}`,unit:`sats/${currency}`,values:satsPrice,format:value=>`${fmtNumber(value,0)} sats/${currency}`,...extra});
    let result;
    if(!state.satsPerFiat)result=[stackSeries()];
    else {
      const options={price:[satsSeries()],stack:[stackSeries()],price_stack:[satsSeries(),stackSeries({secondary:true})],price_market:[satsSeries(),marketScoreSeries({secondary:true})]};
      result=options[mode]||options.price_stack;
    }
    derivedCache.set(cacheKey,result);
    return result;
  }
  const fiat=(key,label,seriesValues,extra={})=>({key,label:`${label} ${currency}`,unit:currency,values:seriesValues,format:value=>fmtFiat(value,currency),...extra});
  const pnl=(extra={})=>fiat("pnl",t("profitLossHistory"),values.totalProfitLoss,{allowNegative:true,...extra});
  const unrealized=(extra={})=>fiat("unrealized_pnl",t("unrealizedProfitLoss"),values.unrealizedProfitLoss,{allowNegative:true,...extra});
  const options={price:[fiat("price",t("btcPrice"),values.price)],portfolio:[fiat("portfolio",t("portfolioValue"),values.portfolio)],stack:[stackSeries()],pnl:[pnl()],price_portfolio:[fiat("price",t("btcPrice"),values.price),fiat("portfolio",t("portfolioValue"),values.portfolio,{secondary:true})],price_stack:[fiat("price",t("btcPrice"),values.price),stackSeries({secondary:true})],price_market:[fiat("price",t("btcPrice"),values.price),marketScoreSeries({secondary:true})],price_pnl:[fiat("price",t("btcPrice"),values.price),pnl({secondary:true})],portfolio_pnl:[fiat("portfolio",t("portfolioValue"),values.portfolio),pnl({secondary:true})],cost_pnl:[fiat("cost",t("openCostBasis"),values.costBasis,{step:true}),unrealized({secondary:true})]};
  const result=options[mode]||options.price;
  derivedCache.set(cacheKey,result);
  return result;
}
function currentProfitMetrics(currency){
  const metric=metricCurrency(currency),server=metric.profit||{};
  if(Object.keys(server).length){
    return {invested:Number(server.open_cost_basis||0),knownBtc:Number(server.known_btc||0),marketValue:server.market_value==null?null:Number(server.market_value),unrealized:server.unrealized==null?null:Number(server.unrealized),realized:Number(server.realized||0),total:server.total==null?null:Number(server.total),cumulativePurchaseOutlay:Number(metric.purchase_outlay||0),netInvested:Number(metric.net_invested_fiat||0)};
  }
  const fifo=state.data?.fifo||{},livePrice=Number(state.data?.prices?.[currency]);
  const summary=fifo.currency_summaries?.[String(currency).toUpperCase()]||{};
  const invested=Number(summary.invested||0),knownBtc=Number(summary.known_btc||0);
  const marketValue=Number.isFinite(livePrice)?knownBtc*livePrice:null;
  const unrealized=Number.isFinite(marketValue)?marketValue-invested:null;
  const realized=Number(summary.realized_gain ?? fifo.realized?.[currency] ?? 0);
  const total=Number.isFinite(unrealized)?unrealized+realized:realized;
  const secured=lifetimeFiatSecured(currency);
  const cumulativePurchaseOutlay=Number(secured.totalOutlay||0);
  return {invested,knownBtc,marketValue,unrealized,realized,total,cumulativePurchaseOutlay,netInvested:cumulativePurchaseOutlay};
}
function renderPerformanceSummary(currency){
  const element=$("#performanceSummary");if(!element)return;
  const values=analyticsValues(currency),priceChange=seriesChange(values.price),stackChange=seriesChange(values.stackBtc);
  const rangeFooter=change=>change?`${esc(fmtDate(change.startDay))} → ${esc(fmtDate(change.endDay))}`:esc(t("comparisonUnavailable"));
  const twoMetricCard=(label,leftLabel,leftValue,rightLabel,rightValue,{css="",footer="",rightCss=css}={})=>`<article class="performance-card"><span>${esc(label)}</span><div class="performance-change"><div><small>${esc(leftLabel)}</small><strong class="${css}">${privateHtml(leftValue)}</strong></div><div><small>${esc(rightLabel)}</small><strong class="${rightCss}">${privateHtml(rightValue)}</strong></div></div>${footer?`<small>${footer}</small>`:""}</article>`;
  const unavailable=label=>`<article class="performance-card"><span>${esc(label)}</span><strong>–</strong><small>${esc(t("comparisonUnavailable"))}</small></article>`;
  const cards=[];

  if(state.fiatFree){
    if(state.satsPerFiat){
      const satsChange=seriesChange(Object.fromEntries(Object.entries(values.price).filter(([,v])=>Number(v)>0).map(([d,v])=>[d,SATS_PER_BTC/Number(v)])));
      if(satsChange){const css=satsChange.absolute>0?"positive":satsChange.absolute<0?"negative":"";cards.push(twoMetricCard(`${t("satsPerFiat")} ${currency}`,t("absoluteChange"),`${signedNumber(satsChange.absolute,0)} sats/${currency}`,t("percentageChange"),signedPercent(satsChange.percent),{css,footer:rangeFooter(satsChange)}));}
    }
    if(stackChange){
      cards.push(twoMetricCard(t("stackPerformance"),t("netStackChange"),state.unit==="sats"?`${signedNumber(stackChange.absolute*SATS_PER_BTC,0)} sats`:`${signedNumber(stackChange.absolute,8)} BTC`,t("endingBalance"),fmtStack(stackChange.end),{footer:rangeFooter(stackChange),rightCss:""}));
    }else cards.push(unavailable(t("stackPerformance")));
    element.innerHTML=cards.join("");renderAdvancedAnalytics(currency);return;
  }

  if(priceChange){const css=priceChange.absolute>0?"positive":priceChange.absolute<0?"negative":"";cards.push(twoMetricCard(t("bitcoinPerformance"),t("absoluteChange"),signedFiat(priceChange.absolute,currency),t("percentageChange"),signedPercent(priceChange.percent),{css,footer:rangeFooter(priceChange)}));}
  else cards.push(unavailable(t("bitcoinPerformance")));

  const portfolioChange=cashflowAdjustedPortfolioChange(currency);
  if(portfolioChange){const css=portfolioChange.absolute>0?"positive":portfolioChange.absolute<0?"negative":"";cards.push(twoMetricCard(t("portfolioPerformance"),t("cashflowAdjustedChange"),signedFiat(portfolioChange.absolute,currency),t("twr"),portfolioChange.percent==null?"–":signedPercent(portfolioChange.percent),{css,footer:rangeFooter(portfolioChange)}));}
  else cards.push(unavailable(t("portfolioPerformance")));

  if(stackChange)cards.push(twoMetricCard(t("stackPerformance"),t("netStackChange"),state.unit==="sats"?`${signedNumber(stackChange.absolute*SATS_PER_BTC,0)} sats`:`${signedNumber(stackChange.absolute,8)} BTC`,t("endingBalance"),fmtStack(stackChange.end),{footer:rangeFooter(stackChange),rightCss:""}));
  else cards.push(unavailable(t("stackPerformance")));

  const profit=currentProfitMetrics(currency),bookCss=(profit.unrealized||0)>0?"positive":(profit.unrealized||0)<0?"negative":"",realizedCss=profit.realized>0?"positive":profit.realized<0?"negative":"",totalCss=profit.total>0?"positive":profit.total<0?"negative":"";
  const bookPercent=profit.unrealized!=null&&profit.invested>0?profit.unrealized/profit.invested*100:null;
  cards.push(twoMetricCard(t("bookProfitLossPerformance"),t("currentProfitLoss"),fmtFiat(profit.unrealized,currency),t("onOpenCostBasis"),bookPercent==null?"–":signedPercent(bookPercent),{css:bookCss,footer:`${esc(t("unrealizedHint"))} · ${esc(t("openCostBasis"))}: ${privateHtml(fmtFiat(profit.invested,currency))}`}));
  cards.push(twoMetricCard(t("realizedProfitLossPerformance"),t("currentProfitLoss"),fmtFiat(profit.realized,currency),t("cumulativePurchaseOutlay"),fmtFiat(profit.cumulativePurchaseOutlay,currency),{css:realizedCss,rightCss:"",footer:esc(t("realizedHint"))}));
  cards.push(twoMetricCard(t("profitLossPerformance"),t("currentProfitLoss"),fmtFiat(profit.total,currency),t("netInvestedFiat"),fmtFiat(profit.netInvested,currency),{css:totalCss,rightCss:"",footer:`${esc(t("totalProfitHint"))} · ${esc(t("netInvestedFiatHint"))}`}));
  element.innerHTML=cards.join("");
  renderAdvancedAnalytics(currency);
}

function renderOverview(){
  const data=state.data,fifo=data.fifo||{},currency=currentCurrency(),rawPrice=data.prices?.[currency],total=Number(fifo.total_btc||0);
  const currencySummary=fifo.currency_summaries?.[String(currency).toUpperCase()]||{};
  if(state.fiatFree){
    const cards=[[t("totalStack"),fmtStack(total),state.unit==="BTC"?`${fmtNumber(total*SATS_PER_BTC,0)} sats`:`${fmtNumber(total,8)} BTC`,""],[t("longTerm"),fmtStack(fifo.long_term_btc||0),"",""],[t("shortTerm"),fmtStack(fifo.short_term_btc||0),"",""],state.satsPerFiat?[t("currentBtcPurchasingPower"),fmtSatsPerFiat(rawPrice,currency),currency,""]:[t("unknown"),fmtStack(fifo.unknown_btc||fifo.unknown_holding_btc||0),"",""]];
    $("#summaryCards").innerHTML=cards.map(([label,value,sub,css])=>`<article class="metric-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong><small>${privateHtml(sub)}</small></article>`).join("");
  }else{
    const value=rawPrice==null?null:total*Number(rawPrice);
    const invested=Number(currencySummary.invested||0),known=Number(currencySummary.known_btc||0);
    const unrealized=rawPrice==null?null:known*Number(rawPrice)-invested;
    const unrealizedPercent=unrealized!=null&&invested>0?unrealized/invested*100:null;
    const realized=Number(currencySummary.realized_gain ?? fifo.realized?.[currency] ?? 0);
    const secured=lifetimeFiatSecured(currency),activity=metricCurrency(currency).activity||{},sales=activity.sales||{},expenses=activity.expenses||{},income=activity.income||{},networkFees=activity.network_fees||{};
    const activityFees=item=>Number(item?.fees_fiat||0)+Number(item?.btc_fee_fiat||0),realizedTotal=Number(activity.realized_total??realized);
    const cards=[
      [t("totalStack"),fmtStack(total),state.unit==="BTC"?`${fmtNumber(total*SATS_PER_BTC,0)} sats`:`${fmtNumber(total,8)} BTC`,""],
      [t("totalValue"),fmtFiat(value,currency),`${fmtFiat(rawPrice,currency)} / BTC`,""],
      [t("openBasis"),fmtFiat(invested,currency),`${fmtStack(known)} · ${t("openBasisHint")}`,""],
      [t("unrealized"),fmtFiat(unrealized,currency),`${t("onOpenCostBasis")}: ${unrealizedPercent==null?"–":signedPercent(unrealizedPercent)} · ${t("realized")}: ${fmtFiat(realized,currency)}`,unrealized>0?"positive":unrealized<0?"negative":""],
      [t("realizedTotal"),fmtFiat(realizedTotal,currency),`${t("salesSummary")}: ${fmtFiat(Number(sales.realized||0),currency)} · ${t("expensesSummary")}: ${fmtFiat(Number(expenses.realized||0),currency)} · ${t("networkFeeEffect")}: ${fmtFiat(Number(networkFees.realized||0),currency)}`,realizedTotal>0?"positive":realizedTotal<0?"negative":""],
      [t("salesSummary"),fmtStack(Number(sales.btc||0)),`${t("saleProceeds")}: ${fmtFiat(Number(sales.value||0),currency)} · ${t("fee")}: ${fmtFiat(activityFees(sales),currency)} · ${t("realizedCategory")}: ${fmtFiat(Number(sales.realized||0),currency)}`,""],
      [t("expensesSummary"),fmtStack(Number(expenses.btc||0)),`${t("expenseValue")}: ${fmtFiat(Number(expenses.value||0),currency)} · ${t("fee")}: ${fmtFiat(activityFees(expenses),currency)} · ${t("realizedCategory")}: ${fmtFiat(Number(expenses.realized||0),currency)}`,""],
      [t("incomeSummary"),fmtStack(Number(income.btc||0)),`${t("incomeValue")}: ${fmtFiat(Number(income.value||0),currency)} · ${t("fee")}: ${fmtFiat(activityFees(income),currency)}`,""],
      [t("networkFeesSummary"),fmtStack(Number(networkFees.btc||0)),`${t("networkFeeValue")}: ${fmtFiat(Number(networkFees.value||0),currency)} · ${t("onchain")}: ${fmtStack(Number(networkFees.onchain_btc||0))} · ${t("lightning")}: ${fmtStack(Number(networkFees.lightning_btc||0))}`,""],
      [t("fiatSecured"),fmtFiat(secured.fiat,currency),`${t("purchaseFees")}: ${fmtFiat(secured.fees,currency)} · ${t("purchaseOutlay")}: ${fmtFiat(secured.totalOutlay,currency)}`,""]
    ];
    $("#summaryCards").innerHTML=cards.map(([label,value,sub,css])=>`<article class="metric-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong><small>${privateHtml(sub)}</small></article>`).join("");
  }
  $("#heroLong").textContent=privateText(fmtStack(fifo.long_term_btc));
  const nextGoal=state.discreet?null:(data.goals||[]).filter(goal=>Number(goal.remaining_btc)>0).sort((a,b)=>Number(a.remaining_btc)-Number(b.remaining_btc))[0];
  $("#heroGoal").textContent=state.discreet?"":(nextGoal?`${nextGoal.name}: ${privateText(fmtStack(nextGoal.remaining_btc))}`:"✓");
  $("#heroText").textContent=state.lang==="de"?`Lokales Bitcoin-Buch mit Käufen, Einnahmen, Verkäufen, Ausgaben und Netzwerkgebühren, depotweisem FIFO, ${data.tax_settings.long_term_days} Tagen Haltezeit-Regel und dauerhaft gespeichertem Tagesverlauf.`:`Local Bitcoin ledger with purchases, income, sales, expenses and network fees, per-depot FIFO, a ${data.tax_settings.long_term_days}-day holding rule, and durable daily history.`;
  renderBitcoinNetworkStrip();
  renderBuyOpportunity();
  if(dashboardSectionLoaded("chart")) renderChart();
  else {
    const chart=$("#chart"); if(chart)chart.innerHTML=`<p class="storage-note">${esc(t("loadingChart"))}</p>`;
    renderStackingVelocityAnalytics();renderFeeAnalytics(currency);renderHodlBenchmark(currency);
    for(const selector of ["#performanceSummary","#returnAnalytics","#dcaAnalytics","#drawdownAnalytics"]){const element=$(selector);if(element)element.innerHTML=`<p class="storage-note">${esc(t("loadingChart"))}</p>`;}
    void ensureDashboardSection("chart");
  }
  renderGoalCards();
}

function renderAggregateDepot(){
  const element=$("#aggregateDepotSummary");if(!element)return;
  const data=state.data||{},fifo=data.fifo||{},currency=currentCurrency(),totalBtc=Number(fifo.total_btc||0),livePrice=Number(data.prices?.[currency]),totalValue=Number.isFinite(livePrice)?totalBtc*livePrice:null,rangeLabel=$("#historyRange option:checked")?.textContent||t("selectedRange");
  if(!dashboardSectionLoaded("chart")){
    const cells=`<div><span>${esc(t("totalStack"))}</span><strong>${privateHtml(fmtStack(totalBtc))}</strong><small>${esc(t("longTerm"))}: ${privateHtml(fmtStack(fifo.long_term_btc||0))} · ${esc(t("shortTerm"))}: ${privateHtml(fmtStack(fifo.short_term_btc||0))}</small></div>${state.fiatFree?"":`<div><span>${esc(t("totalValue"))}</span><strong>${privateHtml(fmtFiat(totalValue,currency))}</strong><small>${privateHtml(fmtFiat(livePrice,currency))} / BTC</small></div>`}<div><span>${esc(t("rangePerformance"))}</span><strong>–</strong><small>${esc(t("loadingChart"))}</small></div>`;
    element.innerHTML=`<article class="aggregate-depot-card"><div class="aggregate-depot-head"><div><span class="kicker">${esc(t("allDepotsCombined"))}</span><h3>${esc(t("totalDepot"))}</h3></div><span class="badge">${esc(rangeLabel)}</span></div><div class="aggregate-depot-grid">${cells}</div></article>`;
    void ensureDashboardSection("chart");
    return;
  }
  const values=chartValues(currency),stackChange=seriesChange(values.stackBtc),stackCss=stackChange?.absolute>0?"positive":stackChange?.absolute<0?"negative":"",stackPerformance=stackChange?`${state.unit==="sats"?`${signedNumber(stackChange.absolute*SATS_PER_BTC,0)} sats`:`${signedNumber(stackChange.absolute,8)} BTC`} · ${signedPercent(stackChange.percent)}`:"–";
  let cells=`<div><span>${esc(t("totalStack"))}</span><strong>${privateHtml(fmtStack(totalBtc))}</strong><small>${esc(t("longTerm"))}: ${privateHtml(fmtStack(fifo.long_term_btc||0))} · ${esc(t("shortTerm"))}: ${privateHtml(fmtStack(fifo.short_term_btc||0))}</small></div>`;
  if(state.fiatFree){const twr=twrAnalysis(currency);cells+=`<div><span>${esc(t("twrLong"))}</span><strong class="${(twr?.percent||0)>0?"positive":(twr?.percent||0)<0?"negative":""}">${privateHtml(twr?.percent==null?"–":signedPercent(twr.percent))}</strong><small>${esc(t("cashflowAdjusted"))}</small></div>`;}else{const portfolioChange=cashflowAdjustedPortfolioChange(currency),portfolioCss=portfolioChange?.absolute>0?"positive":portfolioChange?.absolute<0?"negative":"",portfolioPerformance=portfolioChange?`${signedFiat(portfolioChange.absolute,currency)} · ${portfolioChange.percent==null?"–":signedPercent(portfolioChange.percent)}`:"–";cells+=`<div><span>${esc(t("totalValue"))}</span><strong>${privateHtml(fmtFiat(totalValue,currency))}</strong><small>${privateHtml(fmtFiat(livePrice,currency))} / BTC</small></div><div><span>${esc(t("rangePerformance"))}</span><strong class="${portfolioCss}">${privateHtml(portfolioPerformance)}</strong><small>${portfolioChange?`${esc(fmtDate(portfolioChange.startDay))} → ${esc(fmtDate(portfolioChange.endDay))}`:esc(t("comparisonUnavailable"))}</small></div>`;}
  cells+=`<div><span>${esc(t("stackChange"))}</span><strong class="${stackCss}">${privateHtml(stackPerformance)}</strong><small>${stackChange?`${esc(fmtDate(stackChange.startDay))} → ${esc(fmtDate(stackChange.endDay))}`:esc(t("comparisonUnavailable"))}</small></div>`;
  element.innerHTML=`<article class="aggregate-depot-card"><div class="aggregate-depot-head"><div><span class="kicker">${esc(t("allDepotsCombined"))}</span><h3>${esc(t("totalDepot"))}</h3></div><span class="badge">${esc(rangeLabel)}</span></div><div class="aggregate-depot-grid">${cells}</div></article>`;
}
function renderAll(){
  applyStaticSelects();
  updateFiatFreeChartOptions();
  const discreetToggle=$("#discreetMode"),fiatToggle=$("#fiatFreeMode"),satsToggle=$("#satsPerFiatMode");
  if(discreetToggle)discreetToggle.checked=state.discreet;
  if(fiatToggle)fiatToggle.checked=state.fiatFree;
  if(satsToggle){satsToggle.checked=state.satsPerFiat;satsToggle.disabled=!state.fiatFree;}
  updateDiscreetUi();
  const taxNote=String(state.data.tax_settings.note||"").trim();
  $("#taxDisclaimer").textContent=taxNote?`${taxNote} · ${t("holdingDisclaimer")}`:t("holdingDisclaimer");
  $("#taxForm").long_term_days.value=state.data.tax_settings.long_term_days||365;
  $("#taxForm").tax_note.value=state.data.tax_settings.note||"";
  // Do not rebuild every hidden tab after each save, unit toggle or refresh.
  // Large ledger/FIFO tables and analytics are rendered only when visible.
  renderActiveTabContent(state.activeTab);
}
function backupAgeLabel(timestamp,age){return timestamp?`${fmtDateTime(timestamp)} · ${fmtNumber(age,0)} ${t("daysUnit")}`:t("never");}
function renderBackupHealth(){
  const element=$("#backupHealthStatus"),block=element?.closest(".backup-health-block");if(!element||!block)return;const owner=Boolean(state.data?.security?.owner);block.classList.toggle("hidden",!owner);if(!owner)return;
  const health=state.backupHealth;if(!health){element.innerHTML=`<p class="storage-note">${esc(state.backupHealthLoading?t("checking"):t("never"))}</p>`;return;}
  const backupClass=health.backup_stale?"negative":"positive",testClass=health.restore_test_due?"negative":"positive";
  element.innerHTML=`<article class="backup-health-card"><span>${esc(t("lastEncryptedBackup"))}</span><strong class="${backupClass}">${esc(health.backup_stale?t("backupStale"):t("backupHealthy"))}</strong><small>${esc(backupAgeLabel(health.last_backup_at,health.backup_age_days))}</small></article><article class="backup-health-card"><span>${esc(t("lastRestoreTest"))}</span><strong class="${testClass}">${esc(health.restore_test_due?t("restoreTestDue"):t("restoreTestCurrent"))}</strong><small>${esc(backupAgeLabel(health.last_restore_test_at,health.restore_test_age_days))}</small></article>`;
  $("#backupWarningDays").value=String(health.backup_warning_days||30);$("#restoreTestWarningDays").value=String(health.restore_test_warning_days||180);
}
async function loadBackupHealth(){
  if(!state.entryId||!state.data?.security?.owner){state.backupHealth=null;renderBackupHealth();return;}state.backupHealthLoading=true;renderBackupHealth();try{state.backupHealth=await api(`api/backup-health?entry_id=${encodeURIComponent(state.entryId)}`,{timeoutMs:7000});}catch(error){state.backupHealth={backup_stale:true,restore_test_due:true,last_error:error.message||String(error)};}finally{state.backupHealthLoading=false;renderBackupHealth();}
}
async function saveBackupHealthSettings(){const button=$("#saveBackupHealth"),result=$("#backupHealthResult");button.disabled=true;try{state.backupHealth=await api("api/backup-health/settings",{method:"POST",body:JSON.stringify({entry_id:state.entryId,backup_warning_days:Number($("#backupWarningDays").value),restore_test_warning_days:Number($("#restoreTestWarningDays").value)})});renderBackupHealth();result.textContent=t("backupHealthSaved");result.className="result positive";}catch(error){result.textContent=error.message||String(error);result.className="result negative";}finally{button.disabled=false;}}
async function markRestoreTest(){const button=$("#markRestoreTest"),result=$("#backupHealthResult");button.disabled=true;try{state.backupHealth=await api("api/backup-health/mark-restore-test",{method:"POST",body:JSON.stringify({entry_id:state.entryId})});renderBackupHealth();result.textContent=t("restoreTestMarked");result.className="result positive";}catch(error){result.textContent=error.message||String(error);result.className="result negative";}finally{button.disabled=false;}}


function walletWatchLang(de,en){return state.lang==="de"?de:en;}
function walletWatchPanelStorageKey(){return `bst_walletwatch_panel_state:${state.entryId||"default"}`;}
function walletWatchPanelPreferences(){try{const parsed=JSON.parse(localStorage.getItem(walletWatchPanelStorageKey())||"{}");return parsed&&typeof parsed==="object"&&!Array.isArray(parsed)?parsed:{};}catch(_error){return {};}}
function setWalletWatchPanelCollapsed(panel,collapsed,{persist=false}={}){
  if(!panel)return;const body=panel.querySelector(":scope > .sats-sentinel-panel-body"),button=panel.querySelector(":scope > .panel-head .sats-sentinel-panel-toggle"),isCollapsed=Boolean(collapsed);panel.classList.toggle("is-collapsed",isCollapsed);if(body)body.hidden=isCollapsed;if(button){button.setAttribute("aria-expanded",String(!isCollapsed));button.innerHTML=`<span aria-hidden="true">${isCollapsed?"▸":"▾"}</span><span>${esc(walletWatchLang(isCollapsed?"Einblenden":"Ausblenden",isCollapsed?"Show":"Hide"))}</span>`;button.title=walletWatchLang(isCollapsed?"Bereich einblenden":"Bereich ausblenden",isCollapsed?"Show section":"Hide section");}
  if(persist){const prefs=walletWatchPanelPreferences(),key=String(panel.dataset.sentinelPanel||"");if(key){prefs[key]=isCollapsed;localStorage.setItem(walletWatchPanelStorageKey(),JSON.stringify(prefs));}}
}
function initWalletWatchPanelToggles(){
  const prefs=walletWatchPanelPreferences();
  for(const panel of $$("#tab-walletwatch > .panel[data-sentinel-panel]")){
    const head=panel.querySelector(":scope > .panel-head");if(!head)continue;
    let body=panel.querySelector(":scope > .sats-sentinel-panel-body");
    if(!body){const nodes=[...panel.childNodes].filter(node=>node!==head);body=document.createElement("div");body.className="sats-sentinel-panel-body";for(const node of nodes)body.appendChild(node);panel.appendChild(body);}
    let button=head.querySelector(".sats-sentinel-panel-toggle");
    if(!button){button=document.createElement("button");button.type="button";button.className="ghost compact sats-sentinel-panel-toggle";button.addEventListener("click",event=>{event.preventDefault();event.stopPropagation();setWalletWatchPanelCollapsed(panel,!panel.classList.contains("is-collapsed"),{persist:true});});head.appendChild(button);}
    const key=String(panel.dataset.sentinelPanel||""),fallback=panel.dataset.sentinelDefault==="collapsed",collapsed=Object.prototype.hasOwnProperty.call(prefs,key)?Boolean(prefs[key]):fallback;setWalletWatchPanelCollapsed(panel,collapsed);
  }
}
function walletWatchConfig(){return state.walletWatch?.config || {enabled:false,poll_interval_seconds:60,query_source:"auto",electrum_kind:"fulcrum",electrum_host:"",electrum_port:50001,electrum_tls:false,electrum_verify_ssl:true,electrum_pinned_cert_pem:"",allow_public_tor:false,persistent_notification:true,notification_detail:"discreet",notification_services:[],notification_targets:[],log_display_mode:"days",log_display_count:100,log_display_days:30,monitors:[]};}
function maskWalletWatchValue(value){const raw=String(value||"");if(state.discreet)return "••••";if(raw.length<=22)return raw;return `${raw.slice(0,10)}…${raw.slice(-8)}`;}
function walletWatchCard(label,value,hint="",css=""){return `<article class="sats-sentinel-card"><div class="sats-sentinel-card-label">${esc(label)}</div><div class="sats-sentinel-card-value ${esc(css)}">${esc(value)}</div>${hint?`<div class="sats-sentinel-card-hint">${esc(hint)}</div>`:""}</article>`;}
function walletWatchErrorText(raw){const value=String(raw||"");if(!value)return "";if(value.includes("No Sats Sentinel mempool source is available"))return walletWatchLang("Keine Sats-Sentinel-Datenquelle verfügbar. Konfiguriere eine eigene/custom Mempool-Node oder – nur wenn keine eigene Node existiert – eine öffentliche Mempool-Quelle und erlaube deren Nutzung über Tor.","No Sats Sentinel data source is available. Configure an own/custom mempool node or, only when no own node exists, configure a public mempool source and allow its use through Tor.");if(value.includes("enabled but no addresses"))return walletWatchLang("Sats Sentinel ist aktiv, aber es ist noch keine Adresse zur Überwachung eingerichtet.","Sats Sentinel is active, but no address is configured for monitoring yet.");if(value.includes("source unavailable")||value.includes("poll failed"))return walletWatchLang("Die konfigurierte Sats-Sentinel-Datenquelle ist nicht erreichbar. Bei einer eigenen/custom Node gibt es absichtlich keinen Provider-Fallback.","The configured Sats Sentinel data source is unavailable. With an own/custom node there is intentionally no provider fallback.");if(value.includes("Encrypted Sats Sentinel cache could not be opened"))return walletWatchLang("Der verschlüsselte Sats-Sentinel-Cache konnte nicht geöffnet werden.","The encrypted Sats Sentinel cache could not be opened.");return value;}
function walletWatchCategoryLabel(value){const labels={own:walletWatchLang("Eigene Adresse","Own address"),exchange:"Exchange",interesting:walletWatchLang("Interessant","Interesting"),incident:walletWatchLang("Hacker / Incident","Hacker / incident"),other:walletWatchLang("Sonstige","Other")};return labels[String(value||"other")]||labels.other;}
function walletWatchShortAddress(value){const raw=String(value||"");if(state.discreet)return "••••";if(raw.length<=24)return raw;return `${raw.slice(0,10)}…${raw.slice(-8)}`;}
function walletWatchRouteText(st){
  const label=String(st.selected_source_label||"");
  if(label){const tor=st.selected_source_route==="tor",pin=Boolean(st.electrum_certificate_pinned);return {value:`${label}${tor?" · Tor":" · Direkt"}${pin?" · TLS-Pin":""}`,hint:walletWatchLang(pin?"Das präsentierte Fulcrum-/Electrum-Zertifikat wird exakt per SHA-256-Pin geprüft. Die explizite Quelle bleibt Fail Closed; es gibt keinen heimlichen Provider-Wechsel.":"Die Abfragequelle wurde aus der Sentinel-Konfiguration gewählt. Eine explizite Auswahl bleibt bei Fehlern Fail Closed; es gibt keinen heimlichen Provider-Wechsel.",pin?"The presented Fulcrum/Electrum certificate is verified by an exact SHA-256 pin. The explicit source remains fail-closed; there is no hidden provider switch.":"The query source was selected from Sentinel configuration. An explicit selection stays fail-closed on errors; there is no hidden provider switch.")};}
  return {value:walletWatchLang("Fail Closed","Fail closed"),hint:walletWatchLang("Für die gewählte Einstellung ist keine erlaubte Datenquelle konfiguriert.","No allowed data source is configured for the selected setting.")};
}
function renderWalletWatchStatusOnly(){
  const statusBox=$("#walletWatchStatus"),privacy=$("#walletWatchPrivacy"),errorBox=$("#walletWatchError"),badge=$("#walletWatchBadge");
  if(!statusBox||!privacy)return;
  if(state.walletWatchLoading && !state.walletWatch){statusBox.innerHTML=`<p class="storage-note">${esc(walletWatchLang("Sats Sentinel wird geladen …","Loading Sats Sentinel …"))}</p>`;return;}
  if(!state.walletWatch){statusBox.innerHTML=`<p class="storage-note">${esc(walletWatchLang("Noch nicht geladen.","Not loaded yet."))}</p>`;return;}
  const st=state.walletWatch.status||{};
  const partialWarning=Boolean(st.enabled&&!st.last_error&&st.last_warning);if(badge){badge.textContent=st.enabled?(st.last_error?"⚠ OFFLINE":partialWarning?"⚠ TEILWEISE":"● AKTIV"):"AUS";badge.classList.toggle("positive",Boolean(st.enabled&&!st.last_error&&!partialWarning));badge.classList.toggle("negative",Boolean(st.enabled&&st.last_error));badge.classList.toggle("warning",partialWarning);}
  const addressCount=Number(st.address_count||0),addressHint=state.discreet?"••••":`${addressCount} ${walletWatchLang(addressCount===1?"Adresse":"Adressen",addressCount===1?"address":"addresses")}`;
  statusBox.innerHTML=[
    walletWatchCard(walletWatchLang("Überwachung","Monitoring"),st.enabled?walletWatchLang("Aktiv","Active"):walletWatchLang("Aus","Off"),addressHint,st.enabled&&!st.last_error?"positive":""),
    walletWatchCard("UTXOs",state.discreet?"••••":String(st.utxo_count||0),state.discreet?"••••":`${fmtNumber((Number(st.balance_sats)||0)/SATsFix(),8)} BTC`),
    walletWatchCard(walletWatchLang("Letzter erfolgreicher Check","Last successful check"),fmtDateTime(st.last_success_at),walletWatchLang("Zeitpunkt der letzten vollständig erfolgreichen Prüfung.","Time of the last fully successful check."),st.last_error?"negative":""),
    walletWatchCard(walletWatchLang("Letzter Versuch","Last attempt"),fmtDateTime(st.last_poll_at),walletWatchLang("Wird live alle 15 Sekunden aus dem lokalen HA-Status aktualisiert; erzeugt keine zusätzliche Blockchain-Abfrage.","Refreshed locally from HA every 15 seconds; does not trigger an extra blockchain request.")),
    walletWatchCard(walletWatchLang("Letzte erkannte Bewegung","Last detected movement"),fmtDateTime(st.last_activity_at),walletWatchLang("Zeitpunkt, zu dem Sentinel zuletzt eine neue Bewegung erkannt und ins verschlüsselte Journal geschrieben hat.","Time when Sentinel last detected a new movement and wrote it to the encrypted journal."),st.last_activity_at?"positive":""),
    walletWatchCard(walletWatchLang("Baseline","Baseline"),st.baseline_complete?walletWatchLang("Fertig","Ready"):walletWatchLang("Wird aufgebaut","Building"),walletWatchLang("Bestehende Historie löst beim ersten Einlesen keinen Fehlalarm aus.","Existing history does not trigger alerts on first baseline."),st.baseline_complete?"positive":"")
  ].join("");
  if(errorBox){const isOffline=Boolean(st.last_error),raw=isOffline?st.last_error:st.last_warning,message=isOffline?walletWatchErrorText(raw):walletWatchLang("Die Node ist erreichbar, aber mindestens eine Adress-/TX-Prüfung war unvollständig. Andere Watch-Einträge werden weiter geprüft; die betroffene Adresse wird beim nächsten Poll erneut versucht.","The node is reachable, but at least one address/transaction check was incomplete. Other watch targets continue to be checked; the affected address is retried on the next poll."),technical=(!state.discreet&&raw)?`<small>${esc(walletWatchLang("Technik","Technical"))}: ${esc(String(raw))}</small>`:"";errorBox.classList.toggle("hidden",!raw);errorBox.classList.toggle("warning",Boolean(raw&&!isOffline));errorBox.innerHTML=raw?`<strong>${esc(isOffline?walletWatchLang("Sats Sentinel offline","Sats Sentinel offline"):walletWatchLang("Teilprüfung · Node online","Partial check · node online"))}</strong><span>${esc(message)}</span>${technical}`:"";}
  const route=walletWatchRouteText(st);
  privacy.innerHTML=[
    walletWatchCard("XPUB im Hintergrund",(st.xpub_in_runtime??st.xpup_in_runtime)?"JA":"Nein",walletWatchLang("XPUB bleibt im Tresor.","XPUB remains in the vault."),(st.xpub_in_runtime??st.xpup_in_runtime)?"negative":"positive"),
    walletWatchCard("Descriptor im Hintergrund",st.descriptor_in_runtime?"JA":"Nein",walletWatchLang("Nur konkret abgeleitete Adressen werden überwacht.","Only concretely derived addresses are monitored."),st.descriptor_in_runtime?"negative":"positive"),
    walletWatchCard(walletWatchLang("Monitor-Cache","Monitor cache"),st.runtime_cache_encrypted?walletWatchLang("Verschlüsselt","Encrypted"):walletWatchLang("Unverschlüsselt","Unencrypted"),"AES-256-GCM · device-bound",st.runtime_cache_encrypted?"positive":"negative"),
    walletWatchCard(walletWatchLang("Historische TX-Übersicht","Historical TX overview"),st.historical_tx_overview_persisted?walletWatchLang("Gespeichert","Stored"):walletWatchLang("Nur RAM","RAM only"),walletWatchLang("Wird nicht in HA-Storage oder LocalStorage persistiert.","Not persisted to HA storage or LocalStorage."),st.historical_tx_overview_persisted?"negative":"positive"),
    walletWatchCard(walletWatchLang("Netzwerkregel","Network policy"),route.value,route.hint,st.selected_source_label?"positive":""),
    walletWatchCard(walletWatchLang("Externe Ziele","External targets"),String(st.external_notification_targets||0),st.last_notification_error?walletWatchErrorText(st.last_notification_error):walletWatchLang("Mehrere Ziele parallel möglich.","Multiple targets can run in parallel."),st.last_notification_error?"negative":"positive")
  ].join("");
}
function walletWatchMonitorRuntimeSummary(monitorId){
  const id=String(monitorId||""),st=state.walletWatch?.status||{},last=st.last_activity_by_monitor?.[id]||null,aggregate=st.monitor_summaries?.[id],overview=walletWatchTxOverviewState(id)?.data||null;
  const overviewBalance=overview&&Number.isFinite(Number(overview.balance_sats))?Number(overview.balance_sats):null;
  if(aggregate&&typeof aggregate==="object"){
    return {addresses:Number(aggregate.address_count||0),receive_addresses:Number(aggregate.receive_address_count||0),change_addresses:Number(aggregate.change_address_count||0),receive_used:Number(aggregate.receive_used_count||0),change_used:Number(aggregate.change_used_count||0),balance_sats:overviewBalance===null?Number(aggregate.balance_sats||0):overviewBalance,utxo_count:Number(aggregate.utxo_count||0),baseline_complete:Boolean(aggregate.baseline_complete),last_activity:last};
  }
  const addresses=Array.isArray(st.addresses)?st.addresses.filter(row=>String(row?.monitor_id||"")===id):[],receive=addresses.filter(row=>row?.branch==="receive"),change=addresses.filter(row=>row?.branch==="change");
  return {addresses:addresses.length,receive_addresses:receive.length,change_addresses:change.length,receive_used:receive.filter(row=>row?.used===true).length,change_used:change.filter(row=>row?.used===true).length,balance_sats:overviewBalance===null?addresses.reduce((sum,row)=>sum+Number(row?.balance_sats||0),0):overviewBalance,utxo_count:addresses.reduce((sum,row)=>sum+Number(row?.utxo_count||0),0),baseline_complete:addresses.length>0&&addresses.every(row=>Boolean(row?.baseline_complete)),last_activity:last};
}
function walletWatchDirectionBadge(direction,{compact=false}={}){const outgoing=String(direction||"")==="outgoing",label=outgoing?walletWatchLang("Ausgang","Outgoing"):walletWatchLang("Eingang","Incoming"),arrow=outgoing?"↑":"↓";return `<span class="sats-sentinel-direction-badge ${outgoing?"outgoing":"incoming"} ${compact?"compact":""}"><span aria-hidden="true">${arrow}</span>${esc(label)}</span>`;}
function walletWatchLastDetectedHtml(last){if(!last?.detected_at)return `<strong>${esc(walletWatchLang("Noch keine Sentinel-Bewegung","No Sentinel movement yet"))}</strong><small>${esc(walletWatchLang("Historische TX zählen hier nicht.","Historical TX do not count here."))}</small>`;const amount=state.discreet?"••••":walletWatchTxAmount(last.amount_sats),direction=String(last.direction||"");return `${walletWatchDirectionBadge(direction,{compact:true})}<strong>${esc(fmtDateTime(last.detected_at))}</strong><small>${esc(walletWatchLang("Von Sentinel erkannt","Detected by Sentinel"))}${state.discreet?"":` · ${esc(amount)}`}</small>`;}
function walletWatchTxOverviewState(id){return state.walletWatchTxOverviews?.[String(id||"")]||null;}
function walletWatchTxAmount(value){return state.discreet?"••••":`${fmtNumber(Number(value||0)/SATsFix(),8)} BTC`;}
function walletWatchTxOverviewLinkTx(item,overview){return walletWatchTxLink(item,{explorer_base_url:overview?.explorer_base_url||""});}
function walletWatchTxOverviewCounterparties(item,overview){const cps=Array.isArray(item?.counterparties)?item.counterparties:[];if(!cps.length)return `<span class="storage-note">${esc(walletWatchLang("Keine externe Gegenadresse erkannt","No external counterparty detected"))}</span>`;return cps.slice(0,3).map(cp=>walletWatchPartyHtml({address:String(cp.address||"")},{explorer_base_url:overview?.explorer_base_url||""},{amountSats:Number(cp.value_sats||0),compact:true})).join("");}
function renderWalletWatchTxOverview(monitorId){
  const id=String(monitorId||""),host=document.querySelector(`[data-wallet-watch-tx-host="${CSS.escape(id)}"]`);if(!host)return;
  const stateRow=walletWatchTxOverviewState(id);if(!stateRow){host.innerHTML=`<p class="storage-note">${esc(walletWatchLang("Beim Aufklappen werden die historischen Transaktionen frisch von der gewählten Sentinel-Quelle geladen.","Opening this section loads historical transactions fresh from the selected Sentinel source."))}</p>`;return;}
  if(stateRow.loading){host.innerHTML=`<p class="storage-note">${esc(walletWatchLang("Transaktionen werden geladen …","Loading transactions …"))}</p>`;return;}
  if(stateRow.error){host.innerHTML=`<div class="result negative">${esc(stateRow.error)}</div><button type="button" class="secondary compact wallet-watch-tx-reload" data-id="${esc(id)}">${esc(walletWatchLang("Erneut laden","Retry"))}</button>`;host.querySelector('.wallet-watch-tx-reload')?.addEventListener('click',()=>void loadWalletWatchTransactions(id,{force:true}));return;}
  const overview=stateRow.data||{},items=Array.isArray(overview.transactions)?overview.transactions:[];
  const summary=`<div class="sats-sentinel-tx-summary"><div><span>${esc(walletWatchLang("Aktueller Wallet-Bestand","Current wallet balance"))}</span><strong>${esc(walletWatchTxAmount(overview.balance_sats))}</strong><small>${esc(walletWatchLang(`${Number(overview.derived_address_count||0)} Adresse(n) erfasst`,`${Number(overview.derived_address_count||0)} address(es) covered`))}</small></div><div><span>${esc(walletWatchLang("Geladene TX","Loaded TX"))}</span><strong>${esc(String(overview.loaded_transaction_count||0))}${Number(overview.known_transaction_count||0)>Number(overview.loaded_transaction_count||0)?` / ${esc(String(overview.known_transaction_count))}`:""}</strong></div><div><span>${esc(walletWatchLang("Wallet-Eingänge · geladen","Wallet incoming · loaded"))}</span><strong>${esc(walletWatchTxAmount(overview.loaded_in_sats))}</strong></div><div><span>${esc(walletWatchLang("Wallet-Ausgänge · geladen","Wallet outgoing · loaded"))}</span><strong>${esc(walletWatchTxAmount(overview.loaded_out_sats))}</strong></div><div><span>${esc(walletWatchLang("TX-Inputs · geladen","TX inputs · loaded"))}</span><strong>${esc(overview.loaded_tx_total_input_sats===null||overview.loaded_tx_total_input_sats===undefined?walletWatchLang("nicht vollständig","incomplete"):walletWatchTxAmount(overview.loaded_tx_total_input_sats))}</strong></div><div><span>${esc(walletWatchLang("TX-Outputs · geladen","TX outputs · loaded"))}</span><strong>${esc(walletWatchTxAmount(overview.loaded_tx_total_output_sats))}</strong></div><div><span>${esc(walletWatchLang("Fees · geladen","Fees · loaded"))}</span><strong>${esc(walletWatchTxAmount(overview.loaded_fee_sats))}</strong></div></div>`;
  const addressRows=Array.isArray(overview.address_balances)?overview.address_balances:[];const addressDetail=addressRows.length?`<details class="sats-sentinel-address-detail"><summary>${esc(walletWatchLang("Adressen & Einzelbestände","Addresses & individual balances"))} · ${esc(String(addressRows.length))}</summary><div class="sats-sentinel-address-list">${addressRows.map(row=>`<div><span>${state.discreet?"••••":walletWatchAddressLink(String(row.address||""),overview)}</span><small>${esc(row.branch||"")}${row.index===null||row.index===undefined?"":` #${esc(String(row.index))}`} · ${esc(String(row.utxo_count||0))} UTXO</small><strong>${esc(walletWatchTxAmount(row.balance_sats))}</strong></div>`).join("")}</div></details>`:"";
  const privacyNote=`<p class="storage-note sats-sentinel-tx-privacy">🔒 ${esc(walletWatchLang("Privat: XPUB/ZPUB/Descriptor liegen nur im Passwort-Tresor. Abgeleitete Adressen und Sentinel-Journal liegen AES-256-GCM-verschlüsselt im device-bound Cache. Diese historische TX-Übersicht wird nicht dauerhaft gespeichert.","Private: XPUB/ZPUB/descriptors live only in the password vault. Derived addresses and the Sentinel journal are AES-256-GCM encrypted in the device-bound cache. This historical TX overview is not persisted."))}</p>`;
  const rows=items.map(item=>{const outgoing=item.direction==="outgoing",direction=outgoing?walletWatchLang("Ausgang","Outgoing"):walletWatchLang("Eingang","Incoming"),sentinel=Boolean(item.sentinel_detected),when=item.confirmed?(item.block_time?fmtDateTime(new Date(Number(item.block_time)*1000).toISOString()):item.block_height?`Block ${item.block_height}`:walletWatchLang("Bestätigt","Confirmed")):walletWatchLang("Mempool","Mempool"),input=item.tx_total_input_sats===null||item.tx_total_input_sats===undefined?walletWatchLang("nicht vollständig","incomplete"):walletWatchTxAmount(item.tx_total_input_sats),output=walletWatchTxAmount(item.tx_total_output_sats),fee=item.fee_sats===null||item.fee_sats===undefined?"—":walletWatchTxAmount(item.fee_sats);return `<tr class="sats-sentinel-movement-row ${outgoing?"outgoing":"incoming"} ${sentinel?"sats-sentinel-tx-detected":""}"><td>${sentinel?`<span class="sats-sentinel-detected-badge">★ ${esc(walletWatchLang("SENTINEL ERKANNT","SENTINEL DETECTED"))}</span><small class="sats-sentinel-detected-time">${esc(walletWatchLang("Erkannt","Detected"))}: ${esc(fmtDateTime(item.sentinel_detected_at))}</small>`:""}<span>${esc(when)}</span></td><td class="sats-sentinel-tx-direction-cell">${walletWatchDirectionBadge(item.direction)}<small>${esc(walletWatchTxAmount(item.amount_sats))}</small></td><td>${walletWatchTxOverviewCounterparties(item,overview)}</td><td><span>${esc(walletWatchLang("Inputs","Inputs"))}: ${esc(input)}</span><br><span>${esc(walletWatchLang("Outputs","Outputs"))}: ${esc(output)}</span><br><small>Fee: ${esc(fee)}</small></td><td>${item.confirmed?esc(walletWatchLang("Bestätigt","Confirmed")):esc(walletWatchLang("Unbestätigt","Unconfirmed"))}${item.rbf?" · RBF":""}</td><td>${walletWatchTxOverviewLinkTx(item,overview)}</td></tr>`;}).join("");
  const warnings=Array.isArray(overview.warnings)&&overview.warnings.length?`<div class="result warning">${esc(overview.warnings.slice(0,3).join(" · "))}</div>`:"";
  const currentPage=Math.max(1,Number(overview.page||1)),pages=Math.max(1,Number(overview.pages||1)),unlimited=Boolean(overview.history_unlimited),hasMore=Boolean(overview.has_more);const pageNav=unlimited?`<div class="sats-sentinel-tx-pagination"><button type="button" class="secondary compact wallet-watch-tx-page-prev" ${currentPage<=1?"disabled":""}>‹ ${esc(walletWatchLang("Zurück","Previous"))}</button><span>${esc(pages>1?walletWatchLang(`Seite ${currentPage} von ${pages}`,`Page ${currentPage} of ${pages}`):walletWatchLang(`Seite ${currentPage}`,`Page ${currentPage}`))}</span><button type="button" class="secondary compact wallet-watch-tx-page-next" ${(!hasMore&&currentPage>=pages)?"disabled":""}>${esc(walletWatchLang("Weiter","Next"))} ›</button></div>`:"";
  host.innerHTML=`${summary}${addressDetail}${privacyNote}<div class="sats-sentinel-tx-overview-head"><small>${esc(walletWatchLang(`Quelle: ${overview.source_label||"?"} · ${overview.source_route==="tor"?"Tor":"Direkt"} · reine Übersicht, keine rückwirkenden Alarme`,`Source: ${overview.source_label||"?"} · ${overview.source_route==="tor"?"Tor":"Direct"} · overview only, no retroactive alerts`))}</small><button type="button" class="secondary compact wallet-watch-tx-reload" data-id="${esc(id)}">${esc(walletWatchLang("Aktualisieren","Refresh"))}</button></div>${warnings}${pageNav}<div class="table-scroll"><table class="sats-sentinel-tx-table"><thead><tr><th>${esc(walletWatchLang("Zeit","Time"))}</th><th>${esc(walletWatchLang("Richtung / Betrag","Direction / amount"))}</th><th>${esc(walletWatchLang("Gegenadresse","Counterparty"))}</th><th>${esc(walletWatchLang("Gesamte Transaktion","Whole transaction"))}</th><th>Status</th><th>TXID</th></tr></thead><tbody>${rows||`<tr><td colspan="6" class="storage-note">${esc(walletWatchLang("Keine Transaktionen für die aktuell abgeleiteten Adressen gefunden.","No transactions found for the currently derived addresses."))}</td></tr>`}</tbody></table></div>${pageNav}`;
  host.querySelector('.wallet-watch-tx-reload')?.addEventListener('click',()=>void loadWalletWatchTransactions(id,{force:true,page:currentPage}));
  host.querySelectorAll('.wallet-watch-tx-page-prev').forEach(btn=>btn.addEventListener('click',()=>void loadWalletWatchTransactions(id,{force:true,page:Math.max(1,currentPage-1)})));
  host.querySelectorAll('.wallet-watch-tx-page-next').forEach(btn=>btn.addEventListener('click',()=>void loadWalletWatchTransactions(id,{force:true,page:currentPage+1})));
}
async function loadWalletWatchTransactions(monitorId,{force=false,page=1}={}){
  const id=String(monitorId||"");if(!id||!state.entryId||state.data?.locked)return;const monitor=(walletWatchConfig().monitors||[]).find(item=>String(item.id||"")===id);if(!monitor)return;if(monitor._pending_save){toast(walletWatchLang("Watch-Eintrag zuerst speichern.","Save the watch entry first."));return;}const existing=walletWatchTxOverviewState(id);if(existing?.loading||(!force&&existing?.data&&Number(existing?.data?.page||1)===Number(page||1)))return;state.walletWatchTxOverviews[id]={loading:true,error:"",data:existing?.data||null};renderWalletWatchTxOverview(id);try{const rawLimit=Number(monitor.history_limit);const limit=[0,5,10,25,50,100].includes(rawLimit)?rawLimit:10;const safePage=limit===0?Math.max(1,Number(page||1)):1;const result=await api(`api/wallet-watch/transactions?entry_id=${encodeURIComponent(state.entryId)}&monitor_id=${encodeURIComponent(id)}&limit=${encodeURIComponent(limit)}&page=${encodeURIComponent(safePage)}`,{timeoutMs:180000});state.walletWatchTxOverviews[id]={loading:false,error:"",data:result};if(state.walletWatch?.status?.monitor_summaries?.[id]&&Number.isFinite(Number(result.balance_sats)))state.walletWatch.status.monitor_summaries[id].balance_sats=Number(result.balance_sats||0);if(state.walletWatch?.status?.addresses&&Number.isFinite(Number(result.balance_sats))){const rows=state.walletWatch.status.addresses.filter(row=>String(row.monitor_id||"")===id);if(rows.length===1)rows[0].balance_sats=Number(result.balance_sats||0);}renderWalletWatch();}catch(error){state.walletWatchTxOverviews[id]={loading:false,error:errorText(error),data:null};renderWalletWatchTxOverview(id);}}
function renderWalletWatch(){
  initWalletWatchPanelToggles();
  const statusBox=$("#walletWatchStatus"),privacy=$("#walletWatchPrivacy"),list=$("#walletWatchMonitors"),targetList=$("#walletWatchNotificationTargets"),simMonitor=$("#walletWatchSimMonitor");
  if(!statusBox||!privacy||!list||!targetList)return;
  renderWalletWatchStatusOnly();
  if(!state.walletWatch)return;
  const cfg=walletWatchConfig(),st=state.walletWatch.status||{};
  if(simMonitor){const current=simMonitor.value;const monitors=(cfg.monitors||[]).filter(item=>item&&item.enabled!==false);simMonitor.innerHTML=monitors.length?monitors.map((mon,index)=>`<option value="${esc(mon.id)}">${esc(state.discreet?`Wallet #${index+1}`:(mon.label||`Wallet ${index+1}`))}</option>`).join(""):`<option value="">${esc(walletWatchLang("Test-Wallet (keine echte Adresse)","Test wallet (no real address)"))}</option>`;if([...simMonitor.options].some(option=>option.value===current))simMonitor.value=current;}
  if(!state.walletWatchSettingsDirty){
    $("#walletWatchEnabled").checked=Boolean(cfg.enabled);$("#walletWatchInterval").value=String(cfg.poll_interval_seconds||60);const querySource=$("#walletWatchQuerySource");if(querySource)querySource.value=cfg.query_source||"auto";const electrumKind=$("#walletWatchElectrumKind");if(electrumKind)electrumKind.value=cfg.electrum_kind||"fulcrum";const electrumHost=$("#walletWatchElectrumHost");if(electrumHost)electrumHost.value=cfg.electrum_host||"";const electrumPort=$("#walletWatchElectrumPort");if(electrumPort)electrumPort.value=String(cfg.electrum_port||50001);const electrumTls=$("#walletWatchElectrumTls");if(electrumTls)electrumTls.checked=Boolean(cfg.electrum_tls);const electrumVerify=$("#walletWatchElectrumVerifySsl");if(electrumVerify)electrumVerify.checked=cfg.electrum_verify_ssl!==false;const electrumPinned=$("#walletWatchElectrumPinnedCertPem");if(electrumPinned)electrumPinned.value=cfg.electrum_pinned_cert_pem||"";const publicTor=$("#walletWatchPublicTor");if(publicTor){publicTor.checked=Boolean(cfg.allow_public_tor);publicTor.disabled=false;publicTor.title="";}$("#walletWatchPersistent").checked=Boolean(cfg.persistent_notification);$("#walletWatchDetail").value=cfg.notification_detail||"discreet";
    const logMode=$("#walletWatchLogMode"),logDays=$("#walletWatchLogDays"),logCount=$("#walletWatchLogCount");if(logMode)logMode.value=cfg.log_display_mode||"days";if(logDays)logDays.value=String(cfg.log_display_days||30);if(logCount)logCount.value=String(cfg.log_display_count||100);
    const services=$("#walletWatchNotifyServices"),selected=new Set(cfg.notification_services||[]),available=state.walletWatch.notify_services||[];
    if(services)services.innerHTML=available.length?available.map(name=>`<label><input type="checkbox" value="${esc(name)}" ${selected.has(name)?"checked":""}><span><strong>${esc(name)}</strong></span></label>`).join(""):`<p class="storage-note">${esc(walletWatchLang("Keine notify.*-Dienste gefunden. Persistente HA-Meldungen funktionieren trotzdem.","No notify.* services found. Persistent HA notifications still work."))}</p>`;
  }
  syncWalletWatchSourceUi();syncWalletWatchLogModeUi();
  targetList.innerHTML=(cfg.notification_targets||[]).length?(cfg.notification_targets||[]).map(target=>{
    const detail=target.detail==="inherit"?walletWatchLang("Globale Einstellung","Global setting"):target.detail;
    const targetValue=maskWalletWatchValue(target.url);
    return `<article class="goal-card"><div><span class="kicker">${esc(String(target.kind||"").toUpperCase())}</span><h3>${esc(target.label||target.id)}</h3><p class="storage-note wallet-watch-secret">${esc(targetValue)}</p><small>${esc(detail)} · ${target.verify_ssl===false?"TLS verify AUS":"TLS verify AN"} · ${target.token?walletWatchLang("Token verschlüsselt","Token encrypted"):walletWatchLang("ohne Token","no token")}</small></div><button class="danger wallet-watch-notify-delete" type="button" data-id="${esc(target.id)}">${esc(walletWatchLang("Entfernen","Remove"))}</button></article>`;
  }).join(""):`<p class="storage-note">${esc(walletWatchLang("Noch kein zusätzliches ntfy-/Webhook-Ziel eingetragen.","No additional ntfy/webhook target configured yet."))}</p>`;
  $$(".wallet-watch-notify-delete").forEach(btn=>btn.onclick=()=>{const id=btn.dataset.id;cfg.notification_targets=(cfg.notification_targets||[]).filter(item=>item.id!==id);state.walletWatch.config=cfg;renderWalletWatch();});
  list.querySelectorAll(".sats-sentinel-tx-details[open]").forEach(details=>{const id=String(details.dataset.monitorId||"");if(id)state.walletWatchOpenTxDetails.add(id);});
  list.innerHTML=(cfg.monitors||[]).length?(cfg.monitors||[]).map(mon=>{
    const safeValue=maskWalletWatchValue(mon.value);const reserve=mon.kind==="address"?walletWatchLang("Exakte Adresse dauerhaft überwachen","Monitor this exact address permanently"):`Receive Gap ${mon.receive_count||0} · Change Gap ${mon.change_count||0}`;
    const threshold=Number(mon.min_notify_sats||0);const thresholdText=threshold>0?`${fmtNumber(threshold,0)} sats`:walletWatchLang("Keine Alarmgrenze","No alert threshold");
    const channels=[mon.notify_ha_event!==false?"HA Event":null,mon.notify_persistent!==false?"HA":null,mon.notify_services!==false?"Push":null,mon.notify_external!==false?"ntfy/Webhook":null].filter(Boolean).join(" · ")||walletWatchLang("Nur Journal","Journal only");
    const incoming=mon.notify_incoming!==false,outgoing=mon.notify_outgoing!==false,kindLabel=String(mon.kind||"address").toUpperCase(),runtime=walletWatchMonitorRuntimeSummary(mon.id),historyLimit=[0,5,10,25,50,100].includes(Number(mon.history_limit))?Number(mon.history_limit):10,balanceText=state.discreet?"••••":`${fmtNumber(Number(runtime.balance_sats||0)/SATsFix(),8)} BTC`,pending=Boolean(mon._pending_save),historyLabel=historyLimit===0?walletWatchLang("Unbegrenzt · 25/Seite","Unlimited · 25/page"):`${historyLimit} TX`;
    return `<article class="sats-sentinel-watch-card ${pending?"pending-save":""}"><div class="sats-sentinel-watch-head"><div class="sats-sentinel-watch-badges"><span class="sats-sentinel-category ${esc(walletWatchCategoryClass(mon.category))}">${esc(walletWatchCategoryLabel(mon.category))}</span><span class="sats-sentinel-kind-badge">${esc(kindLabel)}</span>${pending?`<span class="sats-sentinel-pending-badge">${esc(walletWatchLang("NOCH SPEICHERN","SAVE REQUIRED"))}</span>`:""}</div><div class="sats-sentinel-watch-actions"><button class="secondary compact wallet-watch-edit" type="button" data-id="${esc(mon.id)}">${esc(walletWatchLang("Bearbeiten","Edit"))}</button><button class="danger compact wallet-watch-delete" type="button" data-id="${esc(mon.id)}">${esc(walletWatchLang("Entfernen","Remove"))}</button></div></div><div class="sats-sentinel-watch-title"><h3>${esc(state.discreet?"••••":(mon.label||mon.id))}</h3>${mon.note&&!state.discreet?`<p>${esc(mon.note)}</p>`:""}</div><code class="sats-sentinel-watch-address">${esc(safeValue)}</code><div class="wallet-watch-monitor-meta"><div class="wide-meta"><span>${esc(walletWatchLang("Überwachung","Monitoring"))}</span><strong>${esc(reserve)}</strong></div><div><span>${esc(walletWatchLang("Bestand","Balance"))}</span><strong>${esc(balanceText)}</strong><small>${esc(state.discreet?"••••":`${runtime.addresses} ${walletWatchLang("abgeleitete Adresse(n)","derived address(es)")}${mon.kind!=="address"?` · Receive ${runtime.receive_addresses} · Change ${runtime.change_addresses}`:""} · ${runtime.utxo_count} UTXO`)}</small></div><div><span>${esc(walletWatchLang("TX-Übersicht","TX overview"))}</span><strong>${esc(historyLabel)}</strong></div><div class="wide-meta sats-sentinel-last-movement"><span>${esc(walletWatchLang("Letzte von Sentinel erkannte Bewegung","Last movement detected by Sentinel"))}</span>${walletWatchLastDetectedHtml(runtime.last_activity)}</div><div class="${incoming?"is-on":"is-off"}"><span>${esc(walletWatchLang("Eingangs-Alarm","Incoming alert"))}</span><strong>${esc(incoming?walletWatchLang("Alarm aktiv","Alert on"):walletWatchLang("Nur protokollieren","Log only"))}</strong></div><div class="${outgoing?"is-on":"is-off"}"><span>${esc(walletWatchLang("Ausgangs-Alarm","Outgoing alert"))}</span><strong>${esc(outgoing?walletWatchLang("Alarm aktiv","Alert on"):walletWatchLang("Nur protokollieren","Log only"))}</strong></div><div><span>${esc(walletWatchLang("Alarmgrenze","Alert threshold"))}</span><strong>${esc(thresholdText)}</strong></div><div><span>${esc(walletWatchLang("Alarmkanäle","Alert channels"))}</span><strong>${esc(channels)}</strong></div></div><details class="sats-sentinel-tx-details" data-monitor-id="${esc(mon.id)}" ${pending?'data-pending-save="1"':""} ${!pending&&state.walletWatchOpenTxDetails.has(String(mon.id))?"open":""}><summary>${esc(pending?walletWatchLang("Erst Sats Sentinel speichern, dann TX laden","Save Sats Sentinel before loading TX"):historyLimit===0?walletWatchLang("Alle Transaktionen seitenweise anzeigen","Browse all transactions page by page"):walletWatchLang(`Letzte ${historyLimit} Transaktionen anzeigen`,`Show last ${historyLimit} transactions`))}</summary><div class="sats-sentinel-tx-host" data-wallet-watch-tx-host="${esc(mon.id)}"><p class="storage-note">${esc(pending?walletWatchLang("Dieser Watch-Eintrag existiert noch nicht im verschlüsselten Backend. Erst speichern.","This watch entry does not exist in the encrypted backend yet. Save it first."):walletWatchLang("Historische Übersicht wird erst beim Öffnen geladen und löst keine rückwirkenden Alarme aus.","Historical overview is loaded only when opened and never triggers retroactive alerts."))}</p></div></details></article>`;
  }).join(""):`<p class="storage-note">${esc(walletWatchLang("Noch keine Adresse oder Watch-only-Wallet eingetragen.","No address or watch-only wallet configured yet."))}</p>`;
  $$(".wallet-watch-delete").forEach(btn=>btn.onclick=()=>{void removeWalletWatchMonitor(btn.dataset.id);});
  $$(".wallet-watch-edit").forEach(btn=>btn.onclick=()=>editWalletWatchMonitor(btn.dataset.id));
  $$(".sats-sentinel-tx-details").forEach(details=>{
    const id=String(details.dataset.monitorId||"");
    details.ontoggle=()=>{
      if(details.open){
        if(id)state.walletWatchOpenTxDetails.add(id);
        if(details.dataset.pendingSave!=="1"){const currentPage=Math.max(1,Number(walletWatchTxOverviewState(id)?.data?.page||1));renderWalletWatchTxOverview(id);void loadWalletWatchTransactions(id,{page:currentPage});}
      }else if(id){state.walletWatchOpenTxDetails.delete(id);}
    };
    if(details.open&&details.dataset.pendingSave!=="1"){const currentPage=Math.max(1,Number(walletWatchTxOverviewState(id)?.data?.page||1));renderWalletWatchTxOverview(id);void loadWalletWatchTransactions(id,{page:currentPage});}
  });
  renderWalletWatchActivity();
  syncWalletWatchKindUi();
}
function walletWatchCategoryClass(value){return `wallet-watch-category-${String(value||"other")}`;}
function walletWatchCounterpartyLimit(){return Math.max(1,Math.min(12,Number(state.walletWatchActivityCounterparties||3)));}
function walletWatchExplorerBase(log){return String(log?.explorer_base_url||"").replace(/\/$/,"");}
function walletWatchAddressLink(address,log){const raw=String(address||"");if(state.discreet)return `<code>••••</code>`;const short=walletWatchShortAddress(raw),base=walletWatchExplorerBase(log);if(!raw)return `<span class="storage-note">${esc(walletWatchLang("unbekannt","unknown"))}</span>`;if(!base)return `<code title="${esc(raw)}">${esc(short)}</code>`;const href=`${base}/address/${encodeURIComponent(raw)}`;return `<a class="sats-sentinel-explorer-link sats-sentinel-address-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="${esc(raw)}"><code>${esc(short)}</code><span aria-hidden="true">↗</span></a>`;}
function walletWatchPartyHtml({label="",address="",category="",extraCount=0}={},log,{amountSats=null,compact=false}={}){if(state.discreet)return `<div class="sats-sentinel-party"><strong>••••</strong><code>••••</code></div>`;const name=String(label||"").trim(),cat=String(category||"").trim(),amount=amountSats===null?"":`${fmtNumber(Number(amountSats||0)/SATsFix(),8)} BTC`;return `<div class="sats-sentinel-party ${compact?"compact":""}">${name?`<div class="sats-sentinel-party-name"><strong>${esc(name)}</strong>${cat?`<span class="sats-sentinel-category ${esc(walletWatchCategoryClass(cat))}">${esc(walletWatchCategoryLabel(cat))}</span>`:""}</div>`:""}<div class="sats-sentinel-party-address">${walletWatchAddressLink(address,log)}${amount?`<small>${esc(amount)}</small>`:""}</div>${extraCount>0?`<small class="storage-note">+${extraCount} ${esc(walletWatchLang("weitere beobachtete Adresse(n)","more watched address(es)"))}</small>`:""}</div>`;}
function walletWatchWatchedPartyHtml(item,log){const addresses=Array.isArray(item.watched_addresses)?item.watched_addresses.filter(Boolean):[],primary=String(addresses[0]||"");return walletWatchPartyHtml({label:String(item.monitor_label||item.monitor_id||"Wallet"),address:primary,category:String(item.category||"other"),extraCount:Math.max(0,addresses.length-1)},log);}
function walletWatchCounterpartyHtml(item,{mobile=false,log=null}={}){const cps=Array.isArray(item.counterparties)?item.counterparties:[],limit=walletWatchCounterpartyLimit(),shown=cps.slice(0,limit);if(state.discreet)return `<code>••••</code>`;if(!shown.length)return `<span class="storage-note">${esc(walletWatchLang("unbekannt / mehrere","unknown / multiple"))}</span>`;const lines=shown.map(cp=>walletWatchPartyHtml({label:String(cp.monitor_label||""),address:String(cp.address||""),category:String(cp.category||"")},log,{amountSats:Number(cp.value_sats||0),compact:true})).join("");const remaining=cps.length-shown.length;return `<div class="sats-sentinel-counterparty-list ${mobile?"mobile":""}">${lines}${remaining>0?`<small class="storage-note">+${remaining} ${esc(walletWatchLang("weitere Adresse(n)","more address(es)"))}</small>`:""}</div>`;}
function walletWatchTxLink(item,log){const txid=String(item?.txid||"");if(state.discreet||!/^[0-9a-f]{64}$/i.test(txid))return `<code>${esc(state.discreet?"••••":walletWatchShortAddress(txid))}</code>`;const base=walletWatchExplorerBase(log);if(!base)return `<code>${esc(walletWatchShortAddress(txid))}</code>`;const href=`${base}/tx/${encodeURIComponent(txid)}`;return `<a class="sats-sentinel-explorer-link sats-sentinel-tx-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="${esc(txid)}"><code>${esc(walletWatchShortAddress(txid))}</code><span aria-hidden="true">↗</span></a>`;}
function renderWalletWatchActivity(){
  const log=state.walletWatch?.activity_log||{items:[],page:1,pages:1,total:0,stored_total:0,page_size:state.walletWatchActivityPageSize||10},body=$("#walletWatchActivityBody"),cards=$("#walletWatchActivityCards"),nav=$("#walletWatchActivityPagination"),summary=$("#walletWatchActivitySummary"),category=$("#walletWatchActivityCategory"),counterpartySelect=$("#walletWatchActivityCounterparties"),pageSizeSelect=$("#walletWatchActivityPageSize");
  if(category)category.value=state.walletWatchActivityCategory||"all";
  if(counterpartySelect)counterpartySelect.value=String(walletWatchCounterpartyLimit());
  if(pageSizeSelect)pageSizeSelect.value=String(Number(log.page_size||state.walletWatchActivityPageSize||10));
  if(summary)summary.textContent=walletWatchLang(`${Number(log.total||0)} im Filter · ${Number(log.stored_total||0)} insgesamt gespeichert · ${Number(log.page_size||state.walletWatchActivityPageSize||10)} pro Seite (max. 25)`,`${Number(log.total||0)} in filter · ${Number(log.stored_total||0)} stored in total · ${Number(log.page_size||state.walletWatchActivityPageSize||10)} per page (max. 25)`);
  const items=Array.isArray(log.items)?log.items:[];
  const rowHtml=item=>{const outgoing=item.direction==="outgoing",status=item.confirmed?walletWatchLang("Bestätigt","Confirmed"):walletWatchLang("Unbestätigt","Unconfirmed"),amount=state.discreet?"••••":`${fmtNumber(Number(item.amount_sats||0)/SATsFix(),8)} BTC`,watched=walletWatchWatchedPartyHtml(item,log),other=walletWatchCounterpartyHtml(item,{log}),sender=outgoing?watched:other,recipient=outgoing?other:watched;return `<tr class="sats-sentinel-movement-row ${outgoing?"outgoing":"incoming"}"><td><strong>${esc(fmtDateTime(item.detected_at))}</strong><small class="sats-sentinel-detected-time">${esc(walletWatchLang("von Sentinel erkannt","detected by Sentinel"))}</small></td><td><span class="sats-sentinel-category ${esc(walletWatchCategoryClass(item.category))}">${esc(walletWatchCategoryLabel(item.category))}</span></td><td>${sender}</td><td class="sats-sentinel-flow-direction">${walletWatchDirectionBadge(item.direction)}<span aria-hidden="true">→</span></td><td>${recipient}</td><td><strong>${esc(amount)}</strong></td><td>${esc(status)}${item.rbf?" · RBF":""}</td><td>${walletWatchTxLink(item,log)}</td></tr>`;};
  if(body)body.innerHTML=items.length?items.map(rowHtml).join(""):`<tr><td colspan="8" class="storage-note">${esc(walletWatchLang("Noch keine Bewegung im gewählten Anzeigebereich.","No movement in the selected display range yet."))}</td></tr>`;
  if(cards)cards.innerHTML=items.map(item=>{const outgoing=item.direction==="outgoing",amount=state.discreet?"••••":`${fmtNumber(Number(item.amount_sats||0)/SATsFix(),8)} BTC`,watched=walletWatchWatchedPartyHtml(item,log),other=walletWatchCounterpartyHtml(item,{mobile:true,log}),sender=outgoing?watched:other,recipient=outgoing?other:watched;return `<article class="ledger-mobile-card sats-sentinel-activity-card sats-sentinel-movement-row ${outgoing?"outgoing":"incoming"}"><div class="ledger-mobile-card-head"><strong>${walletWatchDirectionBadge(item.direction,{compact:true})} · ${esc(amount)}</strong><span>${esc(fmtDateTime(item.detected_at))}<small class="sats-sentinel-detected-time">${esc(walletWatchLang("erkannt","detected"))}</small></span></div><div class="sats-sentinel-mobile-flow"><section><span>${esc(walletWatchLang("Sender","Sender"))}</span>${sender}</section><div class="sats-sentinel-mobile-direction">${walletWatchDirectionBadge(item.direction,{compact:true})}<span aria-hidden="true">→</span></div><section><span>${esc(walletWatchLang("Empfänger","Recipient"))}</span>${recipient}</section></div><div><span>TXID</span>${walletWatchTxLink(item,log)}</div></article>`;}).join("");
  if(nav){const page=Number(log.page||1),pages=Number(log.pages||1);if(pages>1){const opts=Array.from({length:pages},(_,i)=>`<option value="${i+1}" ${i+1===page?"selected":""}>${esc(walletWatchLang(`Seite ${i+1}`,`Page ${i+1}`))}</option>`).join("");nav.innerHTML=`<button type="button" class="secondary compact" data-ww-page="1" ${page<=1?"disabled":""} title="${esc(walletWatchLang("Erste Seite","First page"))}">«</button><button type="button" class="secondary compact" data-ww-page="${Math.max(1,page-1)}" ${page<=1?"disabled":""}>‹</button><label class="sats-sentinel-page-picker"><span>${esc(walletWatchLang(`Seite ${page} von ${pages}`,`Page ${page} of ${pages}`))}</span><select id="walletWatchActivityPageSelect">${opts}</select></label><button type="button" class="secondary compact" data-ww-page="${Math.min(pages,page+1)}" ${page>=pages?"disabled":""}>›</button><button type="button" class="secondary compact" data-ww-page="${pages}" ${page>=pages?"disabled":""} title="${esc(walletWatchLang("Letzte Seite","Last page"))}">»</button>`;nav.querySelectorAll("[data-ww-page]").forEach(btn=>btn.onclick=()=>loadWalletWatchActivity(Number(btn.dataset.wwPage||1)));const picker=$("#walletWatchActivityPageSelect");if(picker)picker.onchange=()=>loadWalletWatchActivity(Number(picker.value||1));}else nav.innerHTML="";}
}
async function loadWalletWatchActivity(page=1){if(!state.entryId||state.data?.locked)return;state.walletWatchActivityPage=Math.max(1,Number(page||1));try{const result=await api(`api/wallet-watch/log?entry_id=${encodeURIComponent(state.entryId)}&page=${state.walletWatchActivityPage}&page_size=${encodeURIComponent(state.walletWatchActivityPageSize||10)}&category=${encodeURIComponent(state.walletWatchActivityCategory||"all")}`,{timeoutMs:15000});if(state.walletWatch){state.walletWatch.activity_log=result;renderWalletWatchActivity();}}catch(error){if(state.activeTab==="walletwatch")toast(errorText(error));}}
async function refreshWalletWatchStatus({silent=true}={}){if(walletWatchStatusRefreshInFlight||!state.entryId||!state.data?.security?.owner)return false;walletWatchStatusRefreshInFlight=true;try{const oldCount=Number(state.walletWatch?.status?.activity_log_count||0),status=await api(`api/wallet-watch/status?entry_id=${encodeURIComponent(state.entryId)}`,{timeoutMs:7000});if(!state.walletWatch)state.walletWatch={config:walletWatchConfig(),status,notify_services:[],activity_log:{items:[],page:1,pages:1,total:0,stored_total:0}};else state.walletWatch.status=status;if(state.activeTab==="walletwatch"){renderWalletWatchStatusOnly();if(!state.data?.locked&&Number(status.activity_log_count||0)!==oldCount)void loadWalletWatchActivity(1);}return true;}catch(error){if(!silent&&state.activeTab==="walletwatch")toast(errorText(error));return false;}finally{walletWatchStatusRefreshInFlight=false;}}
function startWalletWatchStatusPolling(){if(walletWatchStatusPollTimer)clearInterval(walletWatchStatusPollTimer);walletWatchStatusPollTimer=setInterval(()=>{if(document.hidden||state.activeTab!=="walletwatch")return;void refreshWalletWatchStatus({silent:true});},15000);}
function syncWalletWatchLogModeUi(){const mode=$("#walletWatchLogMode")?.value||"days";$("#walletWatchLogDaysWrap")?.classList.toggle("hidden",mode!=="days");$("#walletWatchLogCountWrap")?.classList.toggle("hidden",mode!=="count");}
function resetWalletWatchMonitorForm(){const form=$("#walletWatchAddForm");if(!form)return;form.reset();form.elements.edit_id.value="";form.elements.kind.value="address";form.elements.category.value="other";form.elements.receive_count.value="2";form.elements.change_count.value="2";form.elements.history_limit.value="10";form.elements.min_notify_amount.value="0";form.elements.min_notify_unit.value="sats";for(const name of ["notify_incoming","notify_outgoing","notify_ha_event","notify_persistent","notify_services","notify_external"])form.elements[name].checked=true;$("#walletWatchMonitorSubmit").textContent=walletWatchLang("Überwachung speichern","Save watch target");$("#walletWatchMonitorCancel").classList.add("hidden");syncWalletWatchKindUi();syncWalletWatchDetectedKind();}
function editWalletWatchMonitor(id){const cfg=walletWatchConfig(),mon=(cfg.monitors||[]).find(item=>item.id===id),form=$("#walletWatchAddForm");if(!mon||!form)return;form.elements.edit_id.value=mon.id;form.elements.label.value=mon.label||"";form.elements.category.value=mon.category||"other";form.elements.kind.value=walletWatchDetectMonitorKind(mon.kind||"address",mon.value||"");form.elements.value.value=mon.value||"";form.elements.receive_count.value=String(mon.receive_count||0);form.elements.change_count.value=String(mon.change_count||0);form.elements.history_limit.value=String(mon.history_limit===0?0:(mon.history_limit||10));form.elements.note.value=mon.note||"";form.elements.min_notify_unit.value="sats";form.elements.min_notify_amount.value=String(mon.min_notify_sats||0);for(const name of ["notify_incoming","notify_outgoing","notify_ha_event","notify_persistent","notify_services","notify_external"])form.elements[name].checked=mon[name]!==false;$("#walletWatchMonitorSubmit").textContent=walletWatchLang("Änderungen speichern","Save changes");$("#walletWatchMonitorCancel").classList.remove("hidden");syncWalletWatchKindUi();syncWalletWatchDetectedKind();form.scrollIntoView({behavior:"smooth",block:"start"});}
function SATsFix(){return 100000000;}
async function loadWalletWatch(){
  if(!state.entryId||state.data?.locked||!state.data?.security?.owner||state.walletWatchLoading)return;
  state.walletWatchLoading=true;renderWalletWatch();
  try{state.walletWatch=await api(`api/wallet-watch?entry_id=${encodeURIComponent(state.entryId)}`,{timeoutMs:30000});state.walletWatchSettingsDirty=false;}
  catch(error){toast(errorText(error));}
  finally{state.walletWatchLoading=false;if(state.activeTab==="walletwatch")renderWalletWatch();}
}
function syncWalletWatchSourceUi(){const mode=$("#walletWatchQuerySource")?.value||"auto",box=$("#walletWatchElectrumSettings");if(box)box.classList.toggle("hidden",!["auto","fulcrum","electrs"].includes(mode));const kind=$("#walletWatchElectrumKind");if(kind){if(mode==="fulcrum")kind.value="fulcrum";if(mode==="electrs")kind.value="electrs";kind.disabled=mode==="fulcrum"||mode==="electrs";}const publicTor=$("#walletWatchPublicTor");if(publicTor)publicTor.disabled=mode==="fulcrum"||mode==="electrs"||mode==="mempool_own";}
function syncWalletWatchKindUi(){const form=$("#walletWatchAddForm");if(!form)return;const derived=form.elements.kind?.value!=="address";$$('.wallet-watch-derived').forEach(el=>el.classList.toggle("hidden",!derived));}
function walletWatchCompactMonitorValue(value){return String(value||"").normalize("NFKC").trim().replace(/[\s\u200B-\u200D\u2060\uFEFF]/g,"").replace(/^[`\'"]|[`\'"]$/g,"");}
function walletWatchExtractExtendedKey(value){const source=walletWatchCompactMonitorValue(value),match=source.match(/^(?:\[[0-9a-fA-F]{8}(?:\/[0-9]+[hH\']?)*\])?((?:xpub|ypub|zpub)[1-9A-HJ-NP-Za-km-z]+)$/i);return match?match[1]:"";}
function walletWatchDetectMonitorKind(kind,value){const requested=String(kind||"address").trim().toLowerCase(),source=walletWatchCompactMonitorValue(value);if(walletWatchExtractExtendedKey(source)||["xpub","ypub","zpub"].some(prefix=>source.toLowerCase().startsWith(prefix)))return "xpub";if(/^(?:pkh\(|wpkh\(|sh\(wpkh\()/i.test(source))return "descriptor";return requested;}
function walletWatchCanonicalMonitorValue(kind,value){const raw=String(value||"");if(kind==="xpub")return walletWatchExtractExtendedKey(raw)||walletWatchCompactMonitorValue(raw);if(kind==="descriptor")return walletWatchCompactMonitorValue(raw);return raw.trim();}
function walletWatchDraftConfig(){
  const cfg=JSON.parse(JSON.stringify(walletWatchConfig()));
  cfg.enabled=Boolean($("#walletWatchEnabled")?.checked);cfg.poll_interval_seconds=Number($("#walletWatchInterval")?.value||60);cfg.query_source=$("#walletWatchQuerySource")?.value||"auto";cfg.electrum_kind=$("#walletWatchElectrumKind")?.value||"fulcrum";cfg.electrum_host=String($("#walletWatchElectrumHost")?.value||"").trim();cfg.electrum_port=Number($("#walletWatchElectrumPort")?.value||50001);cfg.electrum_tls=Boolean($("#walletWatchElectrumTls")?.checked);cfg.electrum_verify_ssl=Boolean($("#walletWatchElectrumVerifySsl")?.checked);cfg.electrum_pinned_cert_pem=String($("#walletWatchElectrumPinnedCertPem")?.value||"").trim();cfg.allow_public_tor=Boolean($("#walletWatchPublicTor")?.checked);cfg.persistent_notification=Boolean($("#walletWatchPersistent")?.checked);cfg.notification_detail=$("#walletWatchDetail")?.value||"discreet";cfg.notification_services=$$("#walletWatchNotifyServices input:checked").map(x=>x.value);cfg.log_display_mode=$("#walletWatchLogMode")?.value||"days";cfg.log_display_days=Number($("#walletWatchLogDays")?.value||30);cfg.log_display_count=Number($("#walletWatchLogCount")?.value||100);
  cfg.monitors=(Array.isArray(cfg.monitors)?cfg.monitors:[]).map(item=>{const raw=String(item?.value||""),kind=walletWatchDetectMonitorKind(item?.kind,raw),value=walletWatchCanonicalMonitorValue(kind,raw),clean={...item,kind,value};delete clean._pending_save;return clean;});
  return cfg;
}
function syncWalletWatchDetectedKind(){const form=$("#walletWatchAddForm"),box=$("#walletWatchDetectedKind");if(!form||!box)return;const raw=String(form.elements.value?.value||""),kind=walletWatchDetectMonitorKind(form.elements.kind?.value||"address",raw);if(raw.trim()&&kind!==String(form.elements.kind?.value||"address")){form.elements.kind.value=kind;syncWalletWatchKindUi();}const label=kind==="xpub"?"XPUB / YPUB / ZPUB":kind==="descriptor"?"Output Descriptor":walletWatchLang("Bitcoin-Adresse","Bitcoin address");box.textContent=raw.trim()?`${walletWatchLang("Erkannt","Detected")}: ${label}`:"";box.className=`storage-note ${raw.trim()?"positive":""}`;}
function walletWatchSourceTestMessage(probe){const label=String(probe?.label||"Quelle"),route=probe?.route==="tor"?"Tor":walletWatchLang("Direkt","Direct"),endpoint=String(probe?.endpoint||"");let detail="";if(probe?.server_version){detail=Array.isArray(probe.server_version)?probe.server_version.join(" · "):String(probe.server_version);}else if(probe?.block_height!==undefined){detail=`Block ${probe.block_height}`;}return `${walletWatchLang("Verbindung erfolgreich","Connection successful")}: ${label} · ${route}${endpoint?` · ${endpoint}`:""}${detail?` · ${detail}`:""}`;}
async function testWalletWatchSource({config=null,silent=false}={}){const button=$("#walletWatchSourceTest"),result=$("#walletWatchSourceTestResult"),cfg=config||walletWatchDraftConfig();if(button)button.disabled=true;if(result){result.textContent=walletWatchLang("Abfragequelle wird geprüft …","Testing query source …");result.className="result";}try{const probe=await api("api/wallet-watch/source-test",{method:"POST",body:JSON.stringify({entry_id:state.entryId,config:cfg}),timeoutMs:45000});if(result){result.textContent=walletWatchSourceTestMessage(probe);result.className="result positive";}if(!silent)toast(walletWatchLang("Sentinel-Abfragequelle erreichbar.","Sentinel query source is reachable."));return probe;}catch(error){const message=errorText(error);if(result){result.textContent=message;result.className="result negative";}if(!silent)toast(message);throw error;}finally{if(button)button.disabled=false;}}
async function saveWalletWatch(event){
  event?.preventDefault();if(!state.walletWatch)return;const cfg=walletWatchDraftConfig(),result=$("#walletWatchSaveResult"),button=$("#walletWatchSaveButton");if(button)button.disabled=true;if(result){result.textContent=walletWatchLang("Speichere Sats Sentinel …","Saving Sats Sentinel …");result.className="result";}
  try{state.walletWatch=await api("api/wallet-watch",{method:"POST",body:JSON.stringify({entry_id:state.entryId,config:cfg}),timeoutMs:30000});state.walletWatchSettingsDirty=false;if(result){result.textContent=state.walletWatch.status?.scan_in_progress?walletWatchLang("Gespeichert. Adressscan läuft im Hintergrund …","Saved. Address scan is running in the background …"):walletWatchLang("Gespeichert. Abfragequelle wird jetzt geprüft …","Saved. Testing query source now …");result.className="result positive";}renderWalletWatch();try{const probe=await testWalletWatchSource({config:state.walletWatch.config,silent:true});if(result){result.textContent=`${walletWatchLang("Sats Sentinel gespeichert.","Sats Sentinel saved.")} ${walletWatchSourceTestMessage(probe)}`;result.className="result positive";}}catch(_probeError){if(result){result.textContent=walletWatchLang("Sats Sentinel wurde gespeichert, aber die Abfragequelle ist nicht erreichbar. Siehe Verbindungstest darunter.","Sats Sentinel was saved, but the query source is not reachable. See the connection test below.");result.className="result warning";}}}
  catch(error){const message=errorText(error);if(result){result.textContent=message;result.className="result negative";}toast(message);}finally{if(button)button.disabled=false;}
}
async function pollWalletWatch(){const button=$("#walletWatchPoll");if(button)button.disabled=true;try{const status=await api("api/wallet-watch/poll",{method:"POST",body:JSON.stringify({entry_id:state.entryId}),timeoutMs:180000});if(state.walletWatch)state.walletWatch.status=status;renderWalletWatch();toast(walletWatchLang("Sats Sentinel geprüft.","Sats Sentinel checked."));}catch(error){toast(errorText(error));}finally{if(button)button.disabled=false;}}
async function removeWalletWatchMonitor(id){
  if(!state.walletWatch)return;const current=(walletWatchConfig().monitors||[]).find(item=>item.id===id);if(!current)return;const label=state.discreet?walletWatchLang("diese Wallet","this wallet"):(current.label||current.id);const ok=window.confirm(walletWatchLang(`„${label}“ wirklich entfernen? Die zugehörige Sentinel-Journal-Historie wird dauerhaft aus dem verschlüsselten Cache gelöscht.`,`Really remove “${label}”? Its Sats Sentinel journal history will be permanently deleted from the encrypted cache.`));if(!ok)return;
  if(current._pending_save){state.walletWatch.config.monitors=(state.walletWatch.config.monitors||[]).filter(item=>item.id!==id);delete state.walletWatchTxOverviews[id];renderWalletWatch();toast(walletWatchLang("Noch nicht gespeicherten Watch-Eintrag entfernt.","Removed unsaved watch entry."));return;}
  const previous=state.walletWatch;try{const response=await api("api/wallet-watch/remove-monitor",{method:"POST",body:JSON.stringify({entry_id:state.entryId,monitor_id:id}),timeoutMs:30000});state.walletWatch={config:response.config,status:response.status,notify_services:response.notify_services||previous.notify_services||[],activity_log:response.activity_log||previous.activity_log};delete state.walletWatchTxOverviews[id];state.walletWatchOpenTxDetails.delete(id);resetWalletWatchMonitorForm();renderWalletWatch();await loadWalletWatchActivity(1);const purged=Number(response?.status?.purged_activity_count||0);toast(walletWatchLang(`Watch-Eintrag entfernt · ${purged} Journal-Eintrag${purged===1?"":"e"} dauerhaft gelöscht.`,`Watch entry removed · ${purged} journal entr${purged===1?"y":"ies"} permanently deleted.`));}
  catch(error){state.walletWatch=previous;renderWalletWatch();toast(errorText(error));}
}
async function addWalletWatchMonitor(event){
  event.preventDefault();if(!state.walletWatch)return;const form=event.currentTarget,fd=new FormData(form),rawValue=String(fd.get("value")||"").trim(),kind=walletWatchDetectMonitorKind(fd.get("kind"),rawValue),value=walletWatchCanonicalMonitorValue(kind,rawValue),result=$("#walletWatchMonitorSaveResult"),button=$("#walletWatchMonitorSubmit");if(!value){toast(walletWatchLang("Adresse/XPUB/Descriptor fehlt.","Address/XPUB/descriptor is missing."));return;}
  const cfg=walletWatchConfig(),editId=String(fd.get("edit_id")||""),unit=String(fd.get("min_notify_unit")||"sats"),rawAmount=Math.max(0,Number(fd.get("min_notify_amount")||0)),minNotifySats=Math.round(unit==="btc"?rawAmount*SATsFix():rawAmount);cfg.monitors=cfg.monitors||[];const existing=editId?cfg.monitors.find(item=>item.id===editId):null,id=existing?.id||`watch_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,7)}`;const monitor={id,label:String(fd.get("label")||"").trim()||existing?.label||`Wallet ${cfg.monitors.length+1}`,category:String(fd.get("category")||"other"),note:String(fd.get("note")||"").trim(),kind,value,enabled:existing?.enabled!==false,receive_count:kind==="address"?0:Number(fd.get("receive_count")||2),change_count:kind==="address"?0:Number(fd.get("change_count")||2),history_limit:[0,5,10,25,50,100].includes(Number(fd.get("history_limit")))?Number(fd.get("history_limit")):10,created_at:existing?.created_at||new Date().toISOString(),min_notify_sats:minNotifySats,notify_incoming:form.elements.notify_incoming.checked,notify_outgoing:form.elements.notify_outgoing.checked,notify_ha_event:form.elements.notify_ha_event.checked,notify_persistent:form.elements.notify_persistent.checked,notify_services:form.elements.notify_services.checked,notify_external:form.elements.notify_external.checked};
  if(button)button.disabled=true;if(result){result.textContent=walletWatchLang("Watch-Eintrag wird verschlüsselt gespeichert …","Saving watch entry encrypted …");result.className="result";}
  try{
    // A user commonly enters/changes the Fulcrum endpoint and then immediately
    // saves a watch target. Persist that dirty settings draft first; otherwise
    // the monitor-only backend endpoint intentionally preserves the *old* source
    // configuration and a restart appears to have forgotten the new server.
    if(state.walletWatchSettingsDirty){
      const settingsDraft=walletWatchDraftConfig();
      state.walletWatch=await api("api/wallet-watch",{method:"POST",body:JSON.stringify({entry_id:state.entryId,config:settingsDraft}),timeoutMs:30000});
      state.walletWatchSettingsDirty=false;
    }
    const response=await api("api/wallet-watch/upsert-monitor",{method:"POST",body:JSON.stringify({entry_id:state.entryId,monitor}),timeoutMs:30000});const previous=state.walletWatch;state.walletWatch={...previous,config:response.config,status:response.status,notify_services:response.notify_services||previous.notify_services||[],activity_log:response.activity_log||previous.activity_log};delete state.walletWatchTxOverviews[id];resetWalletWatchMonitorForm();renderWalletWatch();const scanText=response.status?.scan_in_progress?walletWatchLang(" Adressscan läuft im Hintergrund …"," Address scan is running in the background …"):"";if(result){result.textContent=(existing?walletWatchLang("Watch-Eintrag gespeichert.","Watch entry saved."):walletWatchLang("Watch-Eintrag hinzugefügt und gespeichert.","Watch entry added and saved."))+scanText;result.className="result positive";}toast((existing?walletWatchLang("Watch-Eintrag gespeichert.","Watch entry saved."):walletWatchLang("Watch-Eintrag hinzugefügt und gespeichert.","Watch entry added and saved."))+scanText);}
  catch(error){const message=errorText(error);if(result){result.textContent=message;result.className="result negative";}toast(message);}finally{if(button)button.disabled=false;}
}
function addWalletWatchNotificationTarget(event){
  event.preventDefault();if(!state.walletWatch)return;const form=event.currentTarget,fd=new FormData(form),url=String(fd.get("url")||"").trim();if(!url){toast(walletWatchLang("Ziel-URL fehlt.","Target URL is missing."));return;}
  const cfg=walletWatchConfig(),kind=String(fd.get("kind")||"ntfy"),id=`notify_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,7)}`;cfg.notification_targets=cfg.notification_targets||[];cfg.notification_targets.push({id,label:String(fd.get("label")||"").trim()||(kind==="ntfy"?"ntfy":"Webhook"),kind,url,token:String(fd.get("token")||"").trim(),enabled:true,detail:String(fd.get("detail")||"inherit"),verify_ssl:Boolean(form.elements.verify_ssl.checked)});state.walletWatch.config=cfg;form.reset();form.elements.kind.value="ntfy";form.elements.detail.value="inherit";form.elements.verify_ssl.checked=true;renderWalletWatch();toast(walletWatchLang("Benachrichtigungsziel hinzugefügt – noch speichern.","Notification target added – save to activate."));
}
async function testWalletWatchNotifications(){const button=$("#walletWatchNotifyTest");if(button)button.disabled=true;try{const result=await api("api/wallet-watch/notify-test",{method:"POST",body:JSON.stringify({entry_id:state.entryId}),timeoutMs:180000});if(result.ok){toast(walletWatchLang(`Test an ${result.delivered?.length||0} Ziel(e) gesendet.`,`Test sent to ${result.delivered?.length||0} target(s).`));}else{toast((result.errors||[]).join(" · ")||walletWatchLang("Benachrichtigungstest teilweise fehlgeschlagen.","Notification test partially failed."));}if(state.walletWatch)state.walletWatch.status={...state.walletWatch.status,last_notification_error:result.ok?null:(result.errors||[])[0]||"Fehler"};renderWalletWatch();}catch(error){toast(errorText(error));}finally{if(button)button.disabled=false;}}
async function simulateWalletWatchActivity(event){event?.preventDefault();const form=$("#walletWatchSimulateForm"),button=$("#walletWatchSimulateButton"),resultBox=$("#walletWatchSimulateResult");if(!form)return;if(button)button.disabled=true;if(resultBox){resultBox.textContent=walletWatchLang("Simulation wird ausgelöst …","Starting simulation …");resultBox.className="result";}try{const payload={entry_id:state.entryId,monitor_id:String(form.elements.monitor_id?.value||""),direction:String(form.elements.direction?.value||"outgoing"),amount_sats:Number(form.elements.amount_sats?.value||100000),confirmed:Boolean(form.elements.confirmed?.checked),rbf:Boolean(form.elements.rbf?.checked)};const result=await api("api/wallet-watch/simulate",{method:"POST",body:JSON.stringify(payload),timeoutMs:180000});if(resultBox){resultBox.textContent=walletWatchLang(`TEST-Bewegung ausgelöst: ${result.direction==="outgoing"?"Ausgang":"Eingang"} · ${fmtNumber(result.amount_sats||0,0)} sats`,`TEST movement triggered: ${result.direction} · ${fmtNumber(result.amount_sats||0,0)} sats`);resultBox.className="result positive";}toast(walletWatchLang("Sats-Sentinel-Testbewegung ausgelöst.","Sats Sentinel test movement triggered."));}catch(error){if(resultBox){resultBox.textContent=errorText(error);resultBox.className="result negative";}else toast(errorText(error));}finally{if(button)button.disabled=false;}}
async function liveTestWalletWatchTransaction(event){event?.preventDefault();const form=$("#walletWatchLiveTestForm"),button=$("#walletWatchLiveTestButton"),resultBox=$("#walletWatchLiveTestResult");if(!form)return;if(button)button.disabled=true;if(resultBox){resultBox.textContent=walletWatchLang("Mempool-Transaktion wird über die erlaubte Route geprüft …","Checking transaction through the allowed route …");resultBox.className="result";}try{const payload={entry_id:state.entryId,txid:String(form.elements.txid?.value||"").trim(),direction:String(form.elements.direction?.value||"outgoing")};const result=await api("api/wallet-watch/live-test",{method:"POST",body:JSON.stringify(payload),timeoutMs:180000});if(resultBox){resultBox.textContent=walletWatchLang(`Live-TEST ausgelöst: ${result.direction==="outgoing"?"Ausgang":"Eingang"} · ${fmtNumber(result.amount_sats||0,0)} sats · ${result.confirmed?"bestätigt":"unbestätigt"}`,`Live TEST triggered: ${result.direction} · ${fmtNumber(result.amount_sats||0,0)} sats · ${result.confirmed?"confirmed":"unconfirmed"}`);resultBox.className="result positive";}toast(walletWatchLang("Live-Mempool-Test ausgelöst.","Live mempool test triggered."));}catch(error){if(resultBox){resultBox.textContent=errorText(error);resultBox.className="result negative";}else toast(errorText(error));}finally{if(button)button.disabled=false;}}
const wwSettings=$("#walletWatchSettingsForm"),wwAdd=$("#walletWatchAddForm"),wwNotifyAdd=$("#walletWatchNotifyTargetForm"),wwPoll=$("#walletWatchPoll"),wwSourceTest=$("#walletWatchSourceTest"),wwNotifyTest=$("#walletWatchNotifyTest"),wwSimulate=$("#walletWatchSimulateForm"),wwLiveTest=$("#walletWatchLiveTestForm"),wwLogMode=$("#walletWatchLogMode"),wwQuerySource=$("#walletWatchQuerySource"),wwActivityCategory=$("#walletWatchActivityCategory"),wwActivityPageSize=$("#walletWatchActivityPageSize"),wwActivityCounterparties=$("#walletWatchActivityCounterparties"),wwActivityRefresh=$("#walletWatchActivityRefresh"),wwMonitorCancel=$("#walletWatchMonitorCancel");if(wwSettings){wwSettings.onsubmit=saveWalletWatch;const markWalletWatchSettingsDirty=()=>{state.walletWatchSettingsDirty=true;};wwSettings.addEventListener("input",markWalletWatchSettingsDirty);wwSettings.addEventListener("change",markWalletWatchSettingsDirty);}if(wwSourceTest)wwSourceTest.onclick=()=>{void testWalletWatchSource();};if(wwQuerySource)wwQuerySource.onchange=()=>{state.walletWatchSettingsDirty=true;syncWalletWatchSourceUi();};if(wwAdd){wwAdd.onsubmit=addWalletWatchMonitor;wwAdd.elements.kind.onchange=()=>{syncWalletWatchKindUi();syncWalletWatchDetectedKind();};wwAdd.elements.value?.addEventListener("input",syncWalletWatchDetectedKind);wwAdd.elements.value?.addEventListener("paste",()=>setTimeout(syncWalletWatchDetectedKind,0));}if(wwNotifyAdd)wwNotifyAdd.onsubmit=addWalletWatchNotificationTarget;if(wwPoll)wwPoll.onclick=pollWalletWatch;if(wwNotifyTest)wwNotifyTest.onclick=testWalletWatchNotifications;if(wwSimulate)wwSimulate.onsubmit=simulateWalletWatchActivity;if(wwLiveTest)wwLiveTest.onsubmit=liveTestWalletWatchTransaction;if(wwLogMode)wwLogMode.onchange=syncWalletWatchLogModeUi;if(wwActivityCategory)wwActivityCategory.onchange=()=>{state.walletWatchActivityCategory=wwActivityCategory.value||"all";state.walletWatchActivityPage=1;void loadWalletWatchActivity(1);};if(wwActivityPageSize)wwActivityPageSize.onchange=()=>{const v=Number(wwActivityPageSize.value||10);state.walletWatchActivityPageSize=[10,15,20,25].includes(v)?v:10;localStorage.setItem("bst_wallet_watch_page_size",String(state.walletWatchActivityPageSize));state.walletWatchActivityPage=1;void loadWalletWatchActivity(1);};if(wwActivityCounterparties)wwActivityCounterparties.onchange=()=>{state.walletWatchActivityCounterparties=Number(wwActivityCounterparties.value||3);renderWalletWatchActivity();};if(wwActivityRefresh)wwActivityRefresh.onclick=()=>loadWalletWatchActivity(state.walletWatchActivityPage||1);if(wwMonitorCancel)wwMonitorCancel.onclick=resetWalletWatchMonitorForm;

state.lastActivityAt=Date.now();localStorage.setItem("bst_last_activity_at",String(state.lastActivityAt));
console.info(`Bitcoin Stack Tracker dashboard ${BUILD_VERSION}`);
applyTheme(); applyLanguage(); applyUnit(); applyDiscreetMode(state.discreet); applyFiatFreeMode(state.fiatFree,state.satsPerFiat); updateBackupFileName(); updateCsvFileName(); setDefaultDate(); startBitcoinNetworkTicker(); boot().then(()=>loadBackupHealth());

/* robust historical goal date fallback and capped goal display */

// transaction plausibility controls
updateTransactionFiatLabel();
syncTransactionCalculator();
