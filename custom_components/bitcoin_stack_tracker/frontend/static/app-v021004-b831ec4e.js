"use strict";

const BUILD_VERSION = "0.21.0.4";
const FRONTEND_BUILD = "021004-b831ec4e";
const SATS_PER_BTC = 100_000_000;
const state = {
  lang: localStorage.getItem("bst_lang") || (String(navigator.language || "de").toLowerCase().startsWith("de") ? "de" : "en"),
  theme: localStorage.getItem("bst_theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"),
  unit: localStorage.getItem("bst_unit") || "BTC",
  chartMode: localStorage.getItem("bst_chart_mode") || "price",
  chartScale: localStorage.getItem("bst_chart_scale") || "linear",
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
    return ["1","30","90","365","ytd","1095","1825","3650","first_purchase","max"].includes(saved) ? saved : "365";
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
  lastActivityAt: Date.now()
};
state.fiatFree = localStorage.getItem("bst_fiat_free_mode") === "1";
state.satsPerFiat = localStorage.getItem("bst_sats_per_fiat") !== "0";
state.backupHealth = null;
state.backupHealthLoading = false;

let networkPollTimer = null;
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
    chartView:"Ansicht",chartLegend:"Chart-Legende",leftAxis:"Linke Skala",rightAxis:"Rechte Skala",chartCurrency:"Chartwährung",btcPrice:"Bitcoin-Kurs",portfolioValue:"Portfoliowert",stackHistory:"Stack-Verlauf",profitLossHistory:"Gesamtgewinn/-verlust",pricePortfolioOverlay:"Kurs + Portfoliowert",priceStackOverlay:"Kurs + Stack",priceProfitLossOverlay:"Kurs + Gesamtgewinn/-verlust",portfolioProfitLossOverlay:"Portfoliowert + Gesamtgewinn/-verlust",costProfitLossOverlay:"Einstand + Buchgewinn/-verlust",openCostBasis:"Offener Einstand",unrealizedProfitLoss:"Buchgewinn/-verlust",period:"Zeitraum",allData:"Alle Daten",yearToDate:"Jahresanfang",firstPurchaseRange:"Seit erstem Kauf",maxRange:"Max",scale:"Skala",linear:"Linear",logarithmic:"Logarithmisch",logUnavailable:"Für Gewinn-/Verlust-Ansichten ist nur die lineare Skala möglich.",overlayOpacity:"Overlay-Transparenz",today:"Heute",performance:"Performance im gewählten Zeitraum",performanceNote:"Portfoliowert wird cashflow-bereinigt: Käufe, Verkäufe, Stack-Zugänge und Ausgaben werden nicht als Rendite gezählt. Buchgewinn/-verlust bezieht sich auf den offenen Einstand. Gesamtgewinn/-verlust ist realisiert plus unrealisiert.",periodStart:"Start",periodEnd:"Ende",absoluteChange:"Absolut",percentageChange:"Prozent",bitcoinPerformance:"Bitcoin-Kurs",portfolioPerformance:"Portfoliowert",stackPerformance:"BTC-Stack",bookProfitLossPerformance:"Buchgewinn/-verlust",realizedProfitLossPerformance:"Realisierter Gewinn/Verlust",profitLossPerformance:"Gesamtgewinn/-verlust",comparisonUnavailable:"Für diesen Zeitraum sind noch nicht genug Werte vorhanden.",
    milestones:"Meilensteine",newEntry:"Neue Buchung",type:"Art",depot:"Depot",amount:"Menge",unit:"Einheit",currency:"Fiatwährung",pricePerBtc:"Preis pro BTC",fee:"Gebühr",dateTime:"Datum / Uhrzeit",note:"Notiz",saveEntry:"Buchung speichern",date:"Datum",price:"Preis",holding:"Haltezeit",
    depots:"Depots",totalDepot:"Gesamtdepot",allDepotsCombined:"Alle Depots zusammen",totalStack:"Gesamtstack",totalValue:"Gesamtwert",rangePerformance:"Zeitraum-Performance",stackChange:"Stack-Veränderung",selectedRange:"Gewählter Zeitraum",add:"Hinzufügen",goals:"Stacking-Ziele",name:"Name",target:"Ziel",addGoal:"Ziel hinzufügen",goalStorage:"Jedes Ziel erzeugt zusätzliche lokale Verlaufswerte. Mehr Ziele bedeuten mehr Speicherbedarf.",remaining:"Fehlt",current:"Aktuell",targetValue:"Zielwert",
    overviewOnly:"Nur Übersicht",holdingDisclaimer:"Konfigurierbare Haltezeit- und FIFO-Übersicht. Abhängig vom anwendbaren Recht können Coins nach der gewählten Frist anders behandelt werden. Keine Steuerberatung und keine Steuererklärung.",holdingRule:"Haltezeit-Regel",days:"Tage bis Langzeit",customNote:"Eigene Notiz",saveRule:"Regel speichern",currentClassification:"Aktuelle Einordnung",saleOverview:"Verkaufsübersicht",sale:"Verkauf",purchase:"Kauf",holdingDays:"Haltetage",classification:"Einordnung",gain:"Realisierter Gewinn/Verlust",status:"Status",nextLong:"Nächster Langzeit-Zugang",
    historyAndExport:"Historie & Export",dailyDataCache:"TAGESDATEN-CACHE",enableHistory:"Historische Daten aktivieren",historyCacheHint:"Bereits gespeicherte Tageswerte bleiben beim Deaktivieren vollständig erhalten.",autoSync:"Täglich automatisch ergänzen",incrementalHint:"Nach dem ersten vollständigen Abruf werden nur neue Tage mit einem kleinen Überlappungsfenster geladen.",saveHistorySettings:"Historieneinstellungen speichern",torProxy:"Integrierter Tor-SOCKS5-Proxy",torProxyHint:"Tor wird mit dem Add-on installiert. Alle öffentlichen Live- und Historienabfragen laufen darüber; nur eine eigene private lokale Node wird direkt angesprochen.",torOnly:"Öffentliche Live- und Historienabfragen: nur Tor",historySettingsSaved:"Historieneinstellungen gespeichert",syncHistory:"Historische Tagesdaten synchronisieren",createExport:"CSV-/ZIP-Export erstellen",cachedValues:"Gespeicherte Tagesdatenpunkte",dataPoints:"Datenpunkte",historyCountHint:"Ein Datenpunkt entspricht einem gespeicherten Tageswert für die jeweilige Währung – nicht dem Bitcoin-Preis.",historySource:"Quelle",sourceCascade:"Quellenkette",lastSync:"Letzter Abgleich",historyDisabled:"Historie deaktiviert – lokaler Cache bleibt erhalten",historyEnabled:"Historie aktiviert",never:"Noch nie",
    support:"Unterstützen",v4vText:"Die Anwendung ist offen, lokal und Bitcoin-only. Wer einen Wert darin sieht, kann Sats zurückgeben.",stack:"Stack",expense:"Ausgabe",stackValue:"Stack-Wert",openBasis:"Offener Einstand",unrealized:"Buchgewinn/-verlust",realized:"Realisierter Gewinn/Verlust",noData:"Keine Daten vorhanden",allDepots:"Alle Depots",delete:"Löschen",deleteAllEntries:"Alle Buchungen löschen",allEntriesDeleted:"Alle Buchungen wurden gelöscht",deleteAllBackupConfirm:"Vor dem Löschen solltest du ein aktuelles verschlüsseltes Backup erstellen. Hast du ein Backup erstellt und möchtest du fortfahren?",deleteAllFinalConfirm:"LETZTE WARNUNG: Alle eingetragenen Buchungen werden dauerhaft gelöscht. Käufe, Verkäufe, Ausgaben und Stack-Einträge können danach nur aus einem Backup wiederhergestellt werden. Bist du wirklich sicher?",save:"Speichern",entrySaved:"Buchung gespeichert",ruleSaved:"Regel gespeichert",goalSaved:"Ziel gespeichert",exportCreated:"Export erstellt",syncDone:"Synchronisierung abgeschlossen",confirmDelete:"Wirklich löschen?",search:"Suchen",
    securityTitle:"Passwort-Tresor und Familienzugriff",securityIntro:"Nur ausgewählte Home-Assistant-Nutzer erhalten Zugriff. Bei Passwortverschlüsselung muss jeder freigegebene Nutzer den Tresor zusätzlich entsperren.",allowedUsers:"Erlaubte Nutzer",saveAccess:"Zugriff speichern",accessSaved:"Zugriffsliste gespeichert",entityPrivacy:"HA-Sensoren und Recorder",exposeSensors:"Sensible HA-Sensoren veröffentlichen",sensorWarning:"Unsicher: Normale HA-Nutzer können Entity-Zustände und Recorder-Historie sehen. Für Familienzugriff ausgeschaltet lassen.",saveSensorMode:"Sensormodus speichern",adminLimit:"Ein HA-Administrator mit Root- oder Dateisystemzugriff bleibt technisch vertrauenswürdig.",ownerOnly:"Nur der Portfolio-Eigentümer kann diese Einstellung ändern.",notOwner:"Du darfst das Portfolio verwenden, aber nicht seine Sicherheits- oder Historieneinstellungen ändern.",noAccess:"Für diesen Home-Assistant-Nutzer ist kein Bitcoin-Portfolio freigegeben.",sensorModeSaved:"Sensormodus gespeichert",
    vaultLocked:"Bitcoin-Tresor gesperrt",vaultSetupText:"Lege jetzt das Master-Passwort fest. Es wird nicht gespeichert.",vaultLockedText:"Dieses Portfolio ist mit einem Master-Passwort geschützt. Zusätzlich muss dein Home-Assistant-Nutzer freigegeben sein.",masterPassword:"Master-Passwort",unlockVault:"Tresor entsperren",lockVault:"Sperren",passwordLoss:"Das Passwort wird nicht gespeichert. Bei Verlust können verschlüsselte Daten und Backups nicht wiederhergestellt werden.",backupRestore:"Sicherung & Wiederherstellung",backupPassword:"Backup-Passwort",backupFile:"Backup-Datei",createBackup:"Verschlüsseltes Backup herunterladen",restoreBackup:"Backup importieren",restoreWarning:"Der Import ersetzt ausschließlich Buchungen, Depots, Ziele und lokale Historie des ausgewählten Portfolios. Installations-, Netzwerk- und Zugriffs-Einstellungen bleiben unverändert.",backupCreated:"Verschlüsseltes Backup erstellt",backupRestored:"Backup erfolgreich importiert",encryptionSettings:"Verschlüsselung",newMasterPassword:"Neues Master-Passwort",currentMasterPassword:"Aktuelles Master-Passwort",enableEncryption:"Verschlüsselung aktivieren",disableEncryption:"Verschlüsselung deaktivieren",changePassword:"Passwort ändern",encryptionChoice:"Ohne Verschlüsselung liegt das Kaufbuch lokal im Klartext. Die Nutzerfreigabe schützt dann nur innerhalb von Home Assistant.",encryptionMode:"Speichermodus",passwordProtected:"Passwortschutz",unlocked:"Entsperrt",privateMode:"Privater Sensormodus",confirmDisableEncryption:"Verschlüsselung wirklich deaktivieren? Das Kaufbuch wird danach lokal im Klartext gespeichert.",confirmRestore:"Backup wirklich importieren und die vorhandenen Portfolio-Daten ersetzen?",passwordChanged:"Master-Passwort geändert",encryptionChanged:"Verschlüsselungsmodus geändert",repeatPassword:"Passwort wiederholen",passwordMismatch:"Die Passwörter stimmen nicht überein.",
    appLog:"Technisches App-Log",refreshLogs:"Log aktualisieren",downloadLogs:"Log herunterladen",clearLogs:"Log leeren",confirmClearLogs:"App-Log wirklich leeren?",logCleared:"App-Log geleert",logPrivacy:"Das Log enthält nur technische Metadaten wie Route, Status, Laufzeit und Dienstname. Passwörter, Backups und Buchungsinhalte werden nicht protokolliert.",logLoading:"Log wird geladen …",logEmpty:"Noch keine Logeinträge vorhanden.",
    networkSecurity:"Tor-Killswitch & Leak-Test",runLeakTest:"Leak-Test starten",leakTestHint:"Der Test sendet keine direkte öffentliche Prüfverbindung. Die Zähler sind kumulativ seit dem Start: Die Integration kann verbotene Ziele bereits vor einem Socket blockieren; der Killswitch verwirft zusätzlich jedes Nicht-Tor-Paket im Gateway. Geblockt bedeutet: Es wurde nicht ungefiltert ins Internet übertragen.",onlyTorOnline:"Mit Tor verbunden",torConnecting:"Tor wird aufgebaut",torDisconnected:"Tor-Verbindung abgebrochen",torNotEstablished:"Tor noch nicht verbunden",torError:"Tor-Fehler",clearnetLeak:"Clearnet-Leak erkannt",localCacheOnly:"Nur lokale Daten und Cache verfügbar",protectionFault:"Killswitch-Schutzfehler",leakTestRunning:"Leak-Test läuft …",leakTestPassed:"Leak-Test bestanden: keine direkte Clearnet-Verbindung erkannt.",leakTestFailed:"Leak-Test fehlgeschlagen",killswitch:"Firewall-Killswitch",torVerified:"Tor-Ausgang bestätigt",torExitIp:"Tor-Exit-IP",remoteDns:"Remote-DNS / SafeSocks",blockedConnections:"Vom Killswitch geblockte Pakete",coreBlocked:"Von der Integration vor Verbindung blockiert",localConnections:"Erlaubte lokale Verbindungen",directClearnet:"Festgestellte direkte Clearnet-Sockets",noneAllowed:"0 erkannt",leakTargets:"Leak-Ziele",lastBlocked:"Letztes blockiertes Ziel",checkedAt:"Geprüft",appBuild:"App-Build",active:"Aktiv",inactive:"Inaktiv",yes:"Ja",no:"Nein",checking:"Prüfung läuft …",newTorIdentity:"Neue Tor-Verbindung",runLeakTest:"Neue Tor-IP & Leak-Test",automaticTorRotation:"Tor-Adresse automatisch wechseln",automaticTorRotationHint:"Fordert regelmäßig neue Tor-Circuits an. Eine andere Exit-IP kann nicht garantiert werden.",rotationInterval:"Wechselintervall",saveTorRotation:"Tor-Wechsel speichern",rotationSaved:"Tor-Wechsel gespeichert",rotatingTor:"Neue Tor-Verbindung wird aufgebaut …",torIdentityChanged:"Tor-Exit-IP wurde geändert",torIdentityRequested:"Neue Tor-Circuits wurden angefordert",previousExitIp:"Vorherige Tor-Exit-IP",nextRotation:"Nächster automatischer Wechsel",lastRotation:"Letzter Tor-Wechsel",ipUnchanged:"Tor verwendet weiterhin dieselbe Exit-IP",torControlNotReady:"Tor-Steuerung ist noch nicht bereit",torBootstrap:"Tor-Aufbau",discreetMode:"Diskret-Modus",hideSensitiveValues:"Finanzwerte mit •••• ausblenden",discreetModeHint:"Gilt nur für diesen Browser beziehungsweise dieses Gerät. Diagrammformen bleiben sichtbar, Zahlen werden verborgen.",chooseBackupFile:"Datei auswählen",noFileSelected:"Keine Datei ausgewählt",torProcessUnavailable:"Tor-Prozess und SOCKS5-Endpunkt sind nicht verfügbar",torStarting:"Tor wird noch aufgebaut",torLost:"Tor-SOCKS5-Verbindung wurde unterbrochen",torTimeout:"Tor-Prüfung hat zu lange gedauert"
  },
  en: {
    overview:"Overview",ledger:"Ledger",structure:"Depots & goals",tax:"Holding period",settings:"Export & data",security:"Access & encryption",logs:"App log",
    longTerm:"Long term",shortTerm:"Short term",unknown:"Unknown",mixed:"Mixed",nextMilestone:"Next goal",dailyHistory:"Daily values",chartTitle:"History",
    chartView:"View",chartLegend:"Chart legend",leftAxis:"Left scale",rightAxis:"Right scale",chartCurrency:"Chart currency",btcPrice:"Bitcoin price",portfolioValue:"Portfolio value",stackHistory:"Stack history",profitLossHistory:"Total profit/loss",pricePortfolioOverlay:"Price + portfolio",priceStackOverlay:"Price + stack",priceProfitLossOverlay:"Price + total profit/loss",portfolioProfitLossOverlay:"Portfolio + total profit/loss",costProfitLossOverlay:"Cost basis + unrealized profit/loss",openCostBasis:"Open cost basis",unrealizedProfitLoss:"Unrealized profit/loss",period:"Range",allData:"All data",yearToDate:"Year to date",firstPurchaseRange:"Since first purchase",maxRange:"Max",scale:"Scale",linear:"Linear",logarithmic:"Logarithmic",logUnavailable:"Profit/loss views support the linear scale only.",overlayOpacity:"Overlay opacity",today:"Today",performance:"Performance for selected range",performanceNote:"Portfolio performance is cash-flow adjusted: purchases, sales, stack additions, and expenses are not counted as return. Unrealized profit/loss is measured against open cost basis. Total profit/loss is realized plus unrealized.",periodStart:"Start",periodEnd:"End",absoluteChange:"Absolute",percentageChange:"Percent",bitcoinPerformance:"Bitcoin price",portfolioPerformance:"Portfolio value",stackPerformance:"BTC stack",bookProfitLossPerformance:"Unrealized profit/loss",realizedProfitLossPerformance:"Realized profit/loss",profitLossPerformance:"Total profit/loss",comparisonUnavailable:"Not enough values are available for this range.",
    milestones:"Milestones",newEntry:"New entry",type:"Type",depot:"Depot",amount:"Amount",unit:"Unit",currency:"Fiat currency",pricePerBtc:"Price per BTC",fee:"Fee",dateTime:"Date / time",note:"Note",saveEntry:"Save entry",date:"Date",price:"Price",holding:"Holding",
    depots:"Depots",totalDepot:"Total portfolio",allDepotsCombined:"All depots combined",totalStack:"Total stack",totalValue:"Total value",rangePerformance:"Range performance",stackChange:"Stack change",selectedRange:"Selected range",add:"Add",goals:"Stacking goals",name:"Name",target:"Target",addGoal:"Add goal",goalStorage:"Each goal creates additional local history values. More goals require more storage.",remaining:"Remaining",current:"Current",targetValue:"Target value",
    overviewOnly:"Overview only",holdingDisclaimer:"Configurable holding-period and FIFO overview. Depending on applicable law, coins older than the selected period may be treated differently. Not tax advice and not a tax return.",holdingRule:"Holding-period rule",days:"Days until long term",customNote:"Custom note",saveRule:"Save rule",currentClassification:"Current classification",saleOverview:"Sale overview",sale:"Sale",purchase:"Purchase",holdingDays:"Holding days",classification:"Classification",gain:"Realized profit/loss",status:"Status",nextLong:"Next long-term lot",
    historyAndExport:"History & export",dailyDataCache:"DAILY DATA CACHE",enableHistory:"Enable historical data",historyCacheHint:"Previously cached daily values remain fully stored when disabled.",autoSync:"Automatically add new days",incrementalHint:"After the first complete download, only new days plus a small overlap are fetched.",saveHistorySettings:"Save history settings",torProxy:"Bundled Tor SOCKS5 proxy",torProxyHint:"Tor is installed with the app. All public live and historical requests use it; only an own private local node is contacted directly.",torOnly:"Public live and history requests: Tor only",historySettingsSaved:"History settings saved",syncHistory:"Synchronize historical daily data",createExport:"Create CSV/ZIP export",cachedValues:"Stored daily data points",dataPoints:"data points",historyCountHint:"One data point is one stored daily value for that currency – it is not the Bitcoin price.",historySource:"Source",sourceCascade:"Source cascade",lastSync:"Last synchronization",historyDisabled:"History disabled – local cache retained",historyEnabled:"History enabled",never:"Never",
    support:"Support",v4vText:"The app is open, local, and Bitcoin-only. Anyone who receives value can return value in sats.",stack:"Stack",expense:"Expense",stackValue:"Stack value",openBasis:"Open cost basis",unrealized:"Unrealized profit/loss",realized:"Realized profit/loss",noData:"No data available",allDepots:"All depots",delete:"Delete",deleteAllEntries:"Delete all entries",allEntriesDeleted:"All ledger entries were deleted",deleteAllBackupConfirm:"Create a current encrypted backup before deleting. Have you created a backup and do you want to continue?",deleteAllFinalConfirm:"FINAL WARNING: All entered ledger data will be permanently deleted. Purchases, sales, expenses, and stack entries can then only be restored from a backup. Are you absolutely sure?",save:"Save",entrySaved:"Entry saved",ruleSaved:"Rule saved",goalSaved:"Goal saved",exportCreated:"Export created",syncDone:"Synchronization finished",confirmDelete:"Delete this item?",search:"Search",
    securityTitle:"Password vault and family access",securityIntro:"Only selected Home Assistant users may access the portfolio. Password-protected portfolios must also be unlocked by each allowed user.",allowedUsers:"Allowed users",saveAccess:"Save access",accessSaved:"Access list saved",entityPrivacy:"HA sensors and recorder",exposeSensors:"Publish sensitive HA sensors",sensorWarning:"Unsafe: normal HA users may read entity states and recorder history. Leave this disabled for family access.",saveSensorMode:"Save sensor mode",adminLimit:"A Home Assistant administrator with root or filesystem access remains technically trusted.",ownerOnly:"Only the portfolio owner can change this setting.",notOwner:"You may use the portfolio but cannot change its security or history settings.",noAccess:"No Bitcoin portfolio is shared with this Home Assistant user.",sensorModeSaved:"Sensor mode saved",
    vaultLocked:"Bitcoin vault locked",vaultSetupText:"Set the master password now. It will not be stored.",vaultLockedText:"This portfolio is protected by a master password. Your Home Assistant user must also be allowed.",masterPassword:"Master password",unlockVault:"Unlock vault",lockVault:"Lock",passwordLoss:"The password is never stored. Lost passwords make encrypted data and backups unrecoverable.",backupRestore:"Backup & restore",backupPassword:"Backup password",backupFile:"Backup file",createBackup:"Download encrypted backup",restoreBackup:"Import backup",restoreWarning:"Import replaces only ledger entries, depots, goals, and local history in the selected portfolio. Installation, network, and access settings stay unchanged.",backupCreated:"Encrypted backup created",backupRestored:"Backup imported successfully",encryptionSettings:"Encryption",newMasterPassword:"New master password",currentMasterPassword:"Current master password",enableEncryption:"Enable encryption",disableEncryption:"Disable encryption",changePassword:"Change password",encryptionChoice:"Without encryption the local ledger is stored in plaintext. The allowlist then protects access only inside Home Assistant.",encryptionMode:"Storage mode",passwordProtected:"Password protection",unlocked:"Unlocked",privateMode:"Private sensor mode",confirmDisableEncryption:"Disable encryption? The ledger will then be stored locally in plaintext.",confirmRestore:"Import this backup and replace existing portfolio data?",passwordChanged:"Master password changed",encryptionChanged:"Encryption mode changed",repeatPassword:"Repeat password",passwordMismatch:"The passwords do not match.",
    appLog:"Technical app log",refreshLogs:"Refresh log",downloadLogs:"Download log",clearLogs:"Clear log",confirmClearLogs:"Clear the app log?",logCleared:"App log cleared",logPrivacy:"The log contains technical metadata only. Passwords, backups, and ledger content are never logged.",logLoading:"Loading log …",logEmpty:"No log entries yet.",
    networkSecurity:"Tor killswitch & leak test",runLeakTest:"Run leak test",leakTestHint:"The test sends no direct public probe. Counters are cumulative since startup: the integration can reject forbidden targets before opening a socket, while the killswitch drops any non-Tor packet in the gateway. Blocked means it was not sent unfiltered to the internet.",onlyTorOnline:"Connected through Tor",torConnecting:"Connecting to Tor",torDisconnected:"Tor connection lost",torNotEstablished:"Tor not connected yet",torError:"Tor error",clearnetLeak:"Clearnet leak detected",localCacheOnly:"Local data and cache only",protectionFault:"Killswitch protection fault",leakTestRunning:"Leak test running …",leakTestPassed:"Leak test passed: no direct Clearnet connection detected.",leakTestFailed:"Leak test failed",killswitch:"Firewall killswitch",torVerified:"Tor exit verified",torExitIp:"Tor exit IP",remoteDns:"Remote DNS / SafeSocks",blockedConnections:"Packets blocked by killswitch",coreBlocked:"Blocked by integration before connect",localConnections:"Allowed local connections",directClearnet:"Detected direct Clearnet sockets",noneAllowed:"0 detected",leakTargets:"Leak targets",lastBlocked:"Last blocked target",checkedAt:"Checked",appBuild:"App build",active:"Active",inactive:"Inactive",yes:"Yes",no:"No",checking:"Checking …",newTorIdentity:"New Tor connection",runLeakTest:"New Tor IP & leak test",automaticTorRotation:"Rotate Tor address automatically",automaticTorRotationHint:"Regularly requests new Tor circuits. A different exit IP cannot be guaranteed.",rotationInterval:"Rotation interval",saveTorRotation:"Save Tor rotation",rotationSaved:"Tor rotation saved",rotatingTor:"Building a new Tor connection …",torIdentityChanged:"Tor exit IP changed",torIdentityRequested:"New Tor circuits requested",previousExitIp:"Previous Tor exit IP",nextRotation:"Next automatic rotation",lastRotation:"Last Tor rotation",ipUnchanged:"Tor is still using the same exit IP",torControlNotReady:"Tor control is not ready yet",torBootstrap:"Tor bootstrap",discreetMode:"Discreet mode",hideSensitiveValues:"Hide financial values with ••••",discreetModeHint:"Applies only to this browser or device. Chart shapes remain visible while numbers are hidden.",chooseBackupFile:"Choose file",noFileSelected:"No file selected",torProcessUnavailable:"Tor process and SOCKS5 endpoint are unavailable",torStarting:"Tor is still starting",torLost:"Tor SOCKS5 connection was lost",torTimeout:"Tor check timed out"
  }
};

Object.assign(I18N.de, {
  trueReturn:"Echte Rendite",twr:"TWR",twrLong:"Zeitgewichtete Rendite",xirr:"XIRR p. a.",xirrLong:"Persönliche annualisierte Rendite",twrHint:"TWR trennt die Rendite an jedem Ein- und Auszahlungszeitpunkt und berücksichtigt Transaktionsgebühren. XIRR berücksichtigt Zeitpunkt und Höhe der persönlichen Cashflows (365-Tage-Konvention).",shortRangeXirr:"Bei kurzen Zeiträumen kann die annualisierte XIRR stark schwanken.",cashflowAdjusted:"Cashflow-bereinigt",unavailableReturn:"Nicht berechenbar",cashflowAdjustedChange:"Cashflow-bereinigt",netStackChange:"Netto-Veränderung",endingBalance:"Endbestand",currentProfitLoss:"Aktueller Stand",onOpenCostBasis:"Auf offenen Einstand",onInvestedCapital:"Auf investiertes Kapital",cumulativePurchaseOutlay:"Kumulierte Kaufaufwendungen",ambiguousReturn:"Mehrdeutig",
  dcaAnalysis:"DCA-Auswertung",purchasesInRange:"Käufe im Zeitraum",weightedAveragePrice:"Gewichteter Kaufkurs",averageSatsPerFiat:"Ø Sats pro Fiat",investedFiat:"Investiertes Fiat",feeRatio:"Gebührenquote",breakEvenPrice:"Break-even-Kurs",bestPurchase:"Bester Kauf",worstPurchase:"Schlechtester Kauf",acquiredStack:"Gekaufter Stack",differentCurrenciesOmitted:"Käufe in anderen Währungen wurden für Fiatkennzahlen nicht eingerechnet.",noPurchasesRange:"Keine passenden Käufe im gewählten Zeitraum.",
  drawdownAnalysis:"Drawdown im Zeitraum",periodHighDistance:"Abstand zum Zeitraumhoch",maximumDrawdown:"Maximaler Drawdown",bitcoinDrawdown:"Bitcoin",portfolioDrawdown:"Portfolio · TWR-bereinigt",peak:"Hoch",trough:"Tief",drawdownHint:"Der Portfolio-Drawdown basiert auf einem an jedem Cashflow getrennten TWR-Index. Die Berechnung nutzt die vollständige verfügbare Kursreihe; die Chart-Verdichtung beeinflusst die Kennzahl nicht.",
  fiatFreeMode:"Fiat-freier Modus",fiatFreeValues:"Nur BTC und Sats anzeigen",fiatFreeHint:"Blendet Fiatwerte in Übersichten, Buchungen und Charts aus. Die Eingabefelder für Käufe bleiben erhalten, damit Berechnungen möglich sind.",showSatsPerFiat:"Kurs als Sats pro Fiat anzeigen",showSatsPerFiatHint:"Zeigt optional, wie viele Sats eine Einheit der gewählten Währung kauft.",satsPerFiat:"Sats pro Fiat",fiatHidden:"Fiat ausgeblendet",
  backupHealth:"Backup-Gesundheit",lastEncryptedBackup:"Letztes verschlüsseltes Backup",lastRestoreTest:"Letzter Wiederherstellungstest",backupAgeLimit:"Backup-Warnung nach",restoreTestAgeLimit:"Test-Erinnerung nach",markRestoreTest:"Wiederherstellungstest als erledigt markieren",backupHealthy:"Backup aktuell",backupStale:"Backup fehlt oder ist zu alt",restoreTestDue:"Wiederherstellungstest ist fällig",restoreTestCurrent:"Wiederherstellungstest aktuell",backupHealthSaved:"Backup-Erinnerungen gespeichert",restoreTestMarked:"Wiederherstellungstest gespeichert",daysUnit:"Tagen",neverStoreSeed:"Seed-Wörter, Passphrases und private Schlüssel niemals in dieser App oder im Backup speichern.",backupCreatedHealth:"Backup-Zeitpunkt wurde in der Gesundheitsanzeige erfasst.",
  currentBtcPurchasingPower:"Aktueller Kurs",purchaseCount:"Anzahl Käufe",fiatSecured:"Fiat in Sicherheit gebracht",lifetimePurchases:"Käufe insgesamt",finePriceSamples:"Adaptive Kurs-Samples",finePriceSamplesHint:"Einheitlich je Zeitraum: 1T 5 Min · 30T 1 Std · 90T 4 Std · YTD/1J 12 Std (Tages-Fallback) · länger einheitlich verdichtete Tagesdaten",enableDiscreetMode:"Diskret-Modus einschalten",disableDiscreetMode:"Diskret-Modus ausschalten",openHaMenu:"Home-Assistant-Menü öffnen"
});
Object.assign(I18N.en, {
  trueReturn:"True return",twr:"TWR",twrLong:"Time-weighted return",xirr:"XIRR p.a.",xirrLong:"Personal annualized return",twrHint:"TWR splits performance at every deposit and withdrawal and includes transaction fees. XIRR includes the timing and size of personal cash flows using the 365-day convention.",shortRangeXirr:"Annualized XIRR can be extremely volatile over short ranges.",cashflowAdjusted:"Cash-flow adjusted",unavailableReturn:"Unavailable",cashflowAdjustedChange:"Cash-flow adjusted",netStackChange:"Net change",endingBalance:"Ending balance",currentProfitLoss:"Current result",onOpenCostBasis:"On open cost basis",onInvestedCapital:"On invested capital",cumulativePurchaseOutlay:"Cumulative purchase outlay",ambiguousReturn:"Ambiguous",
  dcaAnalysis:"DCA analysis",purchasesInRange:"Purchases in range",weightedAveragePrice:"Weighted purchase price",averageSatsPerFiat:"Avg sats per fiat",investedFiat:"Invested fiat",feeRatio:"Fee ratio",breakEvenPrice:"Break-even price",bestPurchase:"Best purchase",worstPurchase:"Worst purchase",acquiredStack:"Purchased stack",differentCurrenciesOmitted:"Purchases in other currencies were excluded from fiat metrics.",noPurchasesRange:"No matching purchases in the selected range.",
  drawdownAnalysis:"Drawdown for selected range",periodHighDistance:"Distance from range high",maximumDrawdown:"Maximum drawdown",bitcoinDrawdown:"Bitcoin",portfolioDrawdown:"Portfolio · TWR adjusted",peak:"Peak",trough:"Trough",drawdownHint:"Portfolio drawdown uses a TWR index split at every cash flow. It is calculated from the full available price series, independent of display downsampling.",
  fiatFreeMode:"Fiat-free mode",fiatFreeValues:"Show BTC and sats only",fiatFreeHint:"Hides fiat values in summaries, ledger views, and charts. Purchase input fields remain available so calculations continue to work.",showSatsPerFiat:"Show price as sats per fiat",showSatsPerFiatHint:"Optionally shows how many sats one unit of the selected currency buys.",satsPerFiat:"Sats per fiat",fiatHidden:"Fiat hidden",
  backupHealth:"Backup health",lastEncryptedBackup:"Last encrypted backup",lastRestoreTest:"Last restore test",backupAgeLimit:"Backup warning after",restoreTestAgeLimit:"Restore-test reminder after",markRestoreTest:"Mark restore test complete",backupHealthy:"Backup is current",backupStale:"Backup is missing or stale",restoreTestDue:"Restore test is due",restoreTestCurrent:"Restore test is current",backupHealthSaved:"Backup reminders saved",restoreTestMarked:"Restore test recorded",daysUnit:"days",neverStoreSeed:"Never store seed words, passphrases, or private keys in this app or its backup.",backupCreatedHealth:"Backup creation time was recorded in backup health.",
  currentBtcPurchasingPower:"Current price",purchaseCount:"Purchase count",fiatSecured:"Fiat moved into Bitcoin",lifetimePurchases:"Lifetime purchases",finePriceSamples:"Adaptive price samples",finePriceSamplesHint:"Uniform by range: 1d 5 min · 30d 1 h · 90d 4 h · YTD/1y 12 h (daily fallback) · longer uniformly compacted daily data",enableDiscreetMode:"Enable discreet mode",disableDiscreetMode:"Disable discreet mode",openHaMenu:"Open Home Assistant menu"
});
Object.assign(I18N.de,{refreshChartPrices:"Kurse aktualisieren",refreshingChartPrices:"Kurse für diesen Zeitraum werden über Tor neu geladen …",chartPricesRefreshed:"Kursdaten aktualisiert",chartPriceRefreshFailed:"Kursaktualisierung fehlgeschlagen",chartDailyFallback:"12-h-Kerzen nicht verfügbar · einheitliche Tagesdaten werden verwendet",exactCandles:"Exakte Chart-Kerzen",historySyncRunning:"Historische Tagesdaten werden über Tor synchronisiert …"});
Object.assign(I18N.en,{refreshChartPrices:"Refresh prices",refreshingChartPrices:"Reloading prices for this range through Tor …",chartPricesRefreshed:"Price data refreshed",chartPriceRefreshFailed:"Price refresh failed",chartDailyFallback:"12h candles unavailable · uniform daily data is being used",exactCandles:"Exact chart candles",historySyncRunning:"Synchronizing historical daily data through Tor …"});
Object.assign(I18N.de,{chartMilestones:"Meilensteine",chartHalvings:"Halvings",milestoneMarker:"Meilenstein",halvingMarker:"Bitcoin-Halving",blockHeight:"Blockhöhe",halvingLoadError:"Halving-Daten konnten nicht geladen werden"});
Object.assign(I18N.en,{chartMilestones:"Milestones",chartHalvings:"Halvings",milestoneMarker:"Milestone",halvingMarker:"Bitcoin halving",blockHeight:"Block height",halvingLoadError:"Halving data could not be loaded"});
Object.assign(I18N.de,{bitcoinNetwork:"BITCOIN NETZWERK",moscowTime:"Moscow Time",satsPerUsd:"sats / USD",halvingCountdown:"Halving-Countdown",estimatedHalving:"Halving geschätzt",nextHalvingBlock:"Nächster Halving-Block",networkDataSource:"Netzwerkdaten",monthlySavingsOverall:"Ø Sparrate gesamt",personalSavingsYear:"Persönliches Jahr",ongoing:"laufend",monthsCount:"Monate",fromFirstEntry:"seit erster Buchung",blocksLabel:"Blöcke",perMonth:"/ Monat",tenMinuteEstimate:"≈ 10 Min/Block"});
Object.assign(I18N.en,{bitcoinNetwork:"BITCOIN NETWORK",moscowTime:"Moscow Time",satsPerUsd:"sats / USD",halvingCountdown:"Halving countdown",estimatedHalving:"Estimated halving",nextHalvingBlock:"Next halving block",networkDataSource:"Network data",monthlySavingsOverall:"Avg monthly savings overall",personalSavingsYear:"Personal year",ongoing:"ongoing",monthsCount:"months",fromFirstEntry:"since first entry",blocksLabel:"blocks",perMonth:"/ month",tenMinuteEstimate:"≈ 10 min/block"});
Object.assign(I18N.de,{spentAmount:"Ausgegeben / Einstand",purchaseFees:"Kaufgebühren",purchaseOutlay:"Fiat-Aufwand inkl. Gebühren",openBasisHint:"Nur noch offene FIFO-Lots · Kaufgebühren anteilig enthalten",fiatSecuredHint:"Summe aus BTC-Menge × Kaufpreis aller Käufe · Gebühren nicht als Bitcoin-Kauf gezählt",technicalLogMemory:"Technisches Core-Log · maximal 500 Einträge · keine Passwörter oder Buchungsinhalte"});
Object.assign(I18N.en,{spentAmount:"Spent / cost basis",purchaseFees:"Purchase fees",purchaseOutlay:"Fiat outlay incl. fees",openBasisHint:"Open FIFO lots only · allocated purchase fees included",fiatSecuredHint:"Sum of BTC amount × purchase price for all purchases · fees are not counted as Bitcoin purchases",technicalLogMemory:"Technical Core log · maximum 500 entries · no passwords or ledger contents"});
Object.assign(I18N.de,{edit:"Bearbeiten",editEntry:"Buchung bearbeiten",cancelEdit:"Bearbeiten abbrechen",saveChanges:"Änderungen speichern",entryUpdated:"Buchung aktualisiert",consumed:"FIFO zugeordnet",holdingReasonConsumed:"Diese Buchung ist vollständig durch spätere Verkäufe oder Ausgaben verbraucht und deshalb kein offenes Lot mehr.",holdingReasonCurrency:"Ungeklärt: Kauf und Verkauf verwenden unterschiedliche Fiatwährungen; für den realisierten Gewinn fehlt eine FX-Umrechnung.",holdingReasonUnknownCost:"Ungeklärt: Die verwendeten BTC stammen ganz oder teilweise aus Bestand ohne bekannten Einstandskurs.",holdingReasonInsufficient:"Ungeklärt: Zum Buchungszeitpunkt war nicht genügend früherer BTC-Bestand im Depot vorhanden.",holdingReasonUnknown:"Ungeklärt: Die FIFO-/Haltezeit-Zuordnung konnte für diese Buchung nicht vollständig bestimmt werden.",editTypeLocked:"Die Buchungsart bleibt beim Bearbeiten unverändert. Betrag, Kurs, Fiatwert, Fee, Datum, Depot und Notiz können korrigiert werden."});
Object.assign(I18N.en,{edit:"Edit",editEntry:"Edit entry",cancelEdit:"Cancel editing",saveChanges:"Save changes",entryUpdated:"Entry updated",consumed:"FIFO assigned",holdingReasonConsumed:"This entry has been fully consumed by later sales or expenses and is therefore no longer an open lot.",holdingReasonCurrency:"Unresolved: purchase and sale use different fiat currencies; an FX conversion is missing for realized gain.",holdingReasonUnknownCost:"Unresolved: the BTC used comes wholly or partly from stack entries without a known cost basis.",holdingReasonInsufficient:"Unresolved: there was not enough earlier BTC in the depot at the transaction timestamp.",holdingReasonUnknown:"Unresolved: FIFO/holding-period assignment could not be determined completely for this entry.",editTypeLocked:"The entry type stays unchanged while editing. Amount, price, fiat value, fee, timestamp, depot, and note can be corrected."});

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
  purchasePriceThen:"Kaufkurs damals",fifoCostBasis:"FIFO-Einstand",salePrice:"Verkaufskurs",saleProceeds:"Verkaufserlös",returnPercent:"Rendite",fifoSummary:"FIFO-Gesamtübersicht",soldAmount:"Verkaufte Menge",fifoCostBasisHint:"Damalige Anschaffungskosten der verkauften Sats inklusive anteiliger Kaufgebühren.",saleProceedsHint:"Nettoerlös nach anteiliger Verkaufsgebühr.",fifoCurrencyNote:"Fiat-Gesamtwerte für {currency}; andere Verkaufswährungen werden nicht umgerechnet.",fifoUnresolved:"Davon ohne bekannten FIFO-Einstand",
});
Object.assign(I18N.en, {
  purchasePriceThen:"Purchase price then",fifoCostBasis:"FIFO cost basis",salePrice:"Sale price",saleProceeds:"Sale proceeds",returnPercent:"Return",fifoSummary:"FIFO sales summary",soldAmount:"Amount sold",fifoCostBasisHint:"Original acquisition cost of the sold sats including allocated purchase fees.",saleProceedsHint:"Net proceeds after allocated sale fee.",fifoCurrencyNote:"Fiat totals for {currency}; other sale currencies are not converted.",fifoUnresolved:"Without known FIFO cost basis",
});

Object.assign(I18N.en, {
  deleteAllDialogTitle:"Delete all entries",deleteAllStepBackup:"Step 1 of 2 · Check backup",deleteAllBackupText:"Create a current encrypted backup before deleting. Without a backup, the ledger entries cannot be restored.",deleteAllBackupContinue:"Backup created – continue",deleteAllStepFinal:"Step 2 of 2 · Final warning",deleteAllFinalText:"All entered purchases, sales, expenses, and stack entries will be permanently deleted.",deleteAllAcknowledge:"I understand that all entered data will be permanently deleted.",deleteAllNow:"Permanently delete all entries",deleteAllWorking:"Deleting entries …",deleteAllFallback:"Compatibility mode: removing entries one by one.",deleteAllFailed:"The ledger entries could not be deleted completely.",tableHorizontalScroll:"Scroll table horizontally",csvImportStarting:"Starting import …",csvImporting:"Importing transactions …",csvImportFailed:"Import failed:",scrollTableLeft:"Scroll table left",scrollTableRight:"Scroll table right",
  goalReachedAt:"Goal reached on",milestoneReached:"Milestone reached",wavespacePhysicalCard:"Physical card",wavespaceVirtualCard:"Virtual card",wavespaceCardCreationFee:"Card creation fee",wavespaceCardPriceLocal:"Matched using local price data",wavespaceCardPriceCompared:"Matched by comparing BTC amounts",wavespaceCashWithdrawal:"Cash withdrawal",wavespaceCardPayment:"Card payment",
  autoLock:"Auto-lock",autoLockAfter:"Lock after inactivity",disabled:"Disabled",autoLockDisabled:"Core auto-lock is disabled for this unlocked HA session.",autoLockActive:"Core auto-lock active",autoLockTriggered:"Vault automatically locked because of inactivity.",browserSecretWarning:"Never reuse the master password as a seed, BIP39 passphrase, xprv, wallet password, or Nostr key. A compromised browser can read secrets while they are entered.",
  deleteEntryKicker:"REMOVE ENTRY",deleteEntryDialogTitle:"Delete entry",deleteEntryText:"Permanently delete this single ledger entry?",deleteEntryNow:"Permanently delete entry",deleteEntryWorking:"Deleting entry …",
  liveConnections:"Live connections & data sources",refreshConnections:"Refresh connections",refreshingConnections:"Refreshing …",connectionsRefreshed:"Connections and live prices refreshed",connectionsRefreshFailed:"Refresh failed",viewRefreshedAt:"View refreshed",livePriceRefreshedAt:"Live prices refreshed",livePriceAverage:"Current market average",sourcesUsed:"Sources used",transportPathTitle:"Public data route",transportPathText:"Home Assistant Core → internal SOCKS5 hop → Tor guard/circuit → Tor exit → HTTPS API. The tracker has no direct public Clearnet fallback.",transportExitNote:"The API connection after the Tor exit is outside your home network. The public provider sees the Tor exit IP, not your Home Assistant IP.",liveConnectionsHint:"Shows configured data sources, intended routes, observed requests, and currently visible transport sockets. Visible only to the portfolio owner.",livePriceSources:"Live price sources",historySources:"Historical price sources",systemSources:"System and Tor checks",observedConnections:"Observed network targets",transportConnections:"Current transport connections",connectionPath:"Route",connectionTarget:"Target",connectionStatus:"Status",connectionPurpose:"Purpose",connectionActive:"ACTIVE",connectionReady:"Ready / last used",connectionConfigured:"Configured",connectionNever:"Not observed yet",connectionNoData:"No connection entries available.",routeTor:"Tor · SOCKS5 · remote DNS",routeLocal:"Direct · private/local networks only",routeHaLocal:"Home Assistant internal · no public egress",routeTorRelay:"Tor process → guard/relay · encrypted Tor transport",routeBlocked:"NOT ALLOWED · direct Clearnet egress",purposeLivePrice:"Live price",purposeHistory:"History",purposeInternal:"Home Assistant Core / actions",purposeObserved:"Observed network request",purposeTorCheck:"Tor exit verification",purposeTorTransport:"Tor relay transport",purposeBlocked:"Non-Tor connection",browserIngress:"Browser → Home Assistant Core",coreBridge:"Native Bitcoin panel → Home Assistant Core",bundledTor:"Home Assistant Core → separate Tor gateway",connectionVersions:"Versions",connectionOwnerOnly:"Connection details are visible only to the portfolio owner.",connectionCompatFallback:"Compatibility mode: connection data is reconstructed from the normal dashboard status.",connectionVersionMismatch:"The panel and integration versions differ. Fully update the custom integration and restart Home Assistant.",unlockHardened:"Hardened secret path: master and backup passwords, CSV files, and vault data go directly from the native Home Assistant panel to Home Assistant Core. The Tor gateway is not in this data path and has no Home Assistant API token.",cryptoKdf:"Password KDF",cryptoMemory:"KDF memory",cryptoProfileCurrent:"Current hardened profile",cryptoProfileOld:"Older profile – automatically upgraded after a successful unlock",cryptoEnvelope:"Key architecture",cryptoDataKey:"Vault data key",cryptoKeyWrap:"DEK key wrap",cryptoDeviceBinding:"Device binding",cryptoNonceNote:"GCM IV/nonce (not a key)",cryptoDeviceBound:"Separate 256-bit Core device key",cryptoPortableNote:"Portable backups are intentionally not device-bound"
});

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
  return Date.parse(raw.length === 10 ? `${raw}T00:00:00Z` : raw);
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
function displayDaysForRange() {
  if (state.historyRange === "max" || state.historyRange === "first_purchase") return 0;
  if (state.historyRange === "1") return 1;
  if (state.historyRange === "ytd") {
    const now = new Date(), today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const yearStart = Date.UTC(now.getUTCFullYear(), 0, 1);
    return Math.floor((today - yearStart) / 86400000) + 1;
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
  if (state.historyRange === "30") return 60;
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
  else if (state.activeTab === "ledger") renderLedger();
  else if (state.activeTab === "structure") { renderDepots(); if (!state.discreet) renderGoalsEditor(); }
  else if (state.activeTab === "tax") renderTax();
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
  if (store) localStorage.setItem("bst_active_tab", selected);
  if (render && state.data && !state.data.locked) renderActiveTabContent(selected);
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
    renderChart();
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
  state.data = await api(`api/dashboard?entry_id=${encodeURIComponent(state.entryId)}&history_days=${historyDaysForRange()}&history_interval=${chartIntervalMinutesForRange()}`);
  state.securityUsers = [];
  state.connectionInventory = state.data?.connection_inventory || state.connectionInventory;
  if (state.data?.addon_network) {
    state.network = state.data.addon_network;
  } else if (!state.network) {
    state.network = {tor_connection_state:"connecting",tor_verified:false};
  }
  renderNetworkStatus();
  // Dashboard data already contains the latest known network snapshot. Refresh
  // the live Tor status in the background so ledger/chart interaction is not
  // blocked by an extra request after every save or unlock.
  void refreshNetworkStatus({silent:true});
  if (state.data.locked) {
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
  void ensureIntradayHistory();
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
function depotName(id) { return state.data.depots.find(item => item.id === id)?.name || id; }
function entryHoldingDetails(entry) {
  const fifo=state.data?.fifo||{};
  if (entry.type === "sale") {
    const sale=fifo.sales?.[entry.id]||{}, matches=(fifo.matches||[]).filter(item=>item.sale_id===entry.id);
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
  const lot=fifo.open_lots?.find(item=>item.entry_id===entry.id);
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
  else if (selected === "ledger") renderLedger();
  else if (selected === "structure") { renderDepots(); if (!state.discreet) renderGoalsEditor(); }
  else if (selected === "tax") renderTax();
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
  const purchases = (state.data?.entries || []).filter(entry =>
    entry?.type === "purchase" && String(entry?.currency || "").toUpperCase() === String(currency || "").toUpperCase()
  );
  const result = purchases.reduce((summary, entry) => {
    const amount = Number(entry?.amount_btc || 0), price = Number(entry?.price || 0), fee = Number(entry?.fee || 0);
    if (Number.isFinite(amount) && amount > 0 && Number.isFinite(price) && price > 0) {
      summary.fiat += amount * price;
      summary.btc += amount;
      summary.count += 1;
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
  const secured = lifetimeFiatSecured(currency);
  const cards = [
    [t("totalStack"), fmtStack(total), state.unit === "BTC" ? `${fmtNumber(total * SATS_PER_BTC,0)} sats` : `${fmtNumber(total,8)} BTC`, ""],
    [t("totalValue"), fmtFiat(value,currency), `${fmtFiat(rawPrice,currency)} / BTC`, ""],
    [t("openBasis"), fmtFiat(invested,currency), `${fmtStack(known)} · ${t("openBasisHint")}`, ""],
    [t("unrealized"), fmtFiat(unrealized,currency), `${t("realized")}: ${fmtFiat(realized,currency)}`, unrealized > 0 ? "positive" : unrealized < 0 ? "negative" : ""],
    [t("fiatSecured"), fmtFiat(secured.fiat,currency), `${t("purchaseFees")}: ${fmtFiat(secured.fees,currency)} · ${t("purchaseOutlay")}: ${fmtFiat(secured.totalOutlay,currency)}`, ""]
  ];
  $("#summaryCards").innerHTML = cards.map(([label,value,sub,css]) => `<article class="metric-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong><small>${privateHtml(sub)}</small></article>`).join("");
  $("#heroLong").textContent = privateText(fmtStack(fifo.long_term_btc));
  const nextGoal = (data.goals || []).filter(goal => Number(goal.remaining_btc) > 0).sort((a,b) => Number(a.remaining_btc) - Number(b.remaining_btc))[0];
  $("#heroGoal").textContent = nextGoal ? `${nextGoal.name}: ${privateText(fmtStack(nextGoal.remaining_btc))}` : "✓";
  $("#heroText").textContent = state.lang === "de"
    ? `Lokales Kauf- und Verkaufsbuch mit depotweisem FIFO, ${data.tax_settings.long_term_days} Tagen Haltezeit-Regel und dauerhaft gespeichertem Tagesverlauf.`
    : `Local purchase and sale ledger with per-depot FIFO, a ${data.tax_settings.long_term_days}-day holding rule, and durable daily history.`;
  renderChart();
  renderGoalCards();
}

function goalReachedAtFromEntries(goal) {
  const target = Number(goal?.amount_btc || 0);
  if (!(target > 0)) return null;
  const scope = String(goal?.depot_id || "all");
  const rows = (Array.isArray(state.data?.entries) ? state.data.entries : [])
    .filter(row => scope === "all" || String(row?.depot_id || "main") === scope)
    .map(row => ({
      row,
      time: new Date(row?.timestamp || "").getTime(),
      outgoing: ["sale", "expense"].includes(String(row?.type || ""))
    }))
    .filter(item => Number.isFinite(item.time))
    .sort((a, b) => a.time - b.time || Number(a.outgoing) - Number(b.outgoing) || String(a.row?.id || "").localeCompare(String(b.row?.id || "")));
  let balance = 0;
  for (const item of rows) {
    const amount = Math.max(0, Number(item.row?.amount_btc || 0));
    if (["purchase", "stack"].includes(String(item.row?.type || ""))) balance += amount;
    else if (["sale", "expense"].includes(String(item.row?.type || ""))) balance -= amount;
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
  const entries = Array.isArray(state.data?.entries) ? state.data.entries : [];
  const validDay = entry => {
    const timestamp = chartTimestamp(entry?.timestamp);
    return Number.isFinite(timestamp) ? new Date(timestamp).toISOString().slice(0,10) : null;
  };
  const purchaseDays = entries
    .filter(entry => entry?.type === "purchase")
    .map(validDay)
    .filter(Boolean)
    .sort();
  if (purchaseDays.length) return purchaseDays[0];
  const bookingDays = entries.map(validDay).filter(Boolean).sort();
  return bookingDays[0] || null;
}
function filterSeriesToSelectedStart(values) {
  let entries = Object.entries(values || {});
  const now = Date.now();
  if (state.historyRange === "1") {
    const cutoff = now - 24 * 60 * 60 * 1000;
    entries = entries.filter(([day]) => chartTimestamp(day) >= cutoff);
  } else if (state.historyRange === "ytd") {
    const current = new Date(), cutoff = Date.UTC(current.getUTCFullYear(), 0, 1);
    entries = entries.filter(([day]) => chartTimestamp(day) >= cutoff);
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
  const entries = (state.data?.entries || [])
    .map(entry => ({entry,time:chartTimestamp(entry?.timestamp),amount:Number(entry?.amount_btc || 0)}))
    .filter(item => Number.isFinite(item.time) && Number.isFinite(item.amount) && item.amount > 0)
    .sort((a,b)=>a.time-b.time);
  const points = sortedNumericPoints(priceSeries), stackBtc = {}, portfolio = {};
  let position = 0, stack = 0, started = false;
  for (const point of points) {
    const timestamp = seriesValuationTimestamp(point.day);
    while (position < entries.length && entries[position].time <= timestamp) {
      const {entry,amount} = entries[position];
      if (entry.type === "purchase" || entry.type === "stack") stack += amount;
      else if (entry.type === "sale" || entry.type === "expense") stack -= amount;
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
  const entries = (state.data?.entries || [])
    .map((entry,index) => ({entry,index,time:chartTimestamp(entry?.timestamp)}))
    .filter(item => Number.isFinite(item.time))
    .sort((left,right) => left.time-right.time
      || Number(["sale","expense"].includes(left.entry?.type))-Number(["sale","expense"].includes(right.entry?.type))
      || String(left.entry?.id || "").localeCompare(String(right.entry?.id || ""))
      || left.index-right.index);
  const lotsByDepot = new Map();
  let realized = 0;
  const result = [];
  const metricState = () => {
    let basis = 0, knownBtc = 0;
    for (const lots of lotsByDepot.values()) {
      for (const lot of lots) {
        if (lot.currency !== selectedCurrency || !(lot.remaining > 0) || !(lot.unitBasis >= 0)) continue;
        basis += lot.remaining * lot.unitBasis;
        knownBtc += lot.remaining;
      }
    }
    return {basis,realized,knownBtc};
  };
  let sequence = 0;
  for (const item of entries) {
    const entry = item.entry || {}, kind = String(entry.type || ""), depot = String(entry.depot_id || "main");
    const amount = Math.max(0,Number(entry.amount_btc || 0));
    if (!(amount > 0)) continue;
    const lots = lotsByDepot.get(depot) || [];
    lotsByDepot.set(depot,lots);
    if (kind === "purchase" || kind === "stack") {
      if (kind === "purchase") {
        const price = Number(entry.price), fee = Math.max(0,Number(entry.fee || 0));
        const entryCurrency = String(entry.currency || "").toUpperCase();
        const unitBasis = Number.isFinite(price) && price > 0 ? (amount * price + (Number.isFinite(fee) ? fee : 0)) / amount : null;
        lots.push({remaining:amount,currency:entryCurrency,unitBasis});
      } else {
        lots.push({remaining:amount,currency:null,unitBasis:null});
      }
    } else if (kind === "sale" || kind === "expense") {
      let remaining = amount;
      const saleCurrency = String(entry.currency || "").toUpperCase();
      const salePrice = Number(entry.price), saleFee = Math.max(0,Number(entry.fee || 0));
      for (const lot of lots) {
        if (!(remaining > 1e-15)) break;
        if (!(lot.remaining > 0)) continue;
        const take = Math.min(remaining,lot.remaining);
        if (kind === "sale" && lot.currency === selectedCurrency && saleCurrency === selectedCurrency && Number.isFinite(salePrice) && salePrice > 0 && Number.isFinite(lot.unitBasis)) {
          const feeShare = Number.isFinite(saleFee) ? saleFee * (take / amount) : 0;
          realized += take * salePrice - feeShare - take * lot.unitBasis;
        }
        lot.remaining -= take;
        remaining -= take;
      }
    }
    const stateAfter = metricState();
    const key = new Date(item.time + sequence).toISOString();
    result.push({time:item.time,key,...stateAfter});
    sequence = (sequence + 1) % 997;
  }
  return result;
}

function chartValues(currency, analytics = false) {

  const history = state.data.history || {}, chart = history.chart || {}, fifo = state.data.fifo || {};
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

  const lots = (fifo.open_lots || []).filter(lot => String(lot.currency || "").toUpperCase() === String(currency).toUpperCase());
  const invested = lots.reduce((sum,lot)=>sum + Number(lot.remaining_btc || 0) * Number(lot.unit_basis || 0),0);
  const knownBtc = lots.reduce((sum,lot)=>sum + Number(lot.remaining_btc || 0),0);
  const realizedNow = Number(fifo.realized?.[currency] || 0);

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

  return {price,portfolio,totalProfitLoss,unrealizedProfitLoss,realizedProfitLoss,costBasis,stackBtc};
}

function analyticsValues(currency) { return chartValues(currency,true); }

function seriesChange(values) {
  const points = Object.entries(values || {})
    .filter(([day,value]) => Number.isFinite(chartTimestamp(day)) && Number.isFinite(Number(value)))
    .sort(([left],[right]) => chartTimestamp(left) - chartTimestamp(right));
  if (points.length < 2) return null;
  const [startDay,startRaw] = points[0], [endDay,endRaw] = points.at(-1);
  const start = Number(startRaw), end = Number(endRaw), absolute = end - start;
  const percent = start === 0 ? null : absolute / Math.abs(start) * 100;
  return {startDay,endDay,start,end,absolute,percent};
}

function compactAxis(value) {
  return new Intl.NumberFormat(state.lang === "de" ? "de-DE" : "en-US", {notation:"compact",maximumFractionDigits:1}).format(Number(value));
}
function updateChartScaleButton(disabled = false) {
  const button = $("#chartScaleButton");
  const label = state.chartScale === "log" ? t("logarithmic") : t("linear");
  $("#chartScaleText").textContent = label;
  button.disabled = disabled;
  button.classList.toggle("is-disabled", disabled);
  button.title = disabled ? t("logUnavailable") : `${t("scale")}: ${label}`;
  button.setAttribute("aria-label", button.title);
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
  const milestoneMap = goalMilestonesByEntryId();
  const events = [];
  for (const entry of (state.data?.entries || [])) {
    const goals = milestoneMap.get(String(entry?.id || "")) || [];
    if (!goals.length) continue;
    const timestamp = chartTimestamp(entry?.timestamp);
    if (!Number.isFinite(timestamp)) continue;
    events.push({
      kind: "milestone",
      timestamp,
      icon: "★",
      label: goals.map(goal => `${goal.name} · ${fmtStack(goal.amount_btc)}`).join(" · "),
    });
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

function renderChart() {
  updateChartMarkerButtons();
  const currency = currentCurrency(), mode = $("#chartMode").value || state.chartMode;
  state.chartMode = mode;
  localStorage.setItem("bst_chart_mode",mode);
  const series = chartSeries(mode,currency);
  renderChartLegend(series);
  const overlay = series.length > 1;
  const signedSeries = series.some(item => item.allowNegative);
  if (signedSeries && state.chartScale === "log") {
    state.chartScale = "linear";
    localStorage.setItem("bst_chart_scale","linear");
  }
  updateChartScaleButton(signedSeries);
  const logarithmic = !signedSeries && state.chartScale === "log";
  $("#overlayOpacity").disabled = !overlay;
  $("#opacityControl").classList.toggle("is-inactive", !overlay);
  const usable = value => Number.isFinite(Number(value)) && (!logarithmic || Number(value) > 0);
  const dates = [...new Set(series.flatMap(item => Object.keys(item.values || {})))]
    .filter(day => Number.isFinite(chartTimestamp(day))).sort((left,right) => chartTimestamp(left) - chartTimestamp(right));
  const element = $("#priceChart");
  renderPerformanceSummary(currency);
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
  const transform = value => logarithmic ? Math.log10(Number(value)) : Number(value);
  const inverse = value => logarithmic ? 10 ** Number(value) : Number(value);
  const getExtent = item => {
    const values = dates.map(day => item.values[day]).filter(usable).map(transform);
    let min=Math.min(...values),max=Math.max(...values);
    if(!Number.isFinite(min)||!Number.isFinite(max)){min=0;max=1;}
    if(min===max){min-=.05;max+=.05;}
    const padding=(max-min)*.06;
    if (logarithmic) return [min-padding,max+padding];
    return item.allowNegative ? [min-padding,max+padding] : [Math.max(0,min-padding),max+padding];
  };
  const extents = series.map(getExtent);
  const y = (value,index) => { const [min,max]=extents[index], mapped=transform(value); return pad.t + (1-(mapped-min)/(max-min))*plotHeight; };

  // Final render guard only. The durable fine-price cache is already adaptive:
  // today/very recent = dense, then 30m -> 2h -> 12h -> daily for long ranges.
  // This prevents minute-level data from ever leaking into 10-year/Max charts.
  const requestedChartDays = historyDaysForRange();
  const maxVisiblePoints = requestedChartDays > 0 && requestedChartDays <= 366 ? (mobileChart ? 2200 : 3600) : 1800;
  const step = Math.max(1,Math.ceil(dates.length/maxVisiblePoints));
  const displayDates = dates.filter((_,index)=>index===0||index===dates.length-1||index%step===0);
  const pointRows = (item,index) => displayDates
    .filter(day => usable(item.values[day]))
    .map(day => ({day,x:xDay(day),y:y(item.values[day],index)}));
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
  const axisValue = (extent,fraction) => inverse(extent[1]-fraction*(extent[1]-extent[0]));
  const grid = [0,.25,.5,.75,1].map(fraction => {
    const yy=pad.t+fraction*plotHeight, value=axisValue(extents[0],fraction);
    return `<line class="grid" x1="${pad.l}" y1="${yy}" x2="${width-pad.r}" y2="${yy}"/><text class="axis-text" x="8" y="${yy+4}">${privateHtml(compactAxis(value))}</text>`;
  }).join("");
  const rightAxis = overlay ? [0,.25,.5,.75,1].map(fraction => { const yy=pad.t+fraction*plotHeight,value=axisValue(extents[1],fraction); return `<text class="axis-text" x="${width-4}" y="${yy+4}" text-anchor="end">${privateHtml(compactAxis(value))}</text>`; }).join("") : "";
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
  const zeroLines = series.map((item,index) => {
    if (!item.allowNegative || logarithmic) return "";
    const [min,max] = extents[index];
    if (min > 0 || max < 0) return "";
    const yy = y(0,index);
    return `<line class="zero-line ${index ? "secondary-zero" : ""}" x1="${pad.l}" y1="${yy}" x2="${width-pad.r}" y2="${yy}"/>`;
  }).join("");
  element.innerHTML = `<svg class="${mobileChart ? "mobile-chart-svg" : ""}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(series.map(item=>item.label).join(" + "))}">
    <defs><linearGradient id="areaPrimary" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7931a" stop-opacity=".32"/><stop offset="1" stop-color="#f7931a" stop-opacity="0"/></linearGradient></defs>
    ${grid}${rightAxis}${zeroLines}${markerSvg}${area?`<polygon class="area-primary" points="${area}"/>`:""}<polyline class="series-primary" points="${primaryPoints}"/>${secondary}${dateLabels}
    <text class="axis-text" x="${pad.l}" y="18">${esc(series[0].label)} · ${esc(logarithmic?t("logarithmic"):t("linear"))}</text>${overlay?`<text class="axis-text" x="${width-pad.r}" y="18" text-anchor="end">${esc(series[1].label)}</text>`:""}
    <line id="crossX" class="crosshair hidden" x1="0" y1="${pad.t}" x2="0" y2="${height-pad.b}"/><line id="crossY" class="crosshair hidden" x1="${pad.l}" y1="0" x2="${width-pad.r}" y2="0"/>
    <circle id="crossDotA" class="cross-dot hidden" r="5" stroke="#f7931a"/><circle id="crossDotB" class="cross-dot hidden" r="5" stroke="#66d19e"/>
    <rect id="chartHit" class="chart-hit" x="${pad.l}" y="${pad.t}" width="${plotWidth}" height="${plotHeight}"/>
  </svg>`;
  const hit=$("#chartHit",element), crossX=$("#crossX",element), crossY=$("#crossY",element), dotA=$("#crossDotA",element), dotB=$("#crossDotB",element), tooltip=$("#chartTooltip");
  const hide=()=>{[crossX,crossY,dotA,dotB].forEach(node=>node?.classList.add("hidden"));tooltip.classList.add("hidden");};
  hit.addEventListener("pointerleave",hide);
  hit.addEventListener("pointermove",event=>{
    const rect=hit.getBoundingClientRect(), fraction=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)), index=nearestDateIndex(minTime+fraction*timeSpan), day=dates[index], xPos=xDay(day);
    const primary=Number(series[0].values[day]), secondaryValue=overlay?Number(series[1].values[day]):NaN;
    if(!usable(primary)){hide();return;}
    const yPos=y(primary,0);
    crossX.setAttribute("x1",xPos);crossX.setAttribute("x2",xPos);crossX.classList.remove("hidden");
    crossY.setAttribute("y1",yPos);crossY.setAttribute("y2",yPos);crossY.classList.remove("hidden");
    dotA.setAttribute("cx",xPos);dotA.setAttribute("cy",yPos);dotA.classList.remove("hidden");
    if(overlay&&usable(secondaryValue)){dotB.setAttribute("cx",xPos);dotB.setAttribute("cy",y(secondaryValue,1));dotB.classList.remove("hidden");}else dotB.classList.add("hidden");
    const nearbyMarkers = markerEvents.filter(item => Math.abs(item.x - xPos) <= 10);
    const markerDetails = nearbyMarkers.map(item => `<div class="chart-tooltip-event ${esc(item.kind)}"><span aria-hidden="true">${esc(item.icon)}</span>${esc(item.label)}</div>`).join("");
    tooltip.innerHTML=`<strong>${esc(fmtChartPoint(day,intradayAxis))}</strong><div><span class="chart-tooltip-dot primary" aria-hidden="true"></span>${esc(series[0].label)}: ${privateHtml(series[0].format(primary))}</div>${overlay&&usable(secondaryValue)?`<div><span class="chart-tooltip-dot secondary" aria-hidden="true"></span>${esc(series[1].label)}: ${privateHtml(series[1].format(secondaryValue))}</div>`:""}${markerDetails}`;
    tooltip.classList.remove("hidden");
    const panelRect=element.closest(".chart-panel").getBoundingClientRect(),desiredLeft=event.clientX-panelRect.left+14,maxLeft=panelRect.width-tooltip.offsetWidth-12;
    tooltip.style.left=`${Math.max(10,Math.min(maxLeft,desiredLeft))}px`;
    tooltip.style.top=`${Math.max(70,event.clientY-panelRect.top-tooltip.offsetHeight-15)}px`;
  });
}

function ledgerTypeClass(type) {
  const value = String(type || "").toLowerCase();
  return ["purchase", "sale", "stack", "expense"].includes(value) ? `ledger-type-${value}` : "ledger-type-other";
}

function goalMilestonesByEntryId() {
  const result = new Map();
  if (state.discreet) return result;
  for (const goal of sortedStackingGoals()) {
    const target = Number(goal?.amount_btc || 0);
    if (!(target > 0)) continue;
    const scope = String(goal?.depot_id || "all");
    const rows = (Array.isArray(state.data?.entries) ? state.data.entries : [])
      .filter(row => scope === "all" || String(row?.depot_id || "main") === scope)
      .map(row => ({row,time:new Date(row?.timestamp || "").getTime(),outgoing:["sale","expense"].includes(String(row?.type || ""))}))
      .filter(item => Number.isFinite(item.time))
      .sort((a,b) => a.time - b.time || Number(a.outgoing) - Number(b.outgoing) || String(a.row?.id || "").localeCompare(String(b.row?.id || "")));
    let balance = 0;
    for (const item of rows) {
      const amount = Math.max(0, Number(item.row?.amount_btc || 0));
      if (["purchase","stack"].includes(String(item.row?.type || ""))) balance += amount;
      else if (["sale","expense"].includes(String(item.row?.type || ""))) balance -= amount;
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
    const totalLabel=Number.isFinite(controlTotal)&&controlTotal>0?fmtFiat(controlTotal,entry.currency):"–",feeLabel=entry.fee?fmtFiat(Number(entry.fee||0),entry.currency):"–";
    const typeClass=ledgerTypeClass(entry.type), detail=ledgerDetailHtml(entry,milestoneMap.get(String(entry.id)) || []);
    return `<tr class="ledger-entry-row ${typeClass}"><td class="ledger-date-cell">${esc(fmtDate(entry.timestamp))}</td><td><span class="badge ledger-type-badge">${esc(t(entry.type) || entry.type)}</span></td><td><code>${privateHtml(fmtStack(entry.amount_btc))}</code></td><td>${privateHtml(price)}</td><td>${privateHtml(totalLabel)}</td><td>${privateHtml(feeLabel)}</td><td>${esc(depotName(entry.depot_id))}</td><td>${entryHoldingHtml(entry)}${sale?`<br><small>${privateHtml(fmtStack(sale.long_term_btc))} L / ${privateHtml(fmtStack(sale.short_term_btc))} S</small>`:""}</td><td><div class="ledger-row-actions"><button class="secondary compact edit-entry" type="button" data-id="${esc(entry.id)}" aria-label="${esc(t("edit"))}" title="${esc(t("edit"))}">✎</button><button class="danger compact delete-entry" type="button" data-id="${esc(entry.id)}" aria-label="${esc(t("delete"))}" title="${esc(t("delete"))}">×</button></div></td></tr>${detail ? `<tr class="ledger-note-row ${typeClass}"><td class="ledger-note-date-spacer" aria-hidden="true"></td><td colspan="8"><div class="ledger-entry-details">${detail}</div></td></tr>` : ""}`;
  }).join("");
  const cards = $("#ledgerCards");
  if (cards) {
    cards.innerHTML = !compactLayout ? "" : (entries.length ? entries.map(entry => {
      const sale=state.data.fifo.sales?.[entry.id], price=entry.price?(entry.type==="expense"?`${fmtNumber(Number(entry.amount_btc||0)*Number(entry.price||0),2)} ${entry.currency}`:`${fmtNumber(entry.price,2)} ${entry.currency}`):"–", holding=entryHolding(entry);
      const controlTotal=entry.price?transactionFiatTotal(entry.type,Number(entry.amount_btc||0),Number(entry.price||0),Number(entry.fee||0)):NaN;
      const totalLabel=Number.isFinite(controlTotal)&&controlTotal>0?fmtFiat(controlTotal,entry.currency):"–",feeLabel=entry.fee?fmtFiat(Number(entry.fee||0),entry.currency):"–";
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
  $("#depotList").innerHTML = state.data.depots.map(depot => { const summary=state.data.depot_summaries.find(item=>item.id===depot.id)||{},canDelete=depot.id!=="main"&&!(state.data.entries||[]).some(entry=>entry.depot_id===depot.id);return `<div class="list-item"><div><strong>${esc(depot.name)}</strong><div class="meta">${esc(depot.id)} · ${privateHtml(fmtStack(summary.total_btc||0))} · ${esc(t("longTerm"))}: ${privateHtml(fmtStack(summary.long_term_btc||0))}</div></div>${canDelete?`<button class="danger delete-depot" data-id="${esc(depot.id)}">${esc(t("delete"))}</button>`:""}</div>`; }).join("");
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
  const note=t("fifoCurrencyNote").replace("{currency}",currency);
  host.innerHTML=`<article class="aggregate-depot-card fifo-summary-card">
    <div class="aggregate-depot-head"><div><span class="kicker">FIFO SALES · ${esc(currency)}</span><h3>${esc(t("fifoSummary"))}</h3></div><span class="badge">${fmtNumber(currencyMatches.length,0)} FIFO</span></div>
    <div class="aggregate-depot-grid fifo-summary-grid">
      <div><span>${esc(t("soldAmount"))}</span><strong>${privateHtml(state.unit==="sats"?`${fmtNumber(soldBtc*SATS_PER_BTC,0)} sats`:`${fmtNumber(soldBtc,8)} BTC`)}</strong><small>${unresolvedBtc>0?`${esc(t("fifoUnresolved"))}: ${privateHtml(fmtStack(unresolvedBtc))}`:"FIFO"}</small></div>
      <div class="fifo-fiat-metric"><span>${esc(t("fifoCostBasis"))}</span><strong>${privateHtml(fmtFiat(basis,currency))}</strong><small>${esc(t("fifoCostBasisHint"))}</small></div>
      <div class="fifo-fiat-metric"><span>${esc(t("saleProceeds"))}</span><strong>${privateHtml(fmtFiat(proceeds,currency))}</strong><small>${esc(t("saleProceedsHint"))}</small></div>
      <div class="fifo-fiat-metric"><span>${esc(t("gain"))}</span><strong class="${gainClass}">${privateHtml(signedFiat(gain,currency))}</strong><small>${roi==null?"–":privateHtml(signedPercent(roi))}</small></div>
    </div>
    ${currencies.length>1?`<p class="storage-note fifo-summary-note">${esc(note)}</p>`:""}
  </article>`;
}
function renderTax() {
  const fifo=state.data.fifo,stats=[[t("longTerm"),fmtStack(fifo.long_term_btc)],[t("shortTerm"),fmtStack(fifo.short_term_btc)],[t("unknown"),fmtStack(fifo.unknown_holding_btc)],[t("nextLong"),fifo.next_long_term_date?`${fmtDate(fifo.next_long_term_date)} · ${fmtStack(fifo.next_long_term_btc)}`:"–"]];
  $("#taxSummary").innerHTML=stats.map(([label,value])=>`<div class="tax-stat"><span>${esc(label)}</span><strong>${privateHtml(value)}</strong></div>`).join("");
  const allMatches=(fifo.matches||[]).slice().reverse();
  renderFifoSaleSummary(allMatches);
  const pageSize=Math.max(10,Number(state.ledgerPageSize)||25);
  const totalPages=Math.max(1,Math.ceil(allMatches.length/pageSize));
  state.fifoPage=Math.min(Math.max(1,state.fifoPage),totalPages);
  const pageStart=(state.fifoPage-1)*pageSize;
  const pageEnd=Math.min(allMatches.length,pageStart+pageSize);
  const matches=allMatches.slice(pageStart,pageEnd);
  const entryById=new Map((state.data.entries||[]).map(entry=>[String(entry.id),entry]));
  const rowData=match=>{
    const purchase=match.purchase_id==null?null:entryById.get(String(match.purchase_id));
    const sale=match.sale_id==null?null:entryById.get(String(match.sale_id));
    const purchaseCurrency=String(match.purchase_currency||purchase?.currency||match.sale_currency||"").toUpperCase();
    const saleCurrency=String(match.sale_currency||sale?.currency||"").toUpperCase();
    const purchasePrice=Number(purchase?.price);
    const salePrice=Number(sale?.price);
    const gain=match.realized_gain==null?null:Number(match.realized_gain);
    const basis=match.cost_basis==null?null:Number(match.cost_basis);
    const roi=basis!=null&&basis>0&&gain!=null?(gain/basis)*100:null;
    return {purchase,sale,purchaseCurrency,saleCurrency,purchasePrice,salePrice,gain,basis,roi};
  };
  const compactLayout=compactTableLayout();
  $("#fifoBody").innerHTML=compactLayout?"":matches.map(match=>{
    const d=rowData(match),gainClass=d.gain>0?"positive":d.gain<0?"negative":"";
    const purchasePrice=Number.isFinite(d.purchasePrice)&&d.purchasePrice>0?`${fmtFiat(d.purchasePrice,d.purchaseCurrency)} / BTC`:"–";
    const salePrice=Number.isFinite(d.salePrice)&&d.salePrice>0?`${fmtFiat(d.salePrice,d.saleCurrency)} / BTC`:"–";
    return `<tr><td>${esc(fmtDate(match.sale_timestamp))}</td><td>${privateHtml(fmtStack(match.amount_btc))}</td><td>${privateHtml(purchasePrice)}${match.purchase_timestamp?`<br><small>${esc(fmtDate(match.purchase_timestamp))}</small>`:""}</td><td>${d.basis==null?"–":privateHtml(fmtFiat(d.basis,d.saleCurrency))}</td><td>${privateHtml(salePrice)}</td><td>${match.net_proceeds==null?"–":privateHtml(fmtFiat(match.net_proceeds,d.saleCurrency))}</td><td class="${gainClass}">${d.gain==null?"–":privateHtml(signedFiat(d.gain,d.saleCurrency))}</td><td class="${gainClass}">${d.roi==null?"–":privateHtml(signedPercent(d.roi))}</td></tr>`;
  }).join("");
  const fifoCards=$("#fifoCards");
  if(fifoCards)fifoCards.innerHTML=!compactLayout?"":(matches.length?matches.map(match=>{
    const d=rowData(match),gainClass=d.gain>0?"positive":d.gain<0?"negative":"";
    const purchasePrice=Number.isFinite(d.purchasePrice)&&d.purchasePrice>0?`${fmtFiat(d.purchasePrice,d.purchaseCurrency)} / BTC`:"–";
    const salePrice=Number.isFinite(d.salePrice)&&d.salePrice>0?`${fmtFiat(d.salePrice,d.saleCurrency)} / BTC`:"–";
    return `<article class="ledger-mobile-card">
      <div class="ledger-mobile-head"><div><span class="badge">${esc(match.status)}</span><strong>${esc(fmtDate(match.sale_timestamp))}</strong></div>${badge(match.holding_status)}</div>
      <dl>
        <div><dt>${esc(t("amount"))}</dt><dd>${privateHtml(fmtStack(match.amount_btc))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("purchasePriceThen"))}</dt><dd>${privateHtml(purchasePrice)}${match.purchase_timestamp?`<small>${esc(fmtDate(match.purchase_timestamp))}</small>`:""}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("fifoCostBasis"))}</dt><dd>${d.basis==null?"–":privateHtml(fmtFiat(d.basis,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("salePrice"))}</dt><dd>${privateHtml(salePrice)}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("saleProceeds"))}</dt><dd>${match.net_proceeds==null?"–":privateHtml(fmtFiat(match.net_proceeds,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("gain"))}</dt><dd class="${gainClass}">${d.gain==null?"–":privateHtml(signedFiat(d.gain,d.saleCurrency))}</dd></div>
        <div class="fifo-fiat-metric"><dt>${esc(t("returnPercent"))}</dt><dd class="${gainClass}">${d.roi==null?"–":privateHtml(signedPercent(d.roi))}</dd></div>
      </dl>
    </article>`;
  }).join(""):`<p class="storage-note">${esc(t("noData"))}</p>`);
  renderFifoPagination(allMatches.length,totalPages,pageStart,pageEnd);
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
      const fallback=resampleLongRangeUniform(history.prices?.[selectedCurrency]||{});
      $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: ${fmtNumber(Object.keys(fallback).length,0)} Punkte · 1 Tag Fallback · einheitliches Raster`;
    }else{
      $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: 0 Kerzen · ${intervalLabel} · Abruf erforderlich`;
    }
  }else if(history.enabled){
    const daily=history.prices?.[selectedCurrency]||{}, uniform=resampleLongRangeUniform(daily), stepDays=longRangeUniformStepDays(daily);
    $("#historyStatus").textContent=`${t("historyEnabled")} · ${selectedCurrency}: ${fmtNumber(Object.keys(uniform).length,0)} Punkte · ${stepDays} Tag${stepDays===1?"":"e"} · einheitliches Raster`;
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
function transactionFiatTotal(type, amountBtc, price, fee=0) {
  const amount = Number(amountBtc), rate = Number(price), charge = Math.max(0, Number(fee) || 0);
  if (!(amount > 0) || !(rate > 0)) return NaN;
  const gross = amount * rate;
  if (type === "purchase") return gross + charge;
  if (type === "sale" || type === "expense") return gross - charge;
  return gross;
}
function transactionPriceFromTotal(type, amountBtc, fiatTotal, fee=0) {
  const amount = Number(amountBtc), total = Number(fiatTotal), charge = Math.max(0, Number(fee) || 0);
  if (!(amount > 0) || !(total > 0)) return NaN;
  const gross = type === "purchase" ? total - charge : (type === "sale" || type === "expense") ? total + charge : total;
  return gross > 0 ? gross / amount : NaN;
}
function transactionAmountFromTotal(type, price, fiatTotal, fee=0) {
  const rate = Number(price), total = Number(fiatTotal), charge = Math.max(0, Number(fee) || 0);
  if (!(rate > 0) || !(total > 0)) return NaN;
  const gross = type === "purchase" ? total - charge : (type === "sale" || type === "expense") ? total + charge : total;
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
  const fee = csvFixed(row.fee || 0, 8);
  if (!['purchase','sale','expense'].includes(type) || !timestamp || !depot || !amount || !fee) return "";
  if (type !== "expense" && (!currency || !price)) return "";
  return [type, timestamp, depot, amount, currency, price, fee].join("|");
}
function csvImportRefHash(row) {
  const value = String(row.import_ref_hash || "").trim().toLowerCase();
  return /^[0-9a-f]{64}$/.test(value) ? value : "";
}
function csvFingerprint(row) {
  const refHash = csvImportRefHash(row);
  const values = csvValueFingerprint(row);
  return refHash ? `ref:${refHash}` : values ? `values:${values}` : "";
}
function markCsvDuplicates(rows) {
  const existingRows = (state.data?.entries || [])
    .filter(item => ["purchase","sale","expense"].includes(item.type));
  const existingRefs = new Set(existingRows.map(csvImportRefHash).filter(Boolean));
  const existingValues = new Set(existingRows.map(csvValueFingerprint).filter(Boolean));
  const legacyCounts = new Map();
  existingRows.forEach(item => {
    if (csvImportRefHash(item)) return;
    const values = csvValueFingerprint(item);
    if (values) legacyCounts.set(values, (legacyCounts.get(values) || 0) + 1);
  });
  const pendingRefs = new Set(), pendingValues = new Set();
  rows.forEach(row => {
    const refHash = csvImportRefHash(row), values = csvValueFingerprint(row);
    let duplicate = false;
    if (refHash) {
      duplicate = existingRefs.has(refHash) || pendingRefs.has(refHash);
      if (!duplicate && values && (legacyCounts.get(values) || 0) > 0) {
        legacyCounts.set(values, legacyCounts.get(values) - 1);
        duplicate = true;
      }
      pendingRefs.add(refHash);
      if (!duplicate && values) pendingValues.add(values);
    } else {
      duplicate = Boolean(values && (existingValues.has(values) || pendingValues.has(values)));
      if (values) pendingValues.add(values);
    }
    row.duplicate = duplicate;
    if (row.duplicate) row.selected = false;
  });
}
function validateCsvRow(row) {
  const warnings = [];
  if (!['purchase','sale','expense'].includes(String(row.type || ''))) warnings.push(t("csvInvalid"));
  if (!(Number(row.amount_btc) > 0)) warnings.push(t("csvAmountRequired"));
  if (row.type !== "expense" && !String(row.currency || "").trim()) warnings.push(t("csvCurrencyRequired"));
  if (row.type !== "expense" && !(Number(row.price) > 0)) warnings.push(t("csvPriceRequired"));
  if (row.type === "expense" && (Boolean(String(row.currency || "").trim()) !== (Number(row.price) > 0))) warnings.push(t("csvPriceRequired"));
  if (!(Number(row.fee || 0) >= 0)) warnings.push(t("csvFeeInvalid"));
  const pricedExpense=row.type === "expense" && Boolean(String(row.currency||"").trim()) && Number(row.price)>0;
  if (row.type !== "expense" || pricedExpense) {
    if (!(Number(row.fiat_total) > 0)) warnings.push(t("fiatAmountRequired"));
    else {
      const control=transactionControlCheck(row.type,Number(row.amount_btc),Number(row.price),Number(row.fiat_total),Number(row.fee||0));
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
      if (row && fieldName === "amount_unit") {
        const amountInput=tr?.querySelector('[data-field="amount_btc"]'), previous=event.currentTarget.dataset.previousUnit || row.amount_unit || "BTC", next=event.currentTarget.value || "BTC";
        const btc=displayedAmountToBtc(amountInput?.value,previous);
        if(Number.isFinite(btc)&&btc>0&&amountInput)amountInput.value=compactInputNumber(btcToDisplayedAmount(btc,next),next==="sats"?0:8);
        event.currentTarget.dataset.previousUnit=next;
      }
      if (["amount_btc","amount_unit","price","fiat_total","fee","type"].includes(fieldName)) syncCsvRowCalculator(tr,fieldName);
      csvRowsFromModal();
      refreshCsvReviewVisuals();
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
  const input = $("#csvFileInput"), file = input?.files?.[0];
  if (!file) throw new Error(t("noFileSelected"));
  const button = $("#csvPreviewButton"), originalText = button.textContent;
  button.disabled = true; button.textContent = t("csvParsing");
  try {
    const upload = new FormData();
    upload.append("entry_id", state.entryId);
    upload.append("file", file, file.name);
    const result = await api("api/import/preview", {method:"POST", body:upload, timeoutMs:60000});
    const depotId = $("#csvDefaultDepot")?.value || state.data?.depots?.[0]?.id || "main";
    result.rows = (result.rows || []).map(row => initializeCsvControlTotal({...row, optional_note_fields:{...(row.optional_note_fields || {})}, import_hints:{...(row.import_hints || {})}, depot_id:depotId, selected:Boolean(row.valid), removed:false, parser_requires_review:!row.valid, edited:false, note_user_edited:false}));
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
    const message=`${t("invalidImportRow")}: ${invalid.source||"CSV"} ${t("row")} ${invalid.source_row||"?"}`;
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
      transactions:rows.map(row=>({type:row.type,timestamp:row.timestamp,amount_btc:row.amount_btc,currency:row.currency,price:row.price,fee:row.fee,depot_id:row.depot_id,note:csvComposedNote(row),import_ref_hash:row.import_ref_hash||""}))
    },{timeoutMs:120000});
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
function resetTransactionEditMode({resetForm=true}={}){
  const form=$("#transactionForm"); if(!form)return;
  state.editingEntryId="";
  if(resetForm)form.reset();
  const type=form.querySelector('[name="type"]');
  if(type){type.disabled=false;const expense=type.querySelector('option[value="expense"]');if(expense)expense.disabled=true;if(!["purchase","sale","stack"].includes(type.value))type.value="purchase";}
  $("#transactionFormTitle").textContent=t("newEntry");
  $("#transactionSubmit").textContent=t("saveEntry");
  $("#transactionCancelEdit").classList.add("hidden");
  form.querySelectorAll('[data-auto-calculated]').forEach(item=>delete item.dataset.autoCalculated);
  if(resetForm){setDefaultDate();const unit=form.querySelector('[name="amount_unit"]');unit.value=state.unit;unit.dataset.previousUnit=state.unit;}
  $$(".priced",form).forEach(item=>item.style.display=type?.value==="stack"?"none":"block");
  updateTransactionFiatLabel();syncTransactionCalculator();
}
function beginEditEntry(entryId){
  const entry=(state.data?.entries||[]).find(item=>item.id===entryId); if(!entry)return;
  const form=$("#transactionForm"); state.editingEntryId=entryId;
  const type=form.querySelector('[name="type"]'), expenseOption=type.querySelector('option[value="expense"]');
  if(expenseOption)expenseOption.disabled=entry.type!=="expense";
  type.disabled=false;type.value=entry.type;type.disabled=true;
  form.querySelector('[name="depot_id"]').value=entry.depot_id||"main";
  const unit=form.querySelector('[name="amount_unit"]');unit.value=state.unit;unit.dataset.previousUnit=state.unit;
  form.querySelector('[name="amount"]').value=compactInputNumber(btcToDisplayedAmount(Number(entry.amount_btc||0),state.unit),state.unit==="sats"?0:8);
  const currency=form.querySelector('[name="currency"]'); if(entry.currency&&!([...currency.options].some(o=>o.value===entry.currency)))currency.insertAdjacentHTML("beforeend",`<option value="${esc(entry.currency)}">${esc(entry.currency)}</option>`); if(entry.currency)currency.value=entry.currency;
  form.querySelector('[name="price"]').value=entry.price||"";
  form.querySelector('[name="fee"]').value=entry.fee||0;
  const total=entry.price?transactionFiatTotal(entry.type,Number(entry.amount_btc||0),Number(entry.price||0),Number(entry.fee||0)):NaN;
  form.querySelector('[name="fiat_total"]').value=Number.isFinite(total)&&total>0?Number(total).toFixed(2):"";
  form.querySelector('[name="timestamp"]').value=transactionLocalTimestamp(entry.timestamp);
  form.querySelector('[name="note"]').value=entry.note||"";
  form.querySelectorAll('[data-auto-calculated]').forEach(item=>delete item.dataset.autoCalculated);
  $("#transactionFormTitle").textContent=t("editEntry");
  $("#transactionSubmit").textContent=t("saveChanges");
  $("#transactionCancelEdit").classList.remove("hidden");
  $$(".priced",form).forEach(item=>item.style.display=entry.type==="stack"?"none":"block");
  updateTransactionFiatLabel();syncTransactionCalculator();
  const status=$("#transactionCalcStatus"); if(status&&entry.type==="stack")status.textContent=t("editTypeLocked");
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
$("#themeButton").onclick=()=>{state.theme=state.theme==="dark"?"light":"dark";applyTheme();renderChart();};
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
$("#portfolioSelect").onchange=async event=>{state.entryId=event.target.value;state.halvings=[];state.halvingInfo=null;state.halvingsEntryId="";state.halvingsError="";bitcoinNetworkRefreshAt=0;localStorage.setItem("bst_entry",state.entryId);await loadData();await loadTorRotationSettings();};
$("#historyRange").onchange=async event=>{state.historyRange=event.target.value;localStorage.setItem("bst_history_range",state.historyRange);await loadData();};
if($("#refreshChartPrices")) $("#refreshChartPrices").onclick=refreshChartPrices;
if($("#chartMilestonesButton")) $("#chartMilestonesButton").onclick=()=>{state.showMilestones=!state.showMilestones;localStorage.setItem("bst_chart_milestones",state.showMilestones?"1":"0");updateChartMarkerButtons();renderChart();};
if($("#chartHalvingsButton")) $("#chartHalvingsButton").onclick=()=>{state.showHalvings=!state.showHalvings;localStorage.setItem("bst_chart_halvings",state.showHalvings?"1":"0");updateChartMarkerButtons();if(state.showHalvings&&!state.halvings.length)void loadHalvings();renderChart();};
$("#chartCurrency").onchange=event=>{state.chartCurrency=event.target.value;localStorage.setItem("bst_chart_currency",state.chartCurrency);renderOverview();};
$("#chartMode").onchange=()=>renderChart();
$("#chartScaleButton").onclick=()=>{if($("#chartScaleButton").disabled)return;state.chartScale=state.chartScale==="linear"?"log":"linear";localStorage.setItem("bst_chart_scale",state.chartScale);renderChart();};
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

$("#transactionForm select[name=type]").onchange=event=>{
  $$(".priced",$("#transactionForm")).forEach(item=>item.style.display=event.target.value==="stack"?"none":"block");
  updateTransactionFiatLabel();syncTransactionCalculator("type");
};
$("#transactionForm select[name=currency]").addEventListener("change",()=>{updateTransactionFiatLabel();syncTransactionCalculator("currency");});
["amount","price","fiat_total","fee"].forEach(name=>$("#transactionForm [name="+name+"]")?.addEventListener("input",event=>syncTransactionCalculator(event.currentTarget.name)));
$("#transactionForm select[name=amount_unit]").addEventListener("change",event=>{
  const input=$("#transactionForm [name=amount]"),previous=event.currentTarget.dataset.previousUnit||"BTC",next=event.currentTarget.value||"BTC",btc=displayedAmountToBtc(input?.value,previous);
  if(Number.isFinite(btc)&&btc>0&&input)input.value=compactInputNumber(btcToDisplayedAmount(btc,next),next==="sats"?0:8);
  event.currentTarget.dataset.previousUnit=next;syncTransactionCalculator("amount_unit");
});
$("#transactionCancelEdit").onclick=()=>resetTransactionEditMode();
$("#transactionForm").onsubmit=async event=>{
  event.preventDefault();const form=new FormData(event.target),existing=state.editingEntryId?(state.data?.entries||[]).find(item=>item.id===state.editingEntryId):null,type=existing?.type||form.get("type");
  if(type!=="stack"){
    const amountBtc=displayedAmountToBtc(form.get("amount"),form.get("amount_unit")),price=Number(form.get("price")),fiatTotal=Number(form.get("fiat_total")),fee=Number(form.get("fee")||0);
    if(type!=="expense"||price>0||fiatTotal>0){const control=transactionControlCheck(type,amountBtc,price,fiatTotal,fee);if(!control.complete||!control.valid){toast(t("fiatControlBlocked"));syncTransactionCalculator();return;}}
  }
  const payload={config_entry_id:state.entryId,amount:Number(form.get("amount")),amount_unit:form.get("amount_unit"),timestamp:form.get("timestamp")?new Date(form.get("timestamp")).toISOString():undefined,note:form.get("note")||"",depot_id:form.get("depot_id")};
  if(type!=="stack")Object.assign(payload,{currency:form.get("currency")||"",price:Number(form.get("price")||0),fee:Number(form.get("fee")||0)});
  if(existing){
    payload.ledger_entry_id=existing.id;
    await service("update_entry",payload);
    resetTransactionEditMode();toast(t("entryUpdated"));await loadData();return;
  }
  await service(type==="purchase"?"add_purchase":type==="sale"?"add_sale":"add_stack",payload);
  resetTransactionEditMode();toast(t("entrySaved"));await loadData();
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
$("#unlockForm").onsubmit=async event=>{event.preventDefault();const input=event.target.elements.password;let password=String(input?.value||"");if(input)input.value="";try{await hardenedUnlock(password);state.lastActivityAt=Date.now();await loadData();await syncCoreAutoLock({touch:true,silent:false});}finally{password="";event.target.reset();}};
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
    ? new Set(state.satsPerFiat ? ["price","stack","price_stack"] : ["stack"])
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
  return Object.entries(values || {})
    .filter(([day,value]) => Number.isFinite(chartTimestamp(day)) && Number.isFinite(Number(value)))
    .map(([day,value]) => ({day,value:Number(value)}))
    .sort((a,b) => chartTimestamp(a.day) - chartTimestamp(b.day));
}
function periodContext(currency) {
  const values = analyticsValues(currency), portfolio = sortedNumericPoints(values.portfolio), price = sortedNumericPoints(values.price);
  const source = portfolio.length >= 2 ? portfolio : price;
  if (source.length < 2) return {values,days:[],startDay:null,endDay:null};
  return {values,days:source.map(item=>item.day),startDay:source[0].day,endDay:source.at(-1).day};
}
function valueOnOrBefore(series, when) {
  const target = chartTimestamp(when);
  if (!Number.isFinite(target)) return null;
  const points = sortedNumericPoints(series);
  let current = null;
  for (const item of points) {
    if (seriesValuationTimestamp(item.day) > target) break;
    current = item.value;
  }
  return current;
}
function entryExternalFlow(entry, currency, priceSeries) {
  const amount = Number(entry.amount_btc || 0), timestamp = String(entry.timestamp || "");
  if (!Number.isFinite(amount) || amount <= 0 || !Number.isFinite(chartTimestamp(timestamp))) return 0;
  const marketPrice = valueOnOrBefore(priceSeries,timestamp);
  const sameCurrency = String(entry.currency || "").toUpperCase() === String(currency || "").toUpperCase();
  const transactionPrice = Number(entry.price), fee = Math.max(0,Number(entry.fee || 0));
  if (entry.type === "purchase") {
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
function externalFlowEvents(currency, priceSeries) {
  return (state.data?.entries || [])
    .map((entry,sequence) => ({time:chartTimestamp(entry?.timestamp),flow:entryExternalFlow(entry,currency,priceSeries),entry,sequence}))
    .filter(item => Number.isFinite(item.time) && Number.isFinite(item.flow) && item.flow !== 0)
    .sort((a,b)=>a.time-b.time || Number(["sale","expense"].includes(a.entry?.type))-Number(["sale","expense"].includes(b.entry?.type)) || a.sequence-b.sequence);
}
function performanceLedgerEvents(currency, priceSeries) {
  const selectedCurrency = String(currency || "").toUpperCase();
  const events = (state.data?.entries || []).map((entry,sequence) => {
    const time = chartTimestamp(entry?.timestamp), amount = Math.max(0,Number(entry?.amount_btc || 0));
    const kind = String(entry?.type || "");
    if (!Number.isFinite(time) || !(amount > 0) || !["purchase","stack","sale","expense"].includes(kind)) return null;
    const btcDelta = ["purchase","stack"].includes(kind) ? amount : -amount;
    const sameCurrency = String(entry?.currency || "").toUpperCase() === selectedCurrency;
    const transactionPrice = Number(entry?.price);
    const marketPrice = valueOnOrBefore(priceSeries,entry?.timestamp);
    const valuationPrice = sameCurrency && ["purchase","sale","expense"].includes(kind) && Number.isFinite(transactionPrice) && transactionPrice > 0
      ? transactionPrice
      : marketPrice;
    return {time,btcDelta,externalFlow:entryExternalFlow(entry,currency,priceSeries),valuationPrice,kind,sourceSequence:sequence};
  }).filter(Boolean).sort((a,b)=>a.time-b.time || Number(["sale","expense"].includes(a.kind))-Number(["sale","expense"].includes(b.kind)) || a.sourceSequence-b.sourceSequence);
  return events.map((event,sequence)=>({...event,sequence}));
}
function performancePricePoints(priceSeries) {
  return sortedNumericPoints(priceSeries).map(item => ({time:seriesValuationTimestamp(item.day),value:item.value,key:item.day})).filter(item=>Number.isFinite(item.time));
}
function twrAnalysis(currency) {
  const context = periodContext(currency), math = globalThis.BSTPerformanceMath;
  if (!math || !context.startDay) return null;
  const result = math.timeWeightedReturn(performancePricePoints(context.values.price),performanceLedgerEvents(currency,context.values.price));
  if (!result) return null;
  return {
    percent: result.percent,
    index: result.index || {},
    startDay: Number.isFinite(result.startTime) ? new Date(result.startTime).toISOString() : context.startDay,
    endDay: Number.isFinite(result.endTime) ? new Date(result.endTime).toISOString() : context.endDay,
    calculatedDays: result.calculatedPeriods || 0,
    invalid: Boolean(result.invalid),
    reason: result.reason || null,
  };
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
  const context=periodContext(currency), portfolio=sortedNumericPoints(context.values.portfolio);
  if(portfolio.length<2)return null;
  const start=portfolio[0],end=portfolio.at(-1),startTime=seriesValuationTimestamp(start.day),endTime=seriesValuationTimestamp(end.day),flows=[];
  if(!Number.isFinite(startTime)||!Number.isFinite(endTime)||endTime<=startTime)return null;
  if(start.value>0)flows.push({date:new Date(startTime),amount:-start.value});
  for(const event of externalFlowEvents(currency,context.values.price)){
    if(event.time<=startTime||event.time>endTime)continue;
    flows.push({date:new Date(event.time),amount:-event.flow});
  }
  if(end.value>0)flows.push({date:new Date(endTime),amount:end.value});
  const solved=xirrSolveDetailed(flows);
  return {percent:solved.rate===null?null:solved.rate*100,startDay:start.day,endDay:end.day,flowCount:flows.length,ambiguous:solved.ambiguous,rootCount:solved.roots.length};
}
function cashflowAdjustedPortfolioChange(currency) {
  const context=periodContext(currency), points=sortedNumericPoints(context.values.portfolio);
  if(points.length<2)return null;
  const start=points[0],end=points.at(-1),startTime=seriesValuationTimestamp(start.day),endTime=seriesValuationTimestamp(end.day);
  const events=externalFlowEvents(currency,context.values.price).filter(item=>item.time>startTime&&item.time<=endTime);
  const flow=events.reduce((sum,item)=>sum+item.flow,0);
  const absolute=end.value-start.value-flow;
  const twr=twrAnalysis(currency);
  return {startDay:start.day,endDay:end.day,start:start.value,end:end.value,absolute,percent:twr?.percent ?? null,externalFlow:flow};
}
function maximumDrawdown(values) {
  const math = globalThis.BSTPerformanceMath;
  if (!math) return null;
  const result = math.maximumDrawdown(sortedNumericPoints(values).map(item=>({time:seriesValuationTimestamp(item.day),value:item.value,key:item.day})));
  if (!result) return null;
  return {
    current:result.current,maximum:result.maximum,
    peakDay:new Date(result.peakTime).toISOString(),troughDay:new Date(result.troughTime).toISOString(),
    periodPeakDay:new Date(result.periodPeakTime).toISOString(),endDay:new Date(result.endTime).toISOString(),
  };
}
function analysisCard(label,value,sub="",css="") {
  return `<article class="analysis-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong>${sub?`<small>${sub}</small>`:""}</article>`;
}
function renderReturnAnalytics(currency) {
  const element=$("#returnAnalytics");if(!element)return;
  const twr=twrAnalysis(currency),xirr=xirrAnalysis(currency);
  const twrCss=(twr?.percent||0)>0?"positive":(twr?.percent||0)<0?"negative":"";
  const xirrCss=(xirr?.percent||0)>0?"positive":(xirr?.percent||0)<0?"negative":"";
  const days=twr?.startDay&&twr?.endDay?Math.max(0,(chartTimestamp(twr.endDay)-chartTimestamp(twr.startDay))/86400000):0;
  element.innerHTML=`<div class="return-head"><div><span class="kicker">TWR · XIRR</span><h3>${esc(t("trueReturn"))}</h3></div><small>${esc(t("twrHint"))}</small></div><div class="analysis-grid return-grid">${analysisCard(t("twrLong"),twr?.percent==null?t("unavailableReturn"):signedPercent(twr.percent),twr?`${esc(fmtDate(twr.startDay))} → ${esc(fmtDate(twr.endDay))}`:"",twrCss)}${analysisCard(t("xirrLong"),xirr?.ambiguous?t("ambiguousReturn"):(xirr?.percent==null?t("unavailableReturn"):signedPercent(xirr.percent)),`${esc(t("xirr"))}${days<30?` · ${esc(t("shortRangeXirr"))}`:""}`,xirrCss)}</div>`;
}
function purchasesForPeriod(currency) {
  const context=periodContext(currency);
  if(!context.startDay)return {all:[],matching:[],context};
  let startTime=chartTimestamp(context.startDay),endTime=chartTimestamp(context.endDay);
  if(state.historyRange==="first_purchase"){
    const first=(state.data?.entries||[]).filter(entry=>entry?.type==="purchase").map(entry=>chartTimestamp(entry?.timestamp)).filter(Number.isFinite).sort((a,b)=>a-b)[0];
    if(Number.isFinite(first))startTime=first;
  }
  const all=(state.data?.entries||[]).filter(entry=>{const time=chartTimestamp(entry?.timestamp);return entry.type==="purchase"&&Number.isFinite(time)&&time>=startTime&&time<=endTime;});
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
  const entries = (state.data?.entries || []).map(entry => ({...entry, time:new Date(entry.timestamp || "").getTime()})).filter(entry => Number.isFinite(entry.time)).sort((a,b)=>a.time-b.time);
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
  return `<article class="drawdown-card"><span>${esc(title)}</span><div><small>${esc(t("periodHighDistance"))}</small><strong class="${data.current<0?"negative":""}">${privateHtml(signedPercent(data.current))}</strong></div><div><small>${esc(t("maximumDrawdown"))}</small><strong class="${css}">${privateHtml(signedPercent(data.maximum))}</strong></div><small>${esc(t("peak"))}: ${esc(fmtDate(data.peakDay))} · ${esc(t("trough"))}: ${esc(fmtDate(data.troughDay))}</small></article>`;
}
function renderDrawdownAnalytics(currency) {
  const element=$("#drawdownAnalytics");if(!element)return;
  const context=periodContext(currency),twr=twrAnalysis(currency);
  element.innerHTML=drawdownCard(t("bitcoinDrawdown"),maximumDrawdown(context.values.price))+drawdownCard(t("portfolioDrawdown"),maximumDrawdown(twr?.index||{}));
}
function renderAdvancedAnalytics(currency){renderReturnAnalytics(currency);renderDcaAnalytics(currency);renderDrawdownAnalytics(currency);}
function chartSeries(mode,currency){
  const values=chartValues(currency),stack=Object.fromEntries(Object.entries(values.stackBtc).map(([day,value])=>[day,rawUnitValue(value)]));
  const stackSeries=(extra={})=>({key:"stack",label:`${t("stackHistory")} ${state.unit}`,unit:state.unit,values:stack,format:value=>state.unit==="sats"?`${fmtNumber(value,0)} sats`:`${fmtNumber(value,8)} BTC`,...extra});
  if(state.fiatFree){
    const satsPrice=Object.fromEntries(Object.entries(values.price).filter(([,value])=>Number(value)>0).map(([day,value])=>[day,SATS_PER_BTC/Number(value)]));
    const satsSeries=(extra={})=>({key:"sats_per_fiat",label:`${t("satsPerFiat")} ${currency}`,unit:`sats/${currency}`,values:satsPrice,format:value=>`${fmtNumber(value,0)} sats/${currency}`,...extra});
    if(!state.satsPerFiat)return [stackSeries()];
    const options={price:[satsSeries()],stack:[stackSeries()],price_stack:[satsSeries(),stackSeries({secondary:true})]};
    return options[mode]||options.price_stack;
  }
  const fiat=(key,label,seriesValues,extra={})=>({key,label:`${label} ${currency}`,unit:currency,values:seriesValues,format:value=>fmtFiat(value,currency),...extra});
  const pnl=(extra={})=>fiat("pnl",t("profitLossHistory"),values.totalProfitLoss,{allowNegative:true,...extra});
  const unrealized=(extra={})=>fiat("unrealized_pnl",t("unrealizedProfitLoss"),values.unrealizedProfitLoss,{allowNegative:true,...extra});
  const options={price:[fiat("price",t("btcPrice"),values.price)],portfolio:[fiat("portfolio",t("portfolioValue"),values.portfolio)],stack:[stackSeries()],pnl:[pnl()],price_portfolio:[fiat("price",t("btcPrice"),values.price),fiat("portfolio",t("portfolioValue"),values.portfolio,{secondary:true})],price_stack:[fiat("price",t("btcPrice"),values.price),stackSeries({secondary:true})],price_pnl:[fiat("price",t("btcPrice"),values.price),pnl({secondary:true})],portfolio_pnl:[fiat("portfolio",t("portfolioValue"),values.portfolio),pnl({secondary:true})],cost_pnl:[fiat("cost",t("openCostBasis"),values.costBasis,{step:true}),unrealized({secondary:true})]};
  return options[mode]||options.price;
}
function currentProfitMetrics(currency){
  const fifo=state.data?.fifo||{},livePrice=Number(state.data?.prices?.[currency]);
  const lots=(fifo.open_lots||[]).filter(lot=>String(lot.currency||"").toUpperCase()===String(currency).toUpperCase());
  const invested=lots.reduce((sum,lot)=>sum+Number(lot.remaining_btc||0)*Number(lot.unit_basis||0),0);
  const knownBtc=lots.reduce((sum,lot)=>sum+Number(lot.remaining_btc||0),0);
  const marketValue=Number.isFinite(livePrice)?knownBtc*livePrice:null;
  const unrealized=Number.isFinite(marketValue)?marketValue-invested:null;
  const realized=Number(fifo.realized?.[currency]||0);
  const total=Number.isFinite(unrealized)?unrealized+realized:realized;
  const cumulativePurchaseOutlay=(state.data?.entries||[]).reduce((sum,entry)=>{
    if(entry?.type!=="purchase"||String(entry.currency||"").toUpperCase()!==String(currency).toUpperCase())return sum;
    const amount=Number(entry.amount_btc||0),price=Number(entry.price||0),fee=Number(entry.fee||0);
    if(!Number.isFinite(amount)||amount<=0||!Number.isFinite(price)||price<=0)return sum;
    return sum+amount*price+(Number.isFinite(fee)&&fee>0?fee:0);
  },0);
  return {invested,knownBtc,marketValue,unrealized,realized,total,cumulativePurchaseOutlay};
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
  cards.push(twoMetricCard(t("bookProfitLossPerformance"),t("currentProfitLoss"),fmtFiat(profit.unrealized,currency),t("onOpenCostBasis"),bookPercent==null?"–":signedPercent(bookPercent),{css:bookCss,footer:`${esc(t("openCostBasis"))}: ${privateHtml(fmtFiat(profit.invested,currency))}`}));
  cards.push(twoMetricCard(t("realizedProfitLossPerformance"),t("currentProfitLoss"),fmtFiat(profit.realized,currency),t("cumulativePurchaseOutlay"),fmtFiat(profit.cumulativePurchaseOutlay,currency),{css:realizedCss,rightCss:""}));
  cards.push(twoMetricCard(t("profitLossPerformance"),t("currentProfitLoss"),fmtFiat(profit.total,currency),t("cumulativePurchaseOutlay"),fmtFiat(profit.cumulativePurchaseOutlay,currency),{css:totalCss,rightCss:""}));
  element.innerHTML=cards.join("");
  renderAdvancedAnalytics(currency);
}

function renderOverview(){
  const data=state.data,fifo=data.fifo,currency=currentCurrency(),rawPrice=data.prices[currency],total=Number(fifo.total_btc||0);
  if(state.fiatFree){
    const cards=[[t("totalStack"),fmtStack(total),state.unit==="BTC"?`${fmtNumber(total*SATS_PER_BTC,0)} sats`:`${fmtNumber(total,8)} BTC`,""],[t("longTerm"),fmtStack(fifo.long_term_btc||0),"",""],[t("shortTerm"),fmtStack(fifo.short_term_btc||0),"",""],state.satsPerFiat?[t("currentBtcPurchasingPower"),fmtSatsPerFiat(rawPrice,currency),currency,""]:[t("unknown"),fmtStack(fifo.unknown_btc||fifo.unknown_holding_btc||0),"",""]];
    $("#summaryCards").innerHTML=cards.map(([label,value,sub,css])=>`<article class="metric-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong><small>${privateHtml(sub)}</small></article>`).join("");
  }else{
    const value=rawPrice==null?null:total*Number(rawPrice);
    const lots=(fifo.open_lots||[]).filter(lot=>lot.currency===currency);
    const invested=lots.reduce((sum,lot)=>sum+Number(lot.remaining_btc||0)*Number(lot.unit_basis||0),0);
    const known=lots.reduce((sum,lot)=>sum+Number(lot.remaining_btc||0),0);
    const unrealized=rawPrice==null?null:known*Number(rawPrice)-invested;
    const unrealizedPercent=unrealized!=null&&invested>0?unrealized/invested*100:null;
    const realized=Number(fifo.realized?.[currency]||0);
    const secured=lifetimeFiatSecured(currency);
    const cards=[
      [t("totalStack"),fmtStack(total),state.unit==="BTC"?`${fmtNumber(total*SATS_PER_BTC,0)} sats`:`${fmtNumber(total,8)} BTC`,""],
      [t("totalValue"),fmtFiat(value,currency),`${fmtFiat(rawPrice,currency)} / BTC`,""],
      [t("openBasis"),fmtFiat(invested,currency),`${fmtStack(known)} · ${t("openBasisHint")}`,""],
      [t("unrealized"),fmtFiat(unrealized,currency),`${t("onOpenCostBasis")}: ${unrealizedPercent==null?"–":signedPercent(unrealizedPercent)} · ${t("realized")}: ${fmtFiat(realized,currency)}`,unrealized>0?"positive":unrealized<0?"negative":""],
      [t("fiatSecured"),fmtFiat(secured.fiat,currency),`${t("purchaseFees")}: ${fmtFiat(secured.fees,currency)} · ${t("purchaseOutlay")}: ${fmtFiat(secured.totalOutlay,currency)}`,""]
    ];
    $("#summaryCards").innerHTML=cards.map(([label,value,sub,css])=>`<article class="metric-card"><span>${esc(label)}</span><strong class="${css}">${privateHtml(value)}</strong><small>${privateHtml(sub)}</small></article>`).join("");
  }
  $("#heroLong").textContent=privateText(fmtStack(fifo.long_term_btc));
  const nextGoal=state.discreet?null:(data.goals||[]).filter(goal=>Number(goal.remaining_btc)>0).sort((a,b)=>Number(a.remaining_btc)-Number(b.remaining_btc))[0];
  $("#heroGoal").textContent=state.discreet?"":(nextGoal?`${nextGoal.name}: ${privateText(fmtStack(nextGoal.remaining_btc))}`:"✓");
  $("#heroText").textContent=state.lang==="de"?`Lokales Kauf- und Verkaufsbuch mit depotweisem FIFO, ${data.tax_settings.long_term_days} Tagen Haltezeit-Regel und dauerhaft gespeichertem Tagesverlauf.`:`Local purchase and sale ledger with per-depot FIFO, a ${data.tax_settings.long_term_days}-day holding rule, and durable daily history.`;
  renderBitcoinNetworkStrip();
  renderChart();renderGoalCards();
}

function renderAggregateDepot(){
  const element=$("#aggregateDepotSummary");if(!element)return;const data=state.data||{},fifo=data.fifo||{},currency=currentCurrency(),totalBtc=Number(fifo.total_btc||0),values=chartValues(currency),stackChange=seriesChange(values.stackBtc),rangeLabel=$("#historyRange option:checked")?.textContent||t("selectedRange"),stackCss=stackChange?.absolute>0?"positive":stackChange?.absolute<0?"negative":"",stackPerformance=stackChange?`${state.unit==="sats"?`${signedNumber(stackChange.absolute*SATS_PER_BTC,0)} sats`:`${signedNumber(stackChange.absolute,8)} BTC`} · ${signedPercent(stackChange.percent)}`:"–";
  let cells=`<div><span>${esc(t("totalStack"))}</span><strong>${privateHtml(fmtStack(totalBtc))}</strong><small>${esc(t("longTerm"))}: ${privateHtml(fmtStack(fifo.long_term_btc||0))} · ${esc(t("shortTerm"))}: ${privateHtml(fmtStack(fifo.short_term_btc||0))}</small></div>`;
  if(state.fiatFree){const twr=twrAnalysis(currency);cells+=`<div><span>${esc(t("twrLong"))}</span><strong class="${(twr?.percent||0)>0?"positive":(twr?.percent||0)<0?"negative":""}">${privateHtml(twr?.percent==null?"–":signedPercent(twr.percent))}</strong><small>${esc(t("cashflowAdjusted"))}</small></div>`;}else{const livePrice=Number(data.prices?.[currency]),totalValue=Number.isFinite(livePrice)?totalBtc*livePrice:null,portfolioChange=cashflowAdjustedPortfolioChange(currency),portfolioCss=portfolioChange?.absolute>0?"positive":portfolioChange?.absolute<0?"negative":"",portfolioPerformance=portfolioChange?`${signedFiat(portfolioChange.absolute,currency)} · ${portfolioChange.percent==null?"–":signedPercent(portfolioChange.percent)}`:"–";cells+=`<div><span>${esc(t("totalValue"))}</span><strong>${privateHtml(fmtFiat(totalValue,currency))}</strong><small>${privateHtml(fmtFiat(livePrice,currency))} / BTC</small></div><div><span>${esc(t("rangePerformance"))}</span><strong class="${portfolioCss}">${privateHtml(portfolioPerformance)}</strong><small>${portfolioChange?`${esc(fmtDate(portfolioChange.startDay))} → ${esc(fmtDate(portfolioChange.endDay))}`:esc(t("comparisonUnavailable"))}</small></div>`;}
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

state.lastActivityAt=Date.now();localStorage.setItem("bst_last_activity_at",String(state.lastActivityAt));
console.info(`Bitcoin Stack Tracker dashboard ${BUILD_VERSION}`);
applyTheme(); applyLanguage(); applyUnit(); applyDiscreetMode(state.discreet); applyFiatFreeMode(state.fiatFree,state.satsPerFiat); updateBackupFileName(); updateCsvFileName(); setDefaultDate(); startBitcoinNetworkTicker(); boot().then(()=>loadBackupHealth());

/* robust historical goal date fallback and capped goal display */

// transaction plausibility controls
updateTransactionFiatLabel();
syncTransactionCalculator();
