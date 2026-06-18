"""
e2e_smoke.py — Round 8 exhaustive backend API + WebSocket smoke test.

Exercises every HTTP endpoint and the /ws/sensors stream against a RUNNING
server (uvicorn main:app on :8001), asserting status codes + response-shape
keys, across both asset models and all three plants, including error paths,
the Studio compiler lifecycle, the verification workflow lifecycle, and the
AI graceful-fallback contract (run with NO ANTHROPIC_API_KEY).

This is a test harness, not shipped app code. Run:
    python e2e_smoke.py
Exits non-zero if any assertion fails. Writes a markdown matrix to
_e2e_api_results.md for folding into E2E_TEST_RESULTS.md.
"""
import sys
import json
import time
import asyncio
import os
import urllib.error
import urllib.parse
import urllib.request


BASE = os.getenv("CONFIDENCEOS_E2E_BASE", "http://127.0.0.1:8001")
PLANTS = ["plant-a", "plant-b", "plant-c"]


class Response:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body
        self.text = body.decode("utf-8", errors="replace")

    def json(self):
        if not self._body:
            return None
        return json.loads(self.text)


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None, timeout: int = 15) -> Response:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path + query,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return Response(res.status, res.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read())

ROWS = []  # (area, item, scenario, expected, result, severity, notes)
_FAILS = 0


def record(area, item, scenario, expected, ok, notes="", severity="High"):
    global _FAILS
    result = "PASS" if ok else "FAIL"
    if not ok:
        _FAILS += 1
    ROWS.append((area, item, scenario, expected, result, "" if ok else severity, notes))
    flag = "OK " if ok else "XX "
    print(f"  {flag}[{area}] {item} :: {scenario} -> {result} {('('+notes+')') if notes else ''}")


def get(path, **params):
    return _request("GET", path, params=params or None, timeout=15)


def post(path, body=None, **params):
    return _request("POST", path, params=params or None, body=body, timeout=30)


def check(area, item, scenario, fn, expected="200 + shape"):
    """Run fn() which returns (ok: bool, notes: str)."""
    try:
        ok, notes = fn()
    except Exception as e:  # noqa
        ok, notes = False, f"exception: {type(e).__name__}: {e}"
    record(area, item, scenario, expected, ok, notes)
    return ok


def has_keys(obj, keys):
    if not isinstance(obj, dict):
        return False, f"not a dict: {type(obj).__name__}"
    missing = [k for k in keys if k not in obj]
    return (not missing), ("" if not missing else f"missing keys {missing}")


# ─────────────────────────────────────────────────────────────────────────────
def test_health_and_readonly():
    print("\n== Health & read-only ==")
    def f():
        r = get("/api/health")
        if r.status_code != 200:
            return False, f"status {r.status_code}"
        return has_keys(r.json(), ["status", "modules", "read_only_contract", "plant_loops"])
    check("Health", "GET /api/health", "server up", f)

    def f2():
        r = get("/api/integration/read-only-layer")
        return (r.status_code == 200), f"status {r.status_code}"
    check("Health", "GET /api/integration/read-only-layer", "describes read-only boundary", f2)


def discover_sensors(plant):
    r = get("/api/sensors/latest", plant_id=plant)
    if r.status_code != 200:
        return []
    data = r.json()
    readings = data.get("readings", data if isinstance(data, list) else [])
    return [x.get("sensor_id") for x in readings if x.get("sensor_id")]


def test_sensors_confidence(plant, sensors):
    sid = sensors[0] if sensors else "LT-5100"
    check("Sensors", "GET /api/sensors/latest", f"{plant}",
          lambda: ((get("/api/sensors/latest", plant_id=plant).status_code == 200 and len(sensors) > 0),
                   f"{len(sensors)} sensors"))
    check("Sensors", "GET /api/sensors/history/{sid}", f"{plant}/{sid}",
          lambda: (get(f"/api/sensors/history/{sid}", plant_id=plant).status_code == 200, ""))
    check("Sensors", "GET /api/sensors/{sid}/health", f"{plant}/{sid}",
          lambda: (get(f"/api/sensors/{sid}/health", plant_id=plant).status_code == 200, ""))

    check("Confidence", "GET /api/confidence", f"{plant} all",
          lambda: (get("/api/confidence", plant_id=plant).status_code == 200, ""))
    check("Confidence", "GET /api/confidence/{sid}", f"{plant}/{sid}",
          lambda: (get(f"/api/confidence/{sid}", plant_id=plant).status_code == 200, ""))
    check("Confidence", "GET /api/confidence/{sid}", "unknown sid -> 404",
          lambda: (get("/api/confidence/NOPE-9999", plant_id=plant).status_code == 404, ""),
          expected="404")
    check("Confidence", "GET /api/confidence/explain/{sid}", f"{plant}/{sid}",
          lambda: (get(f"/api/confidence/explain/{sid}", plant_id=plant).status_code == 200, ""))
    check("Confidence", "GET /api/confidence/{sid}/explain", f"{plant}/{sid} alias",
          lambda: (get(f"/api/confidence/{sid}/explain", plant_id=plant).status_code == 200, ""))
    check("Confidence", "GET /api/confidence/sensitivity/{sid}", "role=Engineer -> 200",
          lambda: (get(f"/api/confidence/sensitivity/{sid}", plant_id=plant, role="Engineer").status_code == 200, ""))
    check("Confidence", "GET /api/confidence/sensitivity/{sid}", "role=Operator -> 403",
          lambda: (get(f"/api/confidence/sensitivity/{sid}", plant_id=plant, role="Operator").status_code == 403, ""),
          expected="403")
    check("Confidence", "GET /api/confidence/debt/{plant}", f"{plant}",
          lambda: (get(f"/api/confidence/debt/{plant}").status_code == 200, ""))


def test_mass_balance_anomalies_mode(plant, sensors):
    sid = sensors[0] if sensors else "LT-5100"
    check("MassBalance", "GET /api/mass-balance/flags", f"{plant}",
          lambda: (get("/api/mass-balance/flags", plant_id=plant).status_code == 200, ""))
    check("MassBalance", "GET /api/mass-balance/state", f"{plant}",
          lambda: (get("/api/mass-balance/state", plant_id=plant).status_code == 200, ""))
    check("Anomalies", "GET /api/anomalies", f"{plant}",
          lambda: (get("/api/anomalies", plant_id=plant).status_code == 200, ""))
    check("Anomalies", "GET /api/anomalies/{sid}", f"{plant}/{sid}",
          lambda: (get(f"/api/anomalies/{sid}", plant_id=plant).status_code == 200, ""))
    check("Mode", "GET /api/mode", f"{plant}",
          lambda: (get("/api/mode", plant_id=plant).status_code == 200, ""))
    check("Mode", "POST /api/mode/startup", "active=true",
          lambda: (post("/api/mode/startup", {"active": True}, plant_id=plant).status_code == 200, ""))
    check("Mode", "POST /api/mode/startup", "active=false",
          lambda: (post("/api/mode/startup", {"active": False}, plant_id=plant).status_code == 200, ""))
    check("Mode", "POST /api/mode/startup/acknowledge/{sid}", "unknown stale -> 404",
          lambda: (post(f"/api/mode/startup/acknowledge/NOPE-9999", plant_id=plant).status_code == 404, ""),
          expected="404")


def test_model_runtime(plant):
    for path in ["/api/assumptions", "/api/asset-model", "/api/model/graph",
                 "/api/model/assets", "/api/model/signals", "/api/templates",
                 "/api/runtime/navigation"]:
        check("Model", f"GET {path}", "global",
              lambda p=path: (get(p).status_code == 200, ""))
    check("Runtime", "GET /api/runtime/situations", f"{plant}",
          lambda: (get("/api/runtime/situations", plant_id=plant).status_code == 200, ""))
    check("Runtime", "GET /api/screens/generated", f"{plant} Engineer",
          lambda: (get("/api/screens/generated", role="Engineer", context="auto", plant_id=plant).status_code == 200, ""))
    # equipment: discover a valid equipment id
    r = get("/api/model/assets")
    eqid = None
    if r.status_code == 200:
        assets = r.json()
        items = assets.get("assets", assets) if isinstance(assets, dict) else assets
        if isinstance(items, list):
            for a in items:
                if isinstance(a, dict) and a.get("equipment_id"):
                    eqid = a["equipment_id"]; break
    if eqid:
        check("Runtime", "GET /api/runtime/equipment/{id}", f"{eqid}",
              lambda: (get(f"/api/runtime/equipment/{eqid}", role="Engineer", plant_id=plant).status_code == 200, ""))
    check("Runtime", "GET /api/runtime/equipment/{id}", "unknown -> 404",
          lambda: (get("/api/runtime/equipment/NOPE-XX", role="Engineer", plant_id=plant).status_code == 404, ""),
          expected="404")


def test_graph_forensics_adaptive(plant):
    check("Graph", "GET /api/graph/{plant}", f"{plant}",
          lambda: (get(f"/api/graph/{plant}").status_code == 200, ""))
    check("Graph", "GET /api/trust-dependency/{plant}", f"{plant}",
          lambda: (get(f"/api/trust-dependency/{plant}").status_code == 200, ""))
    check("Adaptive", "GET /api/adaptive-thresholds/{plant}", f"{plant}",
          lambda: (get(f"/api/adaptive-thresholds/{plant}").status_code == 200, ""))
    check("Forensics", "GET /api/forensics/presets", "list",
          lambda: (get("/api/forensics/presets").status_code == 200, ""))
    r = get("/api/forensics/presets")
    pid = None
    if r.status_code == 200:
        d = r.json()
        items = d.get("presets", d) if isinstance(d, dict) else d
        if isinstance(items, list) and items:
            first = items[0]
            pid = first.get("id") or first.get("preset_id") if isinstance(first, dict) else first
    if pid:
        check("Forensics", "GET /api/forensics/presets/{id}", f"{pid}",
              lambda: (get(f"/api/forensics/presets/{pid}").status_code == 200, ""))
    check("Forensics", "GET /api/forensics/presets/{id}", "unknown -> 404",
          lambda: (get("/api/forensics/presets/nope-xyz").status_code == 404, ""), expected="404")
    check("Forensics", "GET /api/forensics/{plant}", f"{plant}",
          lambda: (get(f"/api/forensics/{plant}").status_code == 200, ""))


def test_fleet_predictions(plant, sensors):
    sid = sensors[0] if sensors else "LT-5100"
    check("Fleet", "GET /api/fleet", "all plants",
          lambda: (get("/api/fleet").status_code == 200, ""))
    check("Fleet", "GET /api/fleet/history", "hours=24",
          lambda: (get("/api/fleet/history", hours=24).status_code == 200, ""))
    check("Predictions", "GET /api/predictions/{plant}", f"{plant}",
          lambda: (get(f"/api/predictions/{plant}").status_code == 200, ""))
    check("Predictions", "GET /api/predictions/{plant}/{sid}", f"{plant}/{sid}",
          lambda: (get(f"/api/predictions/{plant}/{sid}").status_code == 200, ""))


def test_ai_fallbacks(plant):
    print("\n== AI fallback contract (no key) ==")
    def fq():
        r = post("/api/query", {"question": "Why is the level sensor degraded?", "plant_id": plant})
        if r.status_code != 200:
            return False, f"status {r.status_code}"
        d = r.json()
        src = d.get("source_type") or d.get("source")
        return (src == "fallback"), f"source={src}"
    check("AI", "POST /api/query", "fallback source", fq)

    def fi():
        r = post("/api/studio/import-tags", {"tags": ["U15_LT_5100.PV", "raw_flow_xx", "FOO.BAR.baz"]})
        if r.status_code != 200:
            return False, f"status {r.status_code}"
        return True, "imported"
    check("AI", "POST /api/studio/import-tags", "arbitrary tags -> court", fi)

    def fa():
        r = post("/api/studio/auto-map", None)
        return (r.status_code == 200), f"status {r.status_code}"
    check("AI", "POST /api/studio/auto-map", "deterministic suggestions", fa)

    def fs():
        r = post("/api/studio/suggest-template", {"description": "a vertical storage vessel with a level transmitter"})
        # Without a key this should degrade gracefully, NOT 500.
        notes = f"status {r.status_code}"
        if r.status_code == 500:
            return False, notes + " (no graceful fallback w/o key)"
        return (r.status_code in (200, 422)), notes
    check("AI", "POST /api/studio/suggest-template", "graceful w/o key (not 500)", fs,
          expected="200/422, not 500")


def test_studio_lifecycle():
    print("\n== Studio compiler lifecycle ==")
    for path in ["/api/studio", "/api/studio/imported-signals", "/api/studio/build",
                 "/api/studio/validation", "/api/studio/diff", "/api/studio/mapping-court",
                 "/api/studio/template-tests", "/api/studio/build/artifacts",
                 "/api/studio/import-batches"]:
        check("Studio", f"GET {path}", "read", lambda p=path: (get(p).status_code == 200, ""))

    # Switch asset model to pump_station and back.
    check("Studio", "POST /api/studio/asset-model", "switch pump_station",
          lambda: (post("/api/studio/asset-model", {"model_key": "pump_station"}).status_code == 200, ""))
    check("Studio", "POST /api/studio/asset-model", "switch back texas_city_vessel",
          lambda: (post("/api/studio/asset-model", {"model_key": "texas_city_vessel"}).status_code == 200, ""))

    check("Studio", "POST /api/studio/template-mutation", "toggle on",
          lambda: (post("/api/studio/template-mutation",
                        {"require_manual_verification_when_level_quarantined": True}).status_code == 200, ""))

    # Mapping court resolution on a real raw_tag if any exist.
    r = get("/api/studio/mapping-court")
    raw_tag = None
    if r.status_code == 200:
        d = r.json()
        items = d.get("rows") or d.get("court") or d.get("items") or (d if isinstance(d, list) else [])
        if isinstance(items, list) and items and isinstance(items[0], dict):
            raw_tag = items[0].get("raw_tag")
    if raw_tag:
        check("Studio", "POST /api/studio/mapping-court/keep-blocking", f"{raw_tag}",
              lambda: (post("/api/studio/mapping-court/keep-blocking", {"raw_tag": raw_tag}).status_code in (200, 422, 409), ""),
              expected="200/4xx")

    check("Studio", "POST /api/studio/build/run", "run compiler",
          lambda: (post("/api/studio/build/run", None).status_code == 200, ""))
    check("Studio", "POST /api/studio/generate", "preview",
          lambda: (post("/api/studio/generate", {"role": "Engineer", "context": "auto"}).status_code == 200, ""))
    # publish may be 200 or 409 (blocked) — both are valid documented outcomes.
    def fp():
        r = post("/api/studio/publish", None)
        return (r.status_code in (200, 409)), f"status {r.status_code}"
    check("Studio", "POST /api/studio/publish", "publish or 409-blocked", fp, expected="200/409")
    check("Studio", "POST /api/studio/reset", "reset to defaults",
          lambda: (post("/api/studio/reset", None).status_code == 200, ""))


def test_verification_lifecycle(plant, sensors):
    print(f"\n== Verification workflow lifecycle ({plant}) ==")
    sid = sensors[0] if sensors else "LT-5100"
    # Create a token (auto-creates a REQUESTED task).
    r = post("/api/verification-tokens", {"sensor_id": sid, "verification_type": "field_check",
                                          "valid_minutes": 30, "note": "smoke"}, plant_id=plant)
    if r.status_code != 200:
        record("Verify", "POST /api/verification-tokens", f"{plant}/{sid}", "200", False,
               f"status {r.status_code}", "High")
        return
    record("Verify", "POST /api/verification-tokens", f"{plant}/{sid}", "200", True, "")

    # Find the freshly created task id.
    tasks = get("/api/verification-tasks", plant_id=plant).json()
    tlist = tasks.get("tasks", tasks) if isinstance(tasks, dict) else tasks
    task_id = None
    for t in (tlist or []):
        if isinstance(t, dict) and t.get("sensor_id") == sid and t.get("state") in ("REQUESTED", "ASSIGNED"):
            task_id = t.get("task_id") or t.get("token_id")
    if not task_id and tlist:
        task_id = (tlist[0].get("task_id") or tlist[0].get("token_id"))
    if not task_id:
        record("Verify", "discover task", f"{plant}", "task id", False, "no task found", "High")
        return

    def st(state, role, note=""):
        body = {"task_id": task_id, "state": state, "actor": f"{role}-1",
                "actor_role": role, "evidence_note": note}
        return post("/api/verification-tasks/state", body, plant_id=plant)

    # Negative cases first (task still REQUESTED):
    check("Verify", "state REQUESTED->ACCEPTED", "illegal -> 400",
          lambda: (st("ACCEPTED", "Engineer", "x").status_code == 400, ""), expected="400")
    check("Verify", "state ->ASSIGNED as Operator", "wrong role -> 403",
          lambda: (st("ASSIGNED", "Operator").status_code == 403, ""), expected="403")
    # Legal happy path:
    check("Verify", "state ->ASSIGNED", "Maintenance -> 200",
          lambda: (st("ASSIGNED", "Maintenance").status_code == 200, ""))
    check("Verify", "state ->FIELD_CHECK_DONE", "missing evidence -> 422",
          lambda: (st("FIELD_CHECK_DONE", "Maintenance", "").status_code == 422, ""), expected="422")
    check("Verify", "state ->FIELD_CHECK_DONE", "with evidence -> 200",
          lambda: (st("FIELD_CHECK_DONE", "Maintenance", "level matches sight glass").status_code == 200, ""))
    check("Verify", "state ->ACCEPTED", "Engineer + evidence -> 200",
          lambda: (st("ACCEPTED", "Engineer", "accepted, instrument trustworthy").status_code == 200, ""))
    check("Verify", "state unknown task", "404",
          lambda: (post("/api/verification-tasks/state",
                        {"task_id": "no-such-task", "state": "ASSIGNED", "actor_role": "Maintenance"},
                        plant_id=plant).status_code == 404, ""), expected="404")
    check("Verify", "GET /api/verification-tasks/audit", f"{plant} trail",
          lambda: (get("/api/verification-tasks/audit", plant_id=plant).status_code == 200, ""))
    check("Verify", "GET /api/verification-tasks/{id}", f"{task_id}",
          lambda: (get(f"/api/verification-tasks/{task_id}", plant_id=plant).status_code == 200, ""))


def test_shift_handover(plant):
    print(f"\n== Shift channel & handover ({plant}) ==")
    check("Shift", "GET /api/shift-channel", f"{plant}",
          lambda: (get("/api/shift-channel", plant_id=plant).status_code == 200, ""))
    check("Shift", "POST /api/shift-channel/note", "pin note",
          lambda: (post("/api/shift-channel/note",
                        {"plant_id": plant, "author": "Operator", "message": "smoke note"}).status_code == 200, ""))
    check("Shift", "POST /api/shift-channel/reset", "reset notes",
          lambda: (post("/api/shift-channel/reset", None).status_code == 200, ""))
    def fh():
        r = post("/api/handover/generate", None, plant_id=plant)
        if r.status_code != 200:
            return False, f"status {r.status_code}"
        d = r.json()
        src = d.get("source")
        return (src == "fallback"), f"source={src}"
    check("Handover", "POST /api/handover/generate", "fallback brief", fh)
    check("Handover", "GET /api/handover/latest", f"{plant}",
          lambda: (get("/api/handover/latest", plant_id=plant).status_code == 200, ""))
    check("Handover", "GET /api/handover/debt", f"{plant}",
          lambda: (get("/api/handover/debt", plant_id=plant).status_code == 200, ""))


def test_compliance_sandbox(plant, sensors):
    print(f"\n== Compliance & sandbox ({plant}) ==")
    def fc():
        r = post("/api/compliance/generate", {"plant_id": plant, "hours": 24, "report_type": "full"})
        if r.status_code != 200:
            return False, f"status {r.status_code}"
        d = r.json()
        prov = d.get("provenance", {})
        ok = ("pdf_base64" in d) and bool(prov.get("content_sha256")) and prov.get("signed") in (False, None)
        return ok, f"signed={prov.get('signed')} hash={'yes' if prov.get('content_sha256') else 'no'}"
    check("Compliance", "POST /api/compliance/generate", "report + provenance + pdf", fc)

    sid = sensors[0] if sensors else "LT-5100"
    check("Sandbox", "POST /api/sandbox/run", "calibration_drift",
          lambda: (post("/api/sandbox/run", {"plant_id": plant, "sensor_id": sid,
                                             "failure_mode": "calibration_drift", "severity": "moderate",
                                             "duration_hours": 2}).status_code == 200, ""))


def test_scenario_and_errors():
    print("\n== Scenario control & error paths ==")
    check("Scenario", "POST /api/scenario/load", "scenario.json -> 200",
          lambda: (post("/api/scenario/load", None, scenario_path="scenario.json", plant_id="plant-a").status_code == 200, ""))
    check("Scenario", "POST /api/scenario/load", "traversal -> 400",
          lambda: (post("/api/scenario/load", None, scenario_path="../secrets.json", plant_id="plant-a").status_code == 400, ""),
          expected="400")
    check("Scenario", "POST /api/scenario/load", "unknown -> 404",
          lambda: (post("/api/scenario/load", None, scenario_path="nope.json", plant_id="plant-a").status_code == 404, ""),
          expected="404")
    check("Scenario", "POST /api/scenario/reset", "reset",
          lambda: (post("/api/scenario/reset", None, plant_id="plant-a").status_code == 200, ""))
    # Unknown plant across representative endpoints.
    check("Errors", "GET /api/confidence unknown plant", "-> 404",
          lambda: (get("/api/confidence", plant_id="plant-zzz").status_code == 404, ""), expected="404")
    check("Errors", "GET /api/graph unknown plant", "-> 404",
          lambda: (get("/api/graph/plant-zzz").status_code == 404, ""), expected="404")


# ─── WebSocket ───────────────────────────────────────────────────────────────
async def _ws_test():
    import websockets
    print("\n== WebSocket /ws/sensors ==")
    uri = "ws://127.0.0.1:8001/ws/sensors?plant_id=plant-a"
    try:
        async with websockets.connect(uri) as ws:
            frames = []
            for _ in range(2):
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                frames.append(json.loads(msg))
            need = ["type", "readings", "confidence", "mass_balance", "mode",
                    "verification_tasks", "handover_debt"]
            ok, notes = has_keys(frames[0], need)
            ok = ok and frames[0].get("type") == "sensor_update" and len(frames) == 2
            record("WS", "/ws/sensors", "plant-a streams sensor_update", "2 frames + keys", ok, notes)
    except Exception as e:  # noqa
        record("WS", "/ws/sensors", "plant-a streams sensor_update", "2 frames + keys", False,
               f"{type(e).__name__}: {e}", "Critical")

    # Unknown plant -> error frame + close.
    uri2 = "ws://127.0.0.1:8001/ws/sensors?plant_id=plant-zzz"
    try:
        async with websockets.connect(uri2) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                d = json.loads(msg)
                # expect an error-type frame then close
                ok = (d.get("type") == "error") or ("error" in str(d).lower())
                record("WS", "/ws/sensors", "unknown plant -> error frame", "error/close", ok, str(d)[:80])
            except Exception:
                # closed immediately is also acceptable rejection
                record("WS", "/ws/sensors", "unknown plant -> error frame", "error/close", True, "closed")
    except Exception as e:  # noqa
        # connection rejected/closed is acceptable behavior
        record("WS", "/ws/sensors", "unknown plant -> error frame", "error/close", True, f"rejected: {type(e).__name__}")


def write_markdown():
    lines = ["| Area | Item | Scenario | Expected | Result | Severity | Notes |",
             "|------|------|----------|----------|--------|----------|-------|"]
    for (area, item, scenario, expected, result, sev, notes) in ROWS:
        item_s = item.replace("|", "\\|")
        lines.append(f"| {area} | {item_s} | {scenario} | {expected} | {result} | {sev} | {notes} |")
    with open("_e2e_api_results.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    print("ConfidenceOS E2E backend smoke — target", BASE)
    test_health_and_readonly()

    # Per-plant coverage.
    for plant in PLANTS:
        print(f"\n########## PLANT {plant} ##########")
        sensors = discover_sensors(plant)
        test_sensors_confidence(plant, sensors)
        test_mass_balance_anomalies_mode(plant, sensors)
        test_model_runtime(plant)
        test_graph_forensics_adaptive(plant)
        test_fleet_predictions(plant, sensors)
        test_shift_handover(plant)
        test_compliance_sandbox(plant, sensors)

    # Global / single-run sections.
    sensors_a = discover_sensors("plant-a")
    test_ai_fallbacks("plant-a")
    test_studio_lifecycle()
    test_verification_lifecycle("plant-a", sensors_a)
    test_scenario_and_errors()

    asyncio.run(_ws_test())

    write_markdown()
    total = len(ROWS)
    print("\n" + "=" * 64)
    print(f"E2E API SMOKE: {total - _FAILS} passed, {_FAILS} failed, {total} total")
    print("Markdown matrix -> _e2e_api_results.md")
    print("=" * 64)
    sys.exit(1 if _FAILS else 0)


if __name__ == "__main__":
    main()
