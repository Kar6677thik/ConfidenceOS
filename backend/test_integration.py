"""
test_integration.py — Real-time integration tests for ConfidenceOS.

Starts a real uvicorn server, then tests every REST endpoint and a WebSocket
connection across all 6 modules.

Run:
    python test_integration.py
"""

import sys
import json
import time
import threading
import asyncio
import urllib.request
import urllib.error

import uvicorn
from main import app


# ─── Helpers ─────────────────────────────────────────────────────────────────

BASE = "http://127.0.0.1:8899"
passed = 0
failed = 0
errors = []


def check(test_name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {test_name}")
    else:
        failed += 1
        msg = f"  FAIL  {test_name}" + (f" -- {detail}" if detail else "")
        print(msg)
        errors.append(msg)


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def GET(path):
    """HTTP GET, returns (status_code, parsed_json)."""
    try:
        r = urllib.request.urlopen(f"{BASE}{path}")
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()) if e.readable() else {}


def POST(path, body=None):
    """HTTP POST with optional JSON body, returns (status_code, parsed_json)."""
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read() if e.readable() else b""
        try:
            return e.code, json.loads(body_text)
        except Exception:
            return e.code, {"raw": body_text.decode(errors="replace")}


def ws_receive(n=2, timeout=10):
    """Connect to WebSocket and receive n messages. Uses websockets library or raw."""
    import websockets.sync.client as wsc
    messages = []
    with wsc.connect(f"ws://127.0.0.1:8899/ws/sensors") as ws:
        for _ in range(n):
            raw = ws.recv(timeout=timeout)
            messages.append(json.loads(raw))
    return messages


# ─── Start Server ────────────────────────────────────────────────────────────

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8899, log_level="error")


server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# Wait for server to start
print("Starting server on port 8899...")
for i in range(30):
    try:
        urllib.request.urlopen(f"{BASE}/api/health")
        break
    except Exception:
        time.sleep(0.3)
else:
    print("FATAL: Server did not start in 9 seconds")
    sys.exit(1)

print("Server ready.\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 1: Sensor Simulator
# ═══════════════════════════════════════════════════════════════════════════════

section("MODULE 1: Sensor Simulator")

code, data = GET("/api/health")
check("GET /api/health returns 200", code == 200)
check("Health status=ok", data.get("status") == "ok")
check("Health lists active modules", len(data.get("modules", {})) >= 5)
check("Health has advisory engine", data.get("modules", {}).get("advisory_engine") == "active")

code, data = POST("/api/scenario/reset")
check("POST /api/scenario/reset returns 200", code == 200)
check("Reset status=reset", data.get("status") == "reset")

code, data = POST("/api/scenario/load")
check("POST /api/scenario/load returns 200", code == 200)
check("Load status=loaded", data.get("status") == "loaded")

code, data = GET("/api/scenario/load?scenario_path=nonexistent.json")
# This is a POST endpoint, GET should fail or we test POST with bad path
code, data = POST("/api/scenario/load?scenario_path=nonexistent.json")
check("Load bad path returns 404", code == 404)


# ─── WebSocket Stream ───────────────────────────────────────────────────────

section("MODULE 1: WebSocket Stream")

try:
    msgs = ws_receive(n=3, timeout=8)
    check("WebSocket received 3 messages", len(msgs) == 3)
    msg = msgs[0]
    check("WS type=sensor_update", msg.get("type") == "sensor_update")
    check("WS has 6 readings", len(msg.get("readings", [])) == 6)
    for key in ("readings", "confidence", "mass_balance", "mode", "stale_flags", "new_anomalies", "plant_context", "incidents"):
        check(f"WS has '{key}'", key in msg)

    sensor_types = {r["sensor_type"] for r in msg["readings"]}
    check("All 6 sensor types present",
          sensor_types == {"level", "flow_in", "flow_out", "pressure", "temperature", "valve"})

    # Value range validation
    for r in msg["readings"]:
        v, st = r["value"], r["sensor_type"]
        bounds = {"level": (0,200), "flow_in": (0,500), "flow_out": (0,500),
                  "pressure": (0,100), "temperature": (60,800), "valve": (0,100)}
        lo, hi = bounds.get(st, (0, 99999))
        check(f"  {r['sensor_id']} value {v} in [{lo},{hi}]", lo <= v <= hi)

    # Confidence structure
    c = msg["confidence"][0]
    for key in ("sensor_id", "confidence_pct", "tier", "sub_scores", "reasons", "evidence", "namur_state", "recommended_action", "dominant_factor"):
        check(f"WS confidence has '{key}'", key in c)

    # Mass-balance structure
    mb = msg["mass_balance"]
    for key in ("implied_level", "measured_level", "discrepancy", "flags"):
        check(f"WS mass_balance has '{key}'", key in mb)

    # Mode structure
    for key in ("mode", "is_active", "tier_thresholds", "stale_flags"):
        check(f"WS mode has '{key}'", key in msg["mode"])

except Exception as e:
    check(f"WebSocket test (exception: {e})", False, str(e))


# ─── DB persistence ─────────────────────────────────────────────────────────

time.sleep(7)  # wait for at least one PERSIST_READINGS_INTERVAL cycle (default 5 s)

code, data = GET("/api/sensors/history/LT-5100?hours=1&limit=10")
check("GET /api/sensors/history returns 200", code == 200)
check("History count > 0 (persisted)", data.get("count", 0) > 0, f"count={data.get('count')}")

code, data = GET("/api/sensors/latest")
check("GET /api/sensors/latest returns 200", code == 200)
check("Latest has readings", isinstance(data.get("readings"), list))

code, data = GET("/api/sensors/history/FAKE-0000")
check("Unknown sensor history: 200, count=0", code == 200 and data.get("count") == 0)


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 2: Confidence Scoring
# ═══════════════════════════════════════════════════════════════════════════════

section("MODULE 2: Confidence Scoring")

code, data = GET("/api/confidence")
check("GET /api/confidence returns 200", code == 200)
conf_list = data.get("confidence", [])
check("6 sensors scored", len(conf_list) == 6)

for c in conf_list:
    pct, tier = c["confidence_pct"], c["tier"]
    check(f"  {c['sensor_id']} pct={pct} in [0,100]", 0 <= pct <= 100)
    check(f"  {c['sensor_id']} tier={tier} valid",
          tier in ("HIGH", "MEDIUM", "LOW", "CRITICAL"))
    # Tier-pct consistency
    if pct >= 80: expected = "HIGH"
    elif pct >= 50: expected = "MEDIUM"
    elif pct >= 20: expected = "LOW"
    else: expected = "CRITICAL"
    check(f"  {c['sensor_id']} pct={pct} -> tier={expected}", tier == expected)

    for sk in ("calibration", "stability", "cross_sensor", "physical_plausibility"):
        v = c["sub_scores"][sk]
        check(f"  {c['sensor_id']} sub_score {sk}={v} in [0,1]", 0 <= v <= 1)

# LT-5100 (47 days uncalibrated)
code, data = GET("/api/confidence/LT-5100")
check("GET /api/confidence/LT-5100 returns 200", code == 200)
check("LT-5100 confidence reduced by aged calibration", data["confidence_pct"] < 100,
      f"got {data['confidence_pct']}%")
check("LT-5100 has calibration reason (47 days)",
      any("47" in r for r in data.get("reasons", [])))
check("LT-5100 has calibration evidence",
      any(e.get("category") == "calibration" and e.get("status") != "OK" for e in data.get("evidence", [])))
for key in ("evidence", "namur_state", "recommended_action", "dominant_factor"):
    check(f"LT-5100 confidence has '{key}'", key in data)

code, _ = GET("/api/confidence/NONEXISTENT")
check("Unknown sensor confidence returns 404", code == 404)

code, data = GET("/api/assumptions")
check("GET /api/assumptions returns 200", code == 200)
check("Assumptions include confidence_weights", "confidence_weights" in data.get("assumptions", {}))
check("Assumptions include mass_balance_tolerance", "mass_balance_tolerance" in data.get("assumptions", {}))

code, data = GET("/api/asset-model")
check("GET /api/asset-model returns 200", code == 200)
check("Asset model is read-only trust layer", data.get("read_only_trust_layer") is True)
check("Asset model equipment id V-5100", data.get("asset_model", {}).get("equipment", {}).get("equipment_id") == "V-5100")

code, data = GET("/api/integration/read-only-layer")
check("GET /api/integration/read-only-layer returns 200", code == 200)
check("Integration layer disables control writes", data.get("control_writes_enabled") is False)
check("Integration layer lists SimulatorProvider", any(p.get("provider_id") == "simulator" for p in data.get("available_providers", [])))

code, data = GET("/api/model/graph")
check("GET /api/model/graph returns 200", code == 200)
check("Model graph is read-only", data.get("read_only_trust_layer") is True)
check("Model graph has nodes", len(data.get("nodes", [])) >= 6)

code, data = GET("/api/model/assets")
check("GET /api/model/assets returns 200", code == 200)
check("Model assets include V-5100", any(item.get("asset_id") == "V-5100" for item in data.get("assets", [])))

code, data = GET("/api/model/signals")
check("GET /api/model/signals returns 200", code == 200)
check("Model signals include LT-5100", any(item.get("id") == "LT-5100" for item in data.get("signals", [])))

code, data = GET("/api/templates")
check("GET /api/templates returns 200", code == 200)
check("Template catalog has equipment templates", len(data.get("equipment_templates", [])) >= 1)

code, data = GET("/api/screens/generated?role=Operator&context=auto")
check("GET /api/screens/generated returns 200", code == 200)
check("Generated screen route=/runtime", data.get("route") == "/runtime")
check("Generated screen has faceplates", len(data.get("faceplates", [])) >= 1)
check("Generated screen includes provenance", "provenance" in data)

code, data = GET("/api/runtime/navigation")
check("GET /api/runtime/navigation returns 200", code == 200)
check("Runtime navigation has areas", len(data.get("navigation", {}).get("areas", [])) >= 1)

code, data = GET("/api/runtime/equipment/V-5100")
check("GET /api/runtime/equipment/V-5100 returns 200", code == 200)
check("Runtime equipment id V-5100", data.get("equipment_id") == "V-5100")

POST("/api/studio/reset")
code, data = GET("/api/studio/imported-signals")
check("GET /api/studio/imported-signals returns 200", code == 200)
check("Studio imports simulator tags", len(data.get("signals", [])) >= 6)

code, data = POST("/api/studio/auto-map")
check("POST /api/studio/auto-map returns 200", code == 200)
check("Studio auto-map has suggestions", len(data.get("suggestions", [])) >= 1)

code, data = POST("/api/studio/assign-template", {"asset_id": "V-5100", "template_id": "vessel", "approved": True})
check("POST /api/studio/assign-template returns 200", code == 200)
check("Studio assignment approved", data.get("assignment", {}).get("approved") is True)

code, data = POST("/api/studio/generate", {"role": "Engineer", "context": "auto"})
check("POST /api/studio/generate returns 200", code == 200)
check("Studio generate returns manifest", data.get("route") == "/runtime")

code, data = GET("/api/studio/validation")
check("GET /api/studio/validation returns 200", code == 200)
check("Studio validation reports status", "status" in data)

code, data = GET("/api/studio/diff")
check("GET /api/studio/diff returns 200", code == 200)
check("Studio diff reports changes", "changes" in data)

code, data = POST("/api/studio/publish")
check("POST /api/studio/publish returns 200", code == 200)
check("Studio publish status", data.get("status") == "published")

code, data = GET("/api/shift-channel")
check("GET /api/shift-channel returns 200", code == 200)
check("Shift channel has pinned/thread fields", "pinned" in data and "thread" in data)

code, data = POST("/api/shift-channel/note", {"plant_id": "plant-a", "author": "Operator", "message": "Field verification pending for LT-5100."})
check("POST /api/shift-channel/note returns 200", code == 200)
check("Shift note created", data.get("note", {}).get("type") == "operator_note")

POST("/api/shift-channel/reset")
POST("/api/studio/reset")

code, data = GET("/api/confidence/explain/LT-5100")
check("GET /api/confidence/explain/LT-5100 returns 200", code == 200)
for key in ("formula", "sub_scores", "dominant_factor", "strongest_evidence",
            "counter_evidence", "verdict", "recommended_action", "related_assumptions"):
    check(f"  Explanation has '{key}'", key in data)
check("Explanation has 4 formula terms", len(data.get("formula", {}).get("terms", [])) == 4)
check("Explanation links related assumptions", len(data.get("related_assumptions", [])) > 0)

code, data = GET("/api/confidence/LT-5100/explain")
check("GET /api/confidence/LT-5100/explain alias returns 200", code == 200)
check("Alias sensor_id=LT-5100", data.get("sensor_id") == "LT-5100")


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 3: Mass-Balance
# ═══════════════════════════════════════════════════════════════════════════════

section("MODULE 3: Mass-Balance")

code, data = GET("/api/mass-balance/state")
check("GET /api/mass-balance/state returns 200", code == 200)
st = data.get("state")
check("State not None", st is not None)
if st:
    for key in ("implied_level", "measured_level", "tolerance", "window_seconds"):
        check(f"  State has '{key}'", key in st)
    check("  Window=900s", st["window_seconds"] == 900)

code, data = GET("/api/mass-balance/flags")
check("GET /api/mass-balance/flags returns 200", code == 200)
check("Flags has 'count'", "count" in data)


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 4: Sensor Health Timeline
# ═══════════════════════════════════════════════════════════════════════════════

section("MODULE 4: Sensor Health Timeline")

cal_ages = {"LT-5100": 47.0, "FI-2010": 12.0, "FO-2020": 15.0,
            "PT-3100": 5.0, "TT-4100": 30.0, "ZT-6100": 8.0}

for sid, expected in cal_ages.items():
    code, d = GET(f"/api/sensors/{sid}/health")
    check(f"GET /api/sensors/{sid}/health returns 200", code == 200)
    for key in ("calibration", "anomalies", "drift_trend", "maintenance"):
        check(f"  {sid} has '{key}'", key in d)
    check(f"  {sid} cal age={expected}", d["calibration"]["age_days"] == expected)
    check(f"  {sid} cal interval=90", d["calibration"]["interval_days"] == 90)
    ratio = expected / 90.0
    status = d["calibration"]["status"]
    if ratio >= 1.0: check(f"  {sid} status=expired", status == "expired")
    elif ratio >= 0.7: check(f"  {sid} status=due_soon", status == "due_soon")
    else: check(f"  {sid} status=current", status == "current")

code, data = GET("/api/anomalies?hours=24&limit=50")
check("GET /api/anomalies returns 200", code == 200)
check("Has 'count'", "count" in data)

code, data = GET("/api/anomalies/LT-5100")
check("GET /api/anomalies/LT-5100 returns 200", code == 200)
check("sensor_id=LT-5100", data.get("sensor_id") == "LT-5100")

code, data = GET("/api/anomalies/FAKE-0000")
check("Unknown sensor anomalies: 200, count=0", code == 200 and data.get("count") == 0)

code, data = GET("/api/sensors/UNKNOWN-999/health")
check("Unknown sensor health returns 200 gracefully", code == 200)
check("Unknown sensor cal age=0", data["calibration"]["age_days"] == 0)


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 5: Startup Mode
# ═══════════════════════════════════════════════════════════════════════════════

section("MODULE 5: Startup Mode")

# Ensure NORMAL
POST("/api/mode/startup", {"active": False})

code, d = GET("/api/mode")
check("GET /api/mode returns 200", code == 200)
check("mode=NORMAL", d["mode"] == "NORMAL")
check("is_active=False", d["is_active"] is False)
check("NORMAL tier MEDIUM=50", d["tier_thresholds"]["MEDIUM"] == 50)
check("NORMAL MB mult=1.0", d["mass_balance_tolerance_multiplier"] == 1.0)
check("NORMAL stale_threshold=None", d["stale_threshold_seconds"] is None)

# Activate
code, d = POST("/api/mode/startup", {"active": True})
check("Activate returns 200", code == 200)
check("status=activated", d["status"] == "activated")
check("mode=STARTUP", d["mode"] == "STARTUP")
check("STARTUP tier MEDIUM=70", d["tier_thresholds"]["MEDIUM"] == 70)
check("STARTUP MB mult=0.5", d["mass_balance_tolerance_multiplier"] == 0.5)
check("STARTUP stale=480", d["stale_threshold_seconds"] == 480.0)

# WS in startup mode
try:
    msgs = ws_receive(n=1, timeout=5)
    check("WS in STARTUP: mode=STARTUP", msgs[0]["mode"]["mode"] == "STARTUP")
    check("WS in STARTUP: tier MEDIUM=70",
          msgs[0]["mode"]["tier_thresholds"]["MEDIUM"] == 70)
    # Check borderline sensors
    for c in msgs[0]["confidence"]:
        if 50 <= c["confidence_pct"] < 70:
            check(f"  {c['sensor_id']} at {c['confidence_pct']}%: LOW in startup",
                  c["tier"] == "LOW")
except Exception as e:
    check(f"WS startup test (exception)", False, str(e))

# Deactivate
code, d = POST("/api/mode/startup", {"active": False})
check("Deactivate returns 200", code == 200)
check("status=deactivated", d["status"] == "deactivated")
check("mode=NORMAL", d["mode"] == "NORMAL")

# Rapid toggle stress test
for _ in range(10):
    POST("/api/mode/startup", {"active": True})
    POST("/api/mode/startup", {"active": False})
code, d = GET("/api/mode")
check("Rapid toggle 10x: mode=NORMAL", d["mode"] == "NORMAL")

# Edge: acknowledge non-existent stale
code, _ = POST("/api/mode/startup/acknowledge/LT-5100")
check("Acknowledge non-existent: 404", code == 404)

# Edge: invalid body
code, _ = POST("/api/mode/startup", {})
check("Empty body: 422", code == 422)


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 6: Shift Handover Brief
# ═══════════════════════════════════════════════════════════════════════════════

section("MODULE 6: Shift Handover Brief")

code, d = POST("/api/handover/generate")
check("POST /api/handover/generate returns 200", code == 200)
check("source=fallback", d["source"] == "fallback")
check("Brief text non-empty", len(d.get("brief", "")) > 50)
check("Has generated_at", "generated_at" in d)
check("Has system_state_summary", "system_state_summary" in d)

brief = d["brief"]
check("Brief has OVERALL PLANT STATUS", "OVERALL PLANT STATUS" in brief)
check("Brief has MASS-BALANCE STATUS", "MASS-BALANCE STATUS" in brief)
check("Brief has RECOMMENDED ACTIONS", "RECOMMENDED ACTIONS" in brief)

summary = d["system_state_summary"]
for key in ("mode", "total_sensors", "healthy_sensors", "degraded_count",
            "anomaly_count", "mass_balance_flags", "plant_context", "incidents"):
    check(f"  Summary has '{key}'", key in summary)
check("  total_sensors=6", summary["total_sensors"] == 6)

code, d = GET("/api/handover/latest")
check("GET /api/handover/latest returns 200", code == 200)
check("Latest brief exists", d.get("brief") is not None)

# Brief in STARTUP mode
POST("/api/mode/startup", {"active": True})
code, d = POST("/api/handover/generate")
check("STARTUP brief returns 200", code == 200)
check("STARTUP brief mode=STARTUP", d["system_state_summary"]["mode"] == "STARTUP")
POST("/api/mode/startup", {"active": False})


# ═══════════════════════════════════════════════════════════════════════════════
#  CROSS-MODULE: End-to-End Scenarios
# ═══════════════════════════════════════════════════════════════════════════════

section("CROSS-MODULE: End-to-End Scenarios")

# Reset + stream
POST("/api/scenario/reset")
try:
    msgs = ws_receive(n=1, timeout=5)
    check("Reset + fresh stream works", msgs[0]["type"] == "sensor_update")
except Exception as e:
    check("Reset + fresh stream", False, str(e))

# Full cycle: Startup -> Stream -> Handover -> Deactivate
POST("/api/mode/startup", {"active": True})
try:
    msgs = ws_receive(n=1, timeout=5)
    check("Cycle: STARTUP stream works", msgs[0]["mode"]["mode"] == "STARTUP")
except Exception as e:
    check("Cycle: STARTUP stream", False, str(e))
code, _ = POST("/api/handover/generate")
check("Cycle: handover in STARTUP=200", code == 200)
POST("/api/mode/startup", {"active": False})
_, d = GET("/api/mode")
check("Cycle: back to NORMAL", d["mode"] == "NORMAL")

# Data persistence: history grows
_, d1 = GET("/api/sensors/history/FI-2010?hours=1&limit=1000")
c1 = d1["count"]
try:
    ws_receive(n=6, timeout=12)
except Exception:
    pass
deadline = time.time() + 6.0
c2 = c1
while time.time() < deadline:
    time.sleep(0.5)
    _, d2 = GET("/api/sensors/history/FI-2010?hours=1&limit=1000")
    c2 = d2["count"]
    if c2 > c1:
        break
check(f"History grows after streaming ({c1} -> {c2})", c2 > c1)


# ═══════════════════════════════════════════════════════════════════════════════
#  RESULTS
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print(f"  INTEGRATION TEST RESULTS")
print(f"{'='*60}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
print(f"  Total:  {passed + failed}")
print(f"{'='*60}")

if errors:
    print(f"\n  FAILURES:")
    for e in errors:
        print(f"    {e}")
    print()

if __name__ == "__main__":
    sys.exit(1 if failed > 0 else 0)
