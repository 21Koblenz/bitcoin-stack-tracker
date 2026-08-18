from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
comp = root / "custom_components" / "bitcoin_stack_tracker"
prepared = root / ".github" / "workflows" / "agent-xpub-backfill-labels.yml"

# Reuse the already-tested backend/backfill portion of the prepared patch.
lines = prepared.read_text(encoding="utf-8").splitlines()
a = next(i for i, line in enumerate(lines) if line.strip() == "- name: Apply fixes")
r = next(i for i in range(a + 1, len(lines)) if lines[i].strip() == "run: |")
e = next(i for i in range(r + 1, len(lines)) if lines[i].startswith("      - name:"))
source = "\n".join(line[10:] if line.startswith("          ") else line for line in lines[r + 1:e]) + "\n"
ws = source.find("# ---------- Raw XPUB auto detection ----------")
we = source.find("# ---------- Wire throttled 90-day backfill + expose completeness ----------", ws)
fs = source.find("# ---------- Frontend: custom labels", we)
if min(ws, we, fs) < 0:
    raise RuntimeError("prepared patch section bounds missing")
source = source[:ws] + source[we:fs]
exec(compile(source, str(prepared) + ":backend", "exec"), {"__name__": "__main__"})

# Normalize the generated async_stats block indentation.
intra = comp / "market_assessment_intraday_cache.py"
it = intra.read_text(encoding="utf-8")
s = it.find("    async def async_stats(")
pnt = it.find("    async def async_points(", s)
if s < 0 or pnt <= s:
    raise RuntimeError("intraday stats block missing")
stats = "\n".join([
    "    async def async_stats(self, signature: str) -> dict[str, Any]:",
    '        """Return lightweight 90-day cache completeness diagnostics."""',
    "        async with self._lock:",
    '            if str(self._data.get("signature") or "") != str(signature):',
    "                return {",
    '                    "cached_points": 0, "live_points": 0, "backfilled_points": 0,',
    '                    "expected_full_grid_points": _RETENTION_DAYS * _BUCKETS_PER_DAY,',
    '                    "oldest_timestamp": None, "newest_timestamp": None,',
    "                }",
    '            points = [item for item in self._data.get("points", []) if isinstance(item, dict)]',
    '            live = sum(1 for item in points if not bool(item.get("backfilled")))',
    "            backfilled = len(points) - live",
    '            ordered = sorted(str(item.get("timestamp") or "") for item in points if item.get("timestamp"))',
    "            return {",
    '                "cached_points": len(points),',
    '                "live_points": live,',
    '                "backfilled_points": backfilled,',
    '                "expected_full_grid_points": _RETENTION_DAYS * _BUCKETS_PER_DAY,',
    '                "oldest_timestamp": ordered[0] if ordered else None,',
    '                "newest_timestamp": ordered[-1] if ordered else None,',
    "            }",
    "",
    "",
])
intra.write_text(it[:s] + stats + it[pnt:], encoding="utf-8")

# Raw XPUB is script-family ambiguous. Keep the current resolver structure, but
# use lightweight Electrum status probes and track whether auto detection was
# actually proved by history.
wallet_path = comp / "wallet_watch.py"
text = wallet_path.read_text(encoding="utf-8")
start = text.find("    async def _resolve_xpub_address_type(")
end = text.find("    async def _probe_gap_address_used(", start)
if start < 0 or end <= start:
    raise RuntimeError("xpub resolver bounds missing")
block = text[start:end]
block = block.replace("    ) -> str:\n", "    ) -> tuple[str, bool]:\n", 1)
block = block.replace("            return requested\n", "            return requested, True\n", 1)
block = block.replace("            return root.script_type\n", "            return root.script_type, True\n", 1)
probe = re.compile(
    r"            if electrum_client is not None:\n"
    r"                calls = \[\n"
    r"                    \(\"blockchain\.scripthash\.get_history\", \[_electrum_scripthash\(address\)\]\)\n"
    r"                    for address in addresses\n"
    r"                \]\n"
    r"                results = await electrum_client\.call_many\(calls\)\n"
    r"                for history in results:\n"
    r"                    if isinstance\(history, list\) and history:\n"
    r"                        scores\[script_type\] \+= 1\n"
)
probe_new = """            if electrum_client is not None:
                calls = [
                    ("blockchain.scripthash.subscribe", [_electrum_scripthash(address)])
                    for address in addresses
                ]
                results = await self._electrum_calls_chunked(
                    electrum_client, calls, chunk_size=ELECTRUM_STATUS_BATCH_SIZE
                )
                for status in results:
                    if status not in {None, ""}:
                        scores[script_type] += 1
"""
block, n = probe.subn(probe_new, block, count=1)
if n != 1:
    raise RuntimeError(f"xpub electrum probe replacement count={n}")
block = block.replace(
    '            return "p2wpkh"\n        return best\n',
    '            return "p2wpkh", False\n        return best, True\n',
    1,
)
text = text[:start] + block + text[end:]

caller = re.compile(
    r'(?P<i>[ \t]+)monitor\["_resolved_address_type"\] = await self\._resolve_xpub_address_type\(\n'
    r'(?P=i)    monitor, source, electrum_client=client\n(?P=i)\)'
)
def caller_repl(match):
    i = match.group("i")
    return (
        f'{i}resolved_type, resolved_verified = await self._resolve_xpub_address_type(\n'
        f'{i}    monitor, source, electrum_client=client\n{i})\n'
        f'{i}monitor["_resolved_address_type"] = resolved_type\n'
        f'{i}monitor["_resolved_address_type_verified"] = bool(resolved_verified)'
    )
text, n = caller.subn(caller_repl, text, count=1)
if n != 1:
    raise RuntimeError(f"xpub caller replacement count={n}")

old = '''            "resolved_address_type": (
                str(monitor.get("_resolved_address_type") or monitor.get("address_type") or "auto")
                if str(monitor.get("kind") or "") == "xpub" else ""
            ),'''
if old not in text:
    raise RuntimeError("runtime resolved type block missing")
text = text.replace(old, old + '''
            "resolved_address_type_verified": (
                bool(monitor.get("_resolved_address_type_verified"))
                if str(monitor.get("kind") or "") == "xpub" else True
            ),''', 1)
old = '''            "last_activity_at", "last_balance_refresh_unix",
        ):'''
if old not in text:
    raise RuntimeError("runtime merge block missing")
text = text.replace(old, '''            "last_activity_at", "last_balance_refresh_unix",
            "resolved_address_type", "resolved_address_type_verified",
        ):''', 1)
cat = re.compile(
    r'        resolved_by_monitor: dict\[str, str\] = \{\}\n.*?                item\["resolved_address_type"\] = resolved_by_monitor\[monitor_id\]',
    re.S,
)
cat_new = "\n".join([
    "        resolved_by_monitor: dict[str, tuple[str, bool]] = {}",
    "        for row in rebuilt:",
    "            if not isinstance(row, dict):",
    "                continue",
    '            resolved = str(row.get("resolved_address_type") or "")',
    '            monitor_id = str(row.get("monitor_id") or "")',
    "            if monitor_id and resolved in _XPUB_AUTO_CANDIDATES:",
    '                resolved_by_monitor[monitor_id] = (resolved, bool(row.get("resolved_address_type_verified")))',
    '        for item in self.runtime_store.data.get("monitor_catalog") or []:',
    "            if not isinstance(item, dict):",
    "                continue",
    '            monitor_id = str(item.get("id") or "")',
    "            if monitor_id in resolved_by_monitor:",
    "                resolved, verified = resolved_by_monitor[monitor_id]",
    '                item["resolved_address_type"] = resolved',
    '                item["resolved_address_type_verified"] = verified',
])
text, n = cat.subn(cat_new, text, count=1)
if n != 1:
    raise RuntimeError(f"xpub catalog replacement count={n}")
old = '''                    "utxo_count": 0,
                    "baseline_complete": True,
                },'''
if old not in text:
    raise RuntimeError("monitor summary init missing")
text = text.replace(old, '''                    "utxo_count": 0,
                    "baseline_complete": True,
                    "resolved_address_type": "",
                    "resolved_address_type_verified": False,
                },''', 1)
old = '''            summary["balance_sats"] += int(row.get("balance_sats") or 0)
            summary["utxo_count"] += int(row.get("utxo_count") or 0)'''
if old not in text:
    raise RuntimeError("monitor summary update missing")
text = text.replace(old, old + '''
            if row.get("resolved_address_type"):
                summary["resolved_address_type"] = str(row.get("resolved_address_type") or "")
                summary["resolved_address_type_verified"] = bool(row.get("resolved_address_type_verified"))''', 1)
wallet_path.write_text(text, encoding="utf-8")

# Frontend: progress diagnostics + editable display-only rating labels.
index = comp / "frontend" / "index.html"
html = index.read_text(encoding="utf-8")
marker = '<div id="marketAssessmentHistoryChart" class="chart market-assessment-history-chart">'
if marker not in html:
    raise RuntimeError("history chart marker missing")
html = html.replace(marker, '<div id="marketAssessmentBackfillStatus" class="result market-assessment-backfill-status"></div>\n        ' + marker, 1)
preview = '<div id="buyOpportunitySettingsPreview" class="result"></div>'
if preview not in html:
    raise RuntimeError("settings preview marker missing")
labels_html = '''<div class="analysis-head"><span class="kicker">RATING LABELS</span><h3>Eigene Bezeichnungen</h3></div>
            <p class="storage-note">Nur Anzeigetext. Eigene Namen verändern weder Score noch Rückrechnung.</p>
            <div class="buy-opportunity-threshold-grid buy-opportunity-label-grid">
              <label><span>Sehr hoch bewertet</span><input name="label_very_expensive" type="text" maxlength="120" placeholder="Standard"></label>
              <label><span>Hoch bewertet</span><input name="label_expensive" type="text" maxlength="120" placeholder="Standard"></label>
              <label><span>Neutral</span><input name="label_neutral" type="text" maxlength="120" placeholder="Standard"></label>
              <label><span>Interessant</span><input name="label_interesting" type="text" maxlength="120" placeholder="Standard"></label>
              <label><span>Günstig</span><input name="label_cheap" type="text" maxlength="120" placeholder="Standard"></label>
              <label><span>Sehr günstig</span><input name="label_very_cheap" type="text" maxlength="120" placeholder="Standard"></label>
              <label><span>Extrem günstig</span><input name="label_extreme" type="text" maxlength="120" placeholder="Standard"></label>
            </div>
            ''' + preview
html = html.replace(preview, labels_html, 1)
html = html.replace('static/style.css?v=0.21.0.13&r=5', 'static/style.css?v=0.21.0.13&r=6', 1)
html = html.replace('static/app.js?v=0.21.0.13&r=5', 'static/app.js?v=0.21.0.13&r=6', 1)
index.write_text(html, encoding="utf-8")
const = comp / "const.py"
const.write_text(const.read_text(encoding="utf-8").replace('FRONTEND_CACHE_REVISION = "5"', 'FRONTEND_CACHE_REVISION = "6"', 1), encoding="utf-8")

app_path = comp / "frontend" / "static" / "app.js"
app = app_path.read_text(encoding="utf-8")
rating = re.compile(r'function buyOpportunityRatingLabel\(rating\)\{.*?\n\}', re.S)
rating_new = '''function buyOpportunityRatingLabel(rating){
  const value=String(rating||"unavailable"),custom=String(state.data?.buy_opportunity_settings?.labels?.[value]||"").trim();
  if(custom)return custom.slice(0,120);
  const key={very_expensive:"ratingVeryExpensive",expensive:"ratingExpensive",neutral:"ratingNeutral",interesting:"ratingInteresting",cheap:"ratingCheap",very_cheap:"ratingVeryCheap",extreme:"ratingExtreme",unavailable:"ratingUnavailable"}[value];
  return t(key||"ratingUnavailable");
}'''
app, n = rating.subn(rating_new, app, count=1)
if n != 1:
    raise RuntimeError("rating function replacement failed")
old = 'function buyOpportunitySettingsDefaults(){return {profile:"balanced",currency:(state.data?.currencies||[])[0]||"EUR",weights:{...BUY_OPPORTUNITY_PRESETS.balanced},signal_weights:structuredClone(BUY_OPPORTUNITY_SIGNAL_DEFAULTS),turning_point_weights:structuredClone(BUY_OPPORTUNITY_TURNING_DEFAULTS),model:{...BUY_OPPORTUNITY_MODEL_DEFAULTS},thresholds:{very_expensive_max:20,expensive_max:35,interesting:50,cheap:65,very_cheap:80,extreme:90}};}'
new = 'function buyOpportunitySettingsDefaults(){return {profile:"balanced",currency:(state.data?.currencies||[])[0]||"EUR",weights:{...BUY_OPPORTUNITY_PRESETS.balanced},signal_weights:structuredClone(BUY_OPPORTUNITY_SIGNAL_DEFAULTS),turning_point_weights:structuredClone(BUY_OPPORTUNITY_TURNING_DEFAULTS),model:{...BUY_OPPORTUNITY_MODEL_DEFAULTS},thresholds:{very_expensive_max:20,expensive_max:35,interesting:50,cheap:65,very_cheap:80,extreme:90},labels:{very_expensive:"",expensive:"",neutral:"",interesting:"",cheap:"",very_cheap:"",extreme:""}};}'
if old not in app:
    raise RuntimeError("defaults function missing")
app = app.replace(old, new, 1)
loop = '  for(const key of ["very_expensive_max","expensive_max","interesting","cheap","very_cheap","extreme"]){const input=form.elements[`threshold_${key}`];if(input)input.value=String(Number(thresholds[key]??defaults.thresholds[key]));}'
if loop not in app:
    raise RuntimeError("threshold render loop missing")
app = app.replace(loop, loop + '\n  const labels=settings.labels||defaults.labels;for(const key of ["very_expensive","expensive","neutral","interesting","cheap","very_cheap","extreme"]){const input=form.elements[`label_${key}`];if(input)input.value=String(labels[key]||"");}', 1)
collect = '  const thresholds=Object.fromEntries(["very_expensive_max","expensive_max","interesting","cheap","very_cheap","extreme"].map(key=>[key,Number(form.elements[`threshold_${key}`].value||0)]));'
if collect not in app:
    raise RuntimeError("threshold collect missing")
app = app.replace(collect, collect + '\n  const labels=Object.fromEntries(["very_expensive","expensive","neutral","interesting","cheap","very_cheap","extreme"].map(key=>[key,String(form.elements[`label_${key}`]?.value||"").trim().slice(0,120)]));', 1)
svc = 'weights,signal_weights,turning_point_weights,model,thresholds});'
if svc not in app:
    raise RuntimeError("settings service payload missing")
app = app.replace(svc, 'weights,signal_weights,turning_point_weights,model,thresholds,labels});', 1)
summary = 'return {addresses:Number(aggregate.address_count||0),receive_addresses:Number(aggregate.receive_address_count||0),change_addresses:Number(aggregate.change_address_count||0),receive_used:Number(aggregate.receive_used_count||0),change_used:Number(aggregate.change_used_count||0),balance_sats:overviewBalance===null?Number(aggregate.balance_sats||0):overviewBalance,utxo_count:Number(aggregate.utxo_count||0),baseline_complete:Boolean(aggregate.baseline_complete),last_activity:last};'
if summary not in app:
    raise RuntimeError("runtime summary return missing")
app = app.replace(summary, summary.replace(',last_activity:last', ',resolved_address_type:String(aggregate.resolved_address_type||""),resolved_address_type_verified:Boolean(aggregate.resolved_address_type_verified),last_activity:last'), 1)
balance = 'balanceText=state.discreet?"••••":`${fmtNumber(Number(runtime.balance_sats||0)/SATsFix(),8)} BTC`'
if balance not in app:
    raise RuntimeError("wallet balance expression missing")
app = app.replace(balance, 'xpubResolving=mon.kind==="xpub"&&String(mon.address_type||"auto")==="auto"&&!runtime.resolved_address_type_verified,balanceText=state.discreet?"••••":xpubResolving?walletWatchLang("Wird ermittelt …","Detecting …"):`${fmtNumber(Number(runtime.balance_sats||0)/SATsFix(),8)} BTC`', 1)
renderer = '''function renderMarketAssessmentBackfillStatus(payload=state.marketAssessmentHistory){
  const host=$("#marketAssessmentBackfillStatus");if(!host)return;const s=payload?.intraday_backfill||{};
  if(!Object.keys(s).length){host.textContent=walletWatchLang("90-Tage-Rückrechnung wartet auf Start …","90-day reconstruction waiting to start …");return;}
  const cached=Number(s.cached_points||0),live=Number(s.live_points||0),backfilled=Number(s.backfilled_points||0),source=Number(s.source_points||0),done=Number(s.completed_points||cached),target=source>0?source:Number(s.expected_full_grid_points||25920),pct=target>0?Math.max(0,Math.min(100,done/target*100)):0,complete=Boolean(s.complete),remaining=Math.max(0,Number(s.remaining_points||target-done));
  host.textContent=walletWatchLang(`${complete?"✓":"⏳"} 90-Tage-Rückrechnung: ${fmtNumber(done,0)} / ${fmtNumber(target,0)} · ${fmtNumber(pct,1)} % · ${complete?"vollständig":String(s.state||"läuft gedrosselt")} · Cache ${fmtNumber(cached,0)} (live ${fmtNumber(live,0)} / rückgerechnet ${fmtNumber(backfilled,0)}) · Bitstamp 5m · Tor only${remaining?` · verbleibend ${fmtNumber(remaining,0)}`:""}`,`${complete?"✓":"⏳"} 90-day reconstruction: ${fmtNumber(done,0)} / ${fmtNumber(target,0)} · ${fmtNumber(pct,1)}% · ${complete?"complete":String(s.state||"throttled")} · cache ${fmtNumber(cached,0)} (live ${fmtNumber(live,0)} / backfilled ${fmtNumber(backfilled,0)}) · Bitstamp 5m · Tor only${remaining?` · ${fmtNumber(remaining,0)} remaining`:""}`);
  host.className=`result market-assessment-backfill-status ${complete?"positive":""}`;
}
'''
marker = 'function renderMarketAssessmentHistory(){'
if marker not in app:
    raise RuntimeError("history renderer marker missing")
app = app.replace(marker, renderer + marker, 1)
line = '  const payload=state.marketAssessmentHistory,rawPoints=marketAssessmentLiveTailPoints(payload,{includeIntraday:true}),points=smoothMarketAssessmentPoints(rawPoints);'
if line not in app:
    raise RuntimeError("history payload line missing")
app = app.replace(line, line + '\n  renderMarketAssessmentBackfillStatus(payload);', 1)
app_path.write_text(app, encoding="utf-8")

(root / "tests" / "test_xpub_backfill_rating_regressions.py").write_text('''from pathlib import Path\nR=Path(__file__).resolve().parents[1];C=R/"custom_components"/"bitcoin_stack_tracker"\nW=(C/"wallet_watch.py").read_text();A=(C/"frontend"/"static"/"app.js").read_text();I=(C/"__init__.py").read_text();B=(C/"buy_opportunity.py").read_text();M=(C/"market_assessment_backfill.py").read_text()\ndef test_xpub():\n assert "blockchain.scripthash.subscribe" in W and 'return "p2wpkh", False' in W and "resolved_address_type_verified" in W and "Wird ermittelt …" in A\ndef test_backfill():\n assert "async_market_assessment_backfill_loop" in I and "intraday_backfill" in I and "BACKFILL_SCORE_BATCH_POINTS = 2" in M and "marketAssessmentBackfillStatus" in A\ndef test_labels():\n assert "score_affecting_settings" in B and 'payload.pop("labels", None)' in B and "label_extreme" in A and "buy_opportunity_settings?.labels" in A\n''', encoding="utf-8")
