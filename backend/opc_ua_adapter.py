"""
opc_ua_adapter.py — OPC UA reference adapter for ConfidenceOS (read-only).

Illustrates how to connect to a live industrial OPC UA server, subscribe to
process tags, and feed them into the read-only ConfidenceOS Trust Layer. It does
real `asyncua` subscriptions and now captures data quality (StatusCode) and the
server SourceTimestamp — but it is a REFERENCE adapter, NOT production-hardened.

TODO production (explicitly not implemented here):
  - reconnect with exponential backoff + connection-state surfacing on comms loss
  - OPC UA security: SecurityPolicy + message signing/encryption + client/server certs
  - namespace browse + dynamic node discovery (mappings below are hardcoded ns=2;s=...)
  - DataType/EUInformation-driven sensor type + engineering units (not id-prefix guesses)
  - out-of-order / late sample handling and historian (HDA) backfill
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Any
from pathlib import Path

# In production, install asyncua: `pip install asyncua`
# We use standard library types here to ensure clean stub execution without dependencies.
try:
    import asyncio
    from asyncua import Client, ua
except ImportError:
    Client = None
    ua = None

from tag_provider import TagProvider

logger = logging.getLogger("ConfidenceOS.OpcUaAdapter")


class SubscriptionHandler:
    """
    Subscription handler to receive asynchronous node change events from the OPC UA server.
    """

    def __init__(self, adapter: OpcUaAdapter):
        self.adapter = adapter

    def datachange_notification(self, node: Any, val: Any, data: Any) -> None:
        """
        Callback called automatically by the OPC UA client thread when subscription tag updates arrive.
        """
        # Node variable names can be parsed or mapped back to the database sensor IDs
        node_id_str = str(node)
        logger.debug(f"OPC UA DataChange received: {node_id_str} = {val}")

        # Extract the OPC UA DataValue's quality (StatusCode) and SourceTimestamp.
        # A real trust layer MUST honour bad/uncertain quality and the source clock,
        # not the local wall clock — otherwise a stale or bad-quality tag looks fresh.
        quality = "good"
        source_ts = None
        try:
            dv = getattr(data, "monitored_item", None)
            dv = getattr(dv, "Value", None) if dv is not None else None
            status = getattr(dv, "StatusCode", None)
            if status is not None and not status.is_good():
                quality = "bad" if status.value else "uncertain"
            src = getattr(dv, "SourceTimestamp", None)
            if src is not None:
                source_ts = src.timestamp()
        except Exception:  # never let quality extraction break ingestion
            pass

        # Update our adapter's internal tag cache thread-safely
        self.adapter.update_cached_tag(node_id_str, val, quality=quality, source_ts=source_ts)


class OpcUaAdapter(TagProvider):
    """
    Template client illustrating how to consume data tags from a live OPC UA server.
    Conforms to the read-only TagProvider interface.
    """

    provider_id = "opcua_live"
    display_name = "Live OPC UA Client Adapter"
    provider_type = "opcua"
    status = "disconnected"

    def __init__(self, endpoint_url: str = "opc.tcp://localhost:4840", node_mappings: dict[str, str] | None = None):
        """
        Args:
            endpoint_url: The OPC UA server connection string.
            node_mappings: Map of OPC UA NodeIDs (e.g. 'ns=2;s=Vessel_LT5100') to sensor IDs (e.g. 'LT-5100').
        """
        self.endpoint_url = endpoint_url
        
        # Maps NodeID strings to ConfidenceOS Sensor IDs
        self.node_mappings = node_mappings or {
            "ns=2;s=LT-5100": "LT-5100",
            "ns=2;s=FI-2010": "FI-2010",
            "ns=2;s=FO-2020": "FO-2020",
            "ns=2;s=PT-3100": "PT-3100",
            "ns=2;s=TT-4100": "TT-4100",
            "ns=2;s=ZT-6100": "ZT-6100",
        }
        
        # Thread-safe cache of latest read tag values
        self.tag_cache: dict[str, dict] = {}
        self.cache_lock = threading.Lock()
        
        # Background event loop for asyncua integration
        self._loop = None
        self._thread = None
        self._client = None
        self._subscription = None
        self._running = False
        
        # Base metadata defaults
        self._tick_count = 0
        self._start_time = time.time()

    def update_cached_tag(self, node_id_str: str, value: Any, quality: str = "good", source_ts: float | None = None) -> None:
        """
        Helper to thread-safely cache raw values in ConfidenceOS structure.

        Args:
            quality:   OPC UA-derived data quality ("good"/"uncertain"/"bad"). A real
                       trust layer must not treat bad/uncertain quality as a clean reading.
            source_ts: SourceTimestamp from the server. We prefer it over the local clock
                       so stale data is visible as stale (timestamp_source records which).
        """
        sensor_id = self.node_mappings.get(node_id_str)
        if not sensor_id:
            return  # ignore unmapped node variables

        # NOTE: sensor_type/unit are inferred from id prefix only as a demo convenience.
        # TODO production: derive type + engineering unit from the OPC UA node's DataType /
        # EUInformation, not from a tag-name prefix convention.
        sensor_type = "level"
        if sensor_id.startswith("LT"): sensor_type = "level"
        elif sensor_id.startswith("FI"): sensor_type = "flow_in"
        elif sensor_id.startswith("FO"): sensor_type = "flow_out"
        elif sensor_id.startswith("PT"): sensor_type = "pressure"
        elif sensor_id.startswith("TT"): sensor_type = "temperature"
        elif sensor_id.startswith("ZT"): sensor_type = "valve"

        unit = "m"
        if sensor_type == "level": unit = "m"
        elif sensor_type.startswith("flow"): unit = "m3/h"
        elif sensor_type == "pressure": unit = "kPa"
        elif sensor_type == "temperature": unit = "C"
        elif sensor_type == "valve": unit = "%"

        with self.cache_lock:
            self.tag_cache[sensor_id] = {
                "sensor_id": sensor_id,
                "sensor_type": sensor_type,
                "value": float(value) if value is not None else 0.0,
                "unit": unit,
                "timestamp": source_ts if source_ts is not None else time.time(),
                "timestamp_source": "opcua_source" if source_ts is not None else "local_clock",
                "quality": quality,
                "failure_mode": None,
            }

    # ── TagProvider overrides ──────────────────────────────────────────────────

    def read_tags(self) -> list[dict]:
        """
        Polls the thread-safe tag cache. Under 1Hz scheduler, returns latest updates.
        """
        self._tick_count += 1
        with self.cache_lock:
            # Return copies of the cached records
            return [dict(item) for item in self.tag_cache.values()]

    def reset(self) -> None:
        self._tick_count = 0
        self._start_time = time.time()

    def elapsed(self) -> float:
        return time.time() - self._start_time

    @property
    def tick_count(self) -> int:
        return self._tick_count

    # ── Lifecycle / Connection Management ──────────────────────────────────────

    def start(self) -> None:
        """Starts the background client connection and subscription thread."""
        if self._thread and self._thread.is_alive():
            return
        
        if Client is None:
            logger.warning("asyncua is not installed. OPC UA live adapter will run in mock shadow-mode.")
            self._start_mock_cache()
            self.status = "shadow_mock"
            return

        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()
        self.status = "connecting"

    def stop(self) -> None:
        """Gracefully disconnects and stops the client worker thread."""
        self._running = False
        if self._loop:
            # Schedule task to close client
            asyncio.run_coroutine_threadsafe(self._async_disconnect(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        if self._thread:
            self._thread.join(timeout=3)
        self.status = "disconnected"

    def _run_async_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_connect_and_subscribe())
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _async_connect_and_subscribe(self) -> None:
        try:
            logger.info(f"Connecting to OPC UA Server at {self.endpoint_url}")
            self._client = Client(url=self.endpoint_url)
            await self._client.connect()
            
            # Create subscription (1000ms publish interval)
            handler = SubscriptionHandler(self)
            self._subscription = await self._client.create_subscription(1000, handler)
            
            # Subscribe to all configured NodeIDs
            for node_id_str in self.node_mappings:
                node = self._client.get_node(node_id_str)
                await self._subscription.subscribe_data_change(node)
                
                # Fetch initial value synchronously
                initial_val = await node.read_value()
                self.update_cached_tag(node_id_str, initial_val)
                
            self.status = "connected"
            logger.info("OPC UA Live Connection established and tags subscribed successfully.")
        except Exception as e:
            logger.error(f"OPC UA Connection error: {e}")
            self.status = "error"
            # In production, scheduling a reconnect timer is recommended

    async def _async_disconnect(self) -> None:
        try:
            if self._subscription:
                await self._subscription.delete()
            if self._client:
                await self._client.disconnect()
            logger.info("OPC UA Client disconnected cleanly.")
        except Exception as e:
            logger.error(f"OPC UA Clean shutdown error: {e}")

    def _start_mock_cache(self) -> None:
        """Feeds static mock values into the cache if asyncua is not present."""
        self.update_cached_tag("ns=2;s=LT-5100", 92.5)
        self.update_cached_tag("ns=2;s=FI-2010", 120.4)
        self.update_cached_tag("ns=2;s=FO-2020", 120.1)
        self.update_cached_tag("ns=2;s=PT-3100", 52.3)
        self.update_cached_tag("ns=2;s=TT-4100", 342.1)
        self.update_cached_tag("ns=2;s=ZT-6100", 48.0)
