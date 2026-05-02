"""
Intel Agent API

Endpoints for running and retrieving bot-operator intelligence reports.
Runs as a background job so the user can navigate away safely.

Reports include both prose and structured JSON for downstream consumption.
"""

import asyncio
import json
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CHICAGO_TZ = ZoneInfo("America/Chicago")
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Query

from meridinate import settings
from meridinate.observability import log_info, log_error

router = APIRouter()

# In-memory status for the running job
_intel_status = {
    "running": False,
    "phase": "",
    "detail": "",
    "started_at": None,
    "progress": 0,
    "dialogue": [],  # [{agent, type, content, timestamp}]
    "usage": {
        "housekeeper": {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0, "fixes": 0},
        "investigator": {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0},
    },
}
_intel_lock = threading.Lock()


def _update_status(phase: str, detail: str = "", progress: int = 0):
    with _intel_lock:
        _intel_status["phase"] = phase
        _intel_status["detail"] = detail
        _intel_status["progress"] = progress


def _add_dialogue(agent: str, msg_type: str, content: str):
    """Add a dialogue entry visible to the frontend."""
    with _intel_lock:
        _intel_status["dialogue"].append({
            "agent": agent,
            "type": msg_type,  # "thinking", "tool_call", "tool_result", "fix", "conclusion"
            "content": content[:500],  # cap length
            "timestamp": datetime.now(CHICAGO_TZ).strftime("%I:%M:%S %p"),
        })
        # Keep last 50 entries
        if len(_intel_status["dialogue"]) > 50:
            _intel_status["dialogue"] = _intel_status["dialogue"][-50:]


def _update_usage(agent: str, input_tokens: int = 0, output_tokens: int = 0, tool_calls: int = 0, fixes: int = 0):
    with _intel_lock:
        u = _intel_status["usage"].get(agent, {})
        u["input_tokens"] = u.get("input_tokens", 0) + input_tokens
        u["output_tokens"] = u.get("output_tokens", 0) + output_tokens
        u["tool_calls"] = u.get("tool_calls", 0) + tool_calls
        if fixes:
            u["fixes"] = u.get("fixes", 0) + fixes
        _intel_status["usage"][agent] = u


def _run_pipeline(focus: str, skip_housekeeper: bool):
    """Run the full pipeline in a background thread."""
    from meridinate.services.intel_precompute import generate_snapshot_and_leads
    from meridinate.services.housekeeper_agent import run_housekeeper
    from meridinate.services.intel_agent import run_intel_report

    with _intel_lock:
        _intel_status["running"] = True
        _intel_status["started_at"] = datetime.now(CHICAGO_TZ).isoformat()
        _intel_status["dialogue"] = []
        _intel_status["usage"] = {
            "housekeeper": {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0, "fixes": 0},
            "investigator": {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0},
        }

    try:
        # Phase 1: Pre-computation
        forensics_data = None
        if focus == "forensics":
            _update_status("pre-compute", "Building forensic casefiles for top PnL wallets...", 10)
            _add_dialogue("system", "thinking", "Running forensics pre-computation: building casefiles for leaderboard outliers...")
            from meridinate.services.intel_precompute import generate_forensics_packet
            from meridinate.settings import CURRENT_API_SETTINGS
            forensics_data = generate_forensics_packet(limit=CURRENT_API_SETTINGS.get("intelForensicsWalletCount", 10))
            precompute = generate_snapshot_and_leads()  # still need snapshot for context
            precompute["leads"] = forensics_data["leads"]  # override leads with forensics
            precompute["raw"]["forensics_casefiles"] = forensics_data["casefiles"]
            _add_dialogue("system", "conclusion", f"Forensics pre-compute complete: {forensics_data['count']} casefiles built")
            _update_status("pre-compute", f"Built {forensics_data['count']} forensic casefiles", 20)
        else:
            _update_status("pre-compute", "Generating database snapshot and investigation leads...", 10)
            _add_dialogue("system", "thinking", "Running pre-computation: scanning database for snapshot + leads...")
            precompute = generate_snapshot_and_leads()
            convergence_count = len(precompute['raw'].get('convergence', []))
            cold_count = len(precompute['raw'].get('cold_wallets', []))
            _add_dialogue("system", "conclusion", f"Pre-compute complete: {convergence_count} convergence alerts, {cold_count} cold wallets, {len(precompute['raw'].get('deployer_watch', []))} deployer watches")
            _update_status("pre-compute", f"Found {convergence_count} convergence, {cold_count} cold wallets", 20)

        # Phase 2: Housekeeper
        housekeeper_report = ""
        housekeeper_structured = {}
        housekeeper_result = {}
        if not skip_housekeeper:
            if focus == "forensics":
                _update_status("housekeeper", "Verifying forensic casefiles...", 30)
                _add_dialogue("housekeeper", "thinking", "Starting casefile verification — checking PnL reality, contamination, trail status...")
            else:
                _update_status("housekeeper", "Verifying wallet reliability and data integrity...", 30)
                _add_dialogue("housekeeper", "thinking", "Starting wallet reliability verification — checking PnL sources, sniper bot contamination, rug exposure, pending verdicts...")
            housekeeper_result = run_housekeeper(
                precompute["snapshot"],
                precompute["quality_flags"],
                precompute["raw"],
                on_dialogue=lambda t, c: _add_dialogue("housekeeper", t, c),
                on_usage=lambda inp, out, tc, fx: _update_usage("housekeeper", inp, out, tc, fx),
                focus=focus,
                forensics_data=forensics_data,
            )
            housekeeper_report = housekeeper_result.get("report", "")
            housekeeper_structured = housekeeper_result.get("structured", {})
            fixes = housekeeper_result.get("fixes_applied", 0)
            if focus == "forensics":
                reliable = len([w for w in housekeeper_structured.get("wallet_reliability", []) if w.get("forensics_ready")])
                _add_dialogue("housekeeper", "conclusion",
                    f"Casefile verification complete — {reliable} forensics-ready, {fixes} fixes")
                _update_status("housekeeper", f"Complete — {reliable} forensics-ready", 50)
            else:
                # Housekeeper schema: wallet_reliability[] entries with trust_quality high/medium/low
                # plus a separate unreliable_wallets[] list for explicitly-flagged data issues.
                reliability = housekeeper_structured.get("wallet_reliability", []) or []
                trust_high = sum(1 for w in reliability if (w.get("trust_quality") or "").lower() == "high")
                trust_med = sum(1 for w in reliability if (w.get("trust_quality") or "").lower() == "medium")
                trust_low = sum(1 for w in reliability if (w.get("trust_quality") or "").lower() == "low")
                unreliable = len(housekeeper_structured.get("unreliable_wallets", []) or [])
                _add_dialogue("housekeeper", "conclusion",
                    f"Verification complete — {fixes} fixes, {len(reliability)} reviewed "
                    f"({trust_high} high / {trust_med} med / {trust_low} low), {unreliable} flagged unreliable")
                _update_status(
                    "housekeeper",
                    f"Complete — {fixes} fixes, {trust_high}H/{trust_med}M/{trust_low}L trust, {unreliable} unreliable",
                    50,
                )
        else:
            _update_status("housekeeper", "Skipped", 50)
            _add_dialogue("housekeeper", "conclusion", "Skipped")

        # Phase 3: Investigator — receives typed housekeeper data, not truncated prose
        if focus == "forensics":
            _update_status("investigator", "Classifying top PnL wallets (forensics)...", 60)
            _add_dialogue("investigator", "thinking", "Starting forensic classification of leaderboard outliers...")
        else:
            _update_status("investigator", "Classifying wallets and clusters (trust / avoid / watch)...", 60)
            _add_dialogue("investigator", "thinking", "Starting bot-operator classification with verified data + reliability flags...")
        result = run_intel_report(
            focus=focus,
            precomputed_snapshot=precompute["snapshot"],
            precomputed_leads=precompute["leads"],
            housekeeper_report=housekeeper_report,
            housekeeper_structured=housekeeper_structured,
            on_dialogue=lambda t, c: _add_dialogue("investigator", t, c),
            on_usage=lambda inp, out, tc: _update_usage("investigator", inp, out, tc),
        )

        result["housekeeper"] = {
            "report": housekeeper_report,
            "structured": housekeeper_structured,
            "fixes_applied": housekeeper_result.get("fixes_applied", 0),
            "tool_calls": housekeeper_result.get("tool_calls", 0),
            "skipped": skip_housekeeper,
        }

        # Store the report with structured JSON
        report_id = None
        if result.get("report"):
            _update_status("saving", "Storing report...", 95)
            import sqlite3
            try:
                from meridinate import analyzed_tokens_db as db
                with db.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS intel_reports (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            focus TEXT,
                            report TEXT,
                            report_json TEXT,
                            housekeeper_report TEXT,
                            housekeeper_json TEXT,
                            housekeeper_fixes INTEGER DEFAULT 0,
                            tool_calls INTEGER,
                            input_tokens INTEGER,
                            output_tokens INTEGER,
                            duration_seconds REAL,
                            generated_at TEXT,
                            dialogue_json TEXT,
                            precompute_json TEXT
                        )
                    """)
                    # Migrate existing tables: add new columns if missing
                    for col in ("report_json", "housekeeper_json", "generated_at", "dialogue_json", "precompute_json"):
                        try:
                            cursor.execute(f"ALTER TABLE intel_reports ADD COLUMN {col} TEXT")
                        except Exception:
                            pass  # Column already exists

                    chicago_now = datetime.now(CHICAGO_TZ).strftime("%b %d, %Y %I:%M %p %Z")

                    # Capture transcript from in-memory dialogue before it's wiped
                    with _intel_lock:
                        dialogue_snapshot = list(_intel_status.get("dialogue", []))

                    cursor.execute(
                        "INSERT INTO intel_reports (focus, report, report_json, housekeeper_report, housekeeper_json, housekeeper_fixes, tool_calls, input_tokens, output_tokens, duration_seconds, generated_at, dialogue_json, precompute_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            result.get("focus", focus),
                            result.get("report", ""),
                            json.dumps(result.get("structured", {})) if result.get("structured") else None,
                            housekeeper_report,
                            json.dumps(housekeeper_structured) if housekeeper_structured else None,
                            housekeeper_result.get("fixes_applied", 0),
                            result.get("tool_calls", 0),
                            result.get("input_tokens", 0),
                            result.get("output_tokens", 0),
                            result.get("duration_seconds", 0),
                            chicago_now,
                            json.dumps(dialogue_snapshot) if dialogue_snapshot else None,
                            json.dumps(precompute["raw"], default=str) if precompute.get("raw") else None,
                        ),
                    )
                    report_id = cursor.lastrowid
                # conn is committed and closed here

            except Exception as e:
                log_error(f"[Intel] Failed to store report: {e}")
                import traceback
                traceback.print_exc()

        # Create recommendations AFTER report is committed (separate DB connection)
        # First: deterministically compile from classifications, filling gaps the model missed
        if report_id and result.get("structured"):
            try:
                from meridinate.services.recommendation_executor import create_recommendations_from_report
                structured = result["structured"]

                # Deterministic compilation: ensure every classification has a matching action.
                # Bias toward shadowing: any wallet that surfaces in classifications without a
                # confident allowlist/denylist verdict gets a monitor_wallet recommendation, so
                # Wallet Shadow accumulates trade data on every plausibly-interesting wallet.
                model_actions = structured.get("recommended_actions", [])
                model_targets = {a.get("target_address") for a in model_actions}
                # Track wallets already getting a monitor/shadow action so we don't double-emit
                already_monitored = {
                    a.get("target_address") for a in model_actions
                    if a.get("action_type") in ("monitor_wallet", "add_bot_allowlist_wallet")
                }

                compiled_actions = list(model_actions)

                def _ensure_monitor(addr: str, label: str, reason: str, confidence: str = "medium") -> None:
                    """Idempotently add a monitor_wallet action for an address."""
                    if not addr or addr in already_monitored:
                        return
                    compiled_actions.append({
                        "action_type": "monitor_wallet",
                        "target_type": "wallet",
                        "target_address": addr,
                        "payload": {"label": label[:120]},
                        "reason": reason,
                        "confidence": confidence,
                        "expected_bot_effect": "Wallet added to Wallet Shadow for live trade-by-trade observation",
                    })
                    already_monitored.add(addr)

                # PESSIMISTIC DENYLIST: only emit a denylist rec when the model gave a non-trivial
                # type beyond bare 'high_rug_exposure'. A wallet flagged solely on high rug exposure
                # is most likely a profitable scalper — downgrade to monitor_wallet instead.
                for dc in structured.get("denylist_candidates", []):
                    addr = dc.get("address")
                    if not addr:
                        continue
                    deny_type = (dc.get("type") or "toxic_flow").lower()
                    is_strong_signal = deny_type not in ("high_rug_exposure",)
                    if dc.get("confidence") in ("high", "medium") and is_strong_signal:
                        if addr not in model_targets:
                            compiled_actions.append({
                                "action_type": "add_bot_denylist_wallet",
                                "target_type": "wallet",
                                "target_address": addr,
                                "payload": {"deny_type": deny_type},
                                "reason": dc.get("reason", "Classified as denylist by Investigator"),
                                "confidence": dc.get("confidence", "medium"),
                                "expected_bot_effect": "Wallet will be filtered from positive confluence signals",
                            })
                    else:
                        # Bare high rug exposure or low confidence → shadow it instead, do not denylist.
                        _ensure_monitor(
                            addr,
                            label=f"Possible scalper - {dc.get('reason', 'high rug exposure')[:60]}",
                            reason=f"Downgraded from denylist (rug exposure alone insufficient): {dc.get('reason', '')}",
                            confidence="low",
                        )

                # CRASH TRADER / SCALPER: high PnL + high rug exposure pattern. Always shadow.
                for sc in structured.get("profitable_scalper_candidates", []):
                    addr = sc.get("address")
                    if addr and addr not in model_targets:
                        signals = sc.get("supporting_signals", []) or []
                        label_bits = " / ".join(s for s in signals[:2]) or "Profitable Scalper"
                        compiled_actions.append({
                            "action_type": "monitor_wallet",
                            "target_type": "wallet",
                            "target_address": addr,
                            "payload": {"label": f"Scalper - {label_bits}"[:120]},
                            "reason": sc.get("reason", "Profitable but high rug exposure — shadow without trusting"),
                            "confidence": sc.get("confidence", "medium"),
                            "expected_bot_effect": "Wallet added to Wallet Shadow; not used for anti-rug confluence",
                        })
                        already_monitored.add(addr)

                # WATCH-ONLY: keep the watchlist tag AND auto-shadow so live trade data accumulates.
                for wo in structured.get("watch_only", []):
                    addr = wo.get("address")
                    if not addr:
                        continue
                    if addr not in model_targets:
                        compiled_actions.append({
                            "action_type": "add_watch_wallet",
                            "target_type": "wallet",
                            "target_address": addr,
                            "payload": {},
                            "reason": wo.get("reason", "Classified as watch-only by Investigator"),
                            "confidence": "medium",
                            "expected_bot_effect": wo.get("monitor_for", "Flag for manual review when seen on new tokens"),
                        })
                    _ensure_monitor(
                        addr,
                        label=f"Watch - {wo.get('monitor_for', 'pending classification')[:60]}",
                        reason=wo.get("reason", "Default-to-shadow on watch-only classification"),
                        confidence="medium",
                    )

                # ALLOWLIST: high confidence only. Auto-shadow happens in the executor on approval.
                for ac in structured.get("allowlist_candidates", []):
                    if ac.get("confidence") == "high" and ac.get("address") not in model_targets:
                        compiled_actions.append({
                            "action_type": "add_bot_allowlist_wallet",
                            "target_type": "wallet",
                            "target_address": ac["address"],
                            "payload": {},
                            "reason": ac.get("reason", "Classified as allowlist by Investigator"),
                            "confidence": ac.get("confidence", "high"),
                            "expected_bot_effect": "Wallet will count as positive anti-rug confluence signal (auto-shadows on approval)",
                        })

                compiled_count = len(compiled_actions) - len(model_actions)
                if compiled_count > 0:
                    log_info(f"[Intel] Deterministic compilation added {compiled_count} recommendations "
                             f"(model produced {len(model_actions)}, total {len(compiled_actions)})")

                structured["recommended_actions"] = compiled_actions

                recs = create_recommendations_from_report(report_id, structured)
                if recs:
                    _add_dialogue("system", "conclusion",
                        f"Created {len(recs)} recommendations for review "
                        f"({len(model_actions)} from model, {compiled_count} compiled)")
            except Exception as rec_err:
                log_error(f"[Intel] Failed to create recommendations: {rec_err}")
                import traceback
                traceback.print_exc()

        _update_status("complete", f"Report ready — {result.get('tool_calls', 0)} queries", 100)

    except Exception as e:
        log_error(f"[Intel] Pipeline error: {e}")
        _update_status("error", str(e), 0)
    finally:
        with _intel_lock:
            _intel_status["running"] = False


@router.post("/api/intel/run")
async def run_intel_report_endpoint(
    focus: str = Query("general", description="Focus: general, convergence, deployer, migrations, starred"),
    skip_housekeeper: bool = Query(False, description="Skip Housekeeper verification"),
):
    """Start the intel pipeline as a background job."""
    with _intel_lock:
        if _intel_status["running"]:
            return {"status": "already_running", "phase": _intel_status["phase"]}

    # Run in background thread
    thread = threading.Thread(target=_run_pipeline, args=(focus, skip_housekeeper), daemon=True)
    thread.start()

    return {"status": "started", "focus": focus}


@router.get("/api/intel/status")
async def get_intel_status():
    """Get the current status of the running intel pipeline."""
    with _intel_lock:
        return dict(_intel_status)

def _convert_report_timestamps(report: dict) -> dict:
    """Convert generated_at from UTC (old rows) or Chicago (new rows) to Chicago display time."""
    raw = report.get("generated_at", "")
    if not raw:
        return report
    # If already has timezone abbreviation (CDT/CST) or AM/PM, it's already converted — keep as-is
    if "CDT" in raw or "CST" in raw or "AM" in raw or "PM" in raw:
        return report
    # Otherwise it's UTC from CURRENT_TIMESTAMP — convert to Chicago
    try:
        from datetime import datetime as dt
        # SQLite CURRENT_TIMESTAMP format: "2026-04-09 01:47:03"
        utc_time = dt.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        chicago_time = utc_time.astimezone(CHICAGO_TZ)
        report["generated_at"] = chicago_time.strftime("%b %d, %Y %I:%M %p %Z")
    except (ValueError, TypeError):
        pass  # Leave as-is if format is unexpected
    return report


@router.get("/api/intel/reports")
async def get_intel_reports(limit: int = Query(10, ge=1, le=50)):
    """Get recent intelligence reports."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM intel_reports ORDER BY generated_at DESC LIMIT ?",
                (limit,),
            )
            rows = [_convert_report_timestamps(dict(r)) for r in await cursor.fetchall()]
            return {"reports": rows}
    except Exception:
        return {"reports": []}


@router.get("/api/intel/latest")
async def get_latest_report():
    """Get the most recent intelligence report."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM intel_reports ORDER BY generated_at DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            if row:
                return _convert_report_timestamps(dict(row))
            return {"report": None}
    except Exception:
        return {"report": None}


@router.get("/api/intel/reports/{report_id}/bundle")
async def download_bundle(report_id: int):
    """Download a full AI handoff bundle for a report — single JSON with all artifacts."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM intel_reports WHERE id = ?", (report_id,))
            row = await cursor.fetchone()
            if not row:
                return {"error": f"Report {report_id} not found"}

            r = _convert_report_timestamps(dict(row))

            # Parse stored JSON fields
            def _parse(val):
                if not val:
                    return None
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return None

            # Fetch recommendations for this report
            rec_cursor = await conn.execute(
                "SELECT * FROM intel_recommendations WHERE report_id = ? ORDER BY id",
                (report_id,),
            )
            recs = [dict(rec) for rec in await rec_cursor.fetchall()]

            bundle = {
                "metadata": {
                    "report_id": r.get("id"),
                    "focus": r.get("focus"),
                    "generated_at": r.get("generated_at"),
                    "duration_seconds": r.get("duration_seconds"),
                    "input_tokens": r.get("input_tokens"),
                    "output_tokens": r.get("output_tokens"),
                    "tool_calls": r.get("tool_calls"),
                    "housekeeper_fixes": r.get("housekeeper_fixes"),
                    "models": {
                        "housekeeper": "claude-sonnet-4-20250514",
                        "investigator": "claude-sonnet-4-20250514",
                    },
                },
                "precompute": _parse(r.get("precompute_json")),
                "housekeeper": {
                    "report": r.get("housekeeper_report"),
                    "structured": _parse(r.get("housekeeper_json")),
                },
                "investigator": {
                    "report": r.get("report"),
                    "structured": _parse(r.get("report_json")),
                },
                "transcript": _parse(r.get("dialogue_json")),
                "recommendations": recs if recs else None,
            }

            from fastapi.responses import Response
            return Response(
                content=json.dumps(bundle, indent=2, default=str),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="intel-bundle-{report_id}-{r.get("focus", "general")}.json"'
                },
            )
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/intel/reports/{report_id}/report.md")
async def download_report_md(report_id: int):
    """Download a human-readable markdown report."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM intel_reports WHERE id = ?", (report_id,))
            row = await cursor.fetchone()
            if not row:
                return {"error": f"Report {report_id} not found"}

            r = _convert_report_timestamps(dict(row))

            md = f"""# Meridinate Intel Report #{r.get('id')}

**Focus:** {r.get('focus', 'general')}
**Generated:** {r.get('generated_at')}
**Duration:** {r.get('duration_seconds', 0)}s
**Tokens:** {r.get('input_tokens', 0)} in / {r.get('output_tokens', 0)} out
**Tool Calls:** {r.get('tool_calls', 0)}
**Housekeeper Fixes:** {r.get('housekeeper_fixes', 0)}

---

{r.get('report', '')}
"""

            from fastapi.responses import Response
            return Response(
                content=md,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="intel-report-{report_id}-{r.get("focus", "general")}.md"'
                },
            )
    except Exception as e:
        return {"error": str(e)}
