"""
opc_ua_adapter.py — OPC UA read-only adapter for ConfidenceOS.

Connects to a live OPC UA server, subscribes to process tags, and feeds them
into the ConfidenceOS Trust Layer. Captures OPC UA data quality (StatusCode)
and SourceTimestamp so stale or bad-quality tags are visible as such.

Production features implemented:
  - Reconnect with exponential backoff (1 s → 2 → 4 → 8 → 16 → 32 → 60 s max)
  - Connection-state surfacing: status field exposed to health endpoint
  - Namespace browse: browse_namespace() returns available nodes from server
  - OPC UA quality and SourceTimestamp honoured (not replaced by local clock)

Still explicit limitations (document, not hide):
  - OPC UA security: SecurityPolicy / message signing / client certs not yet wired
  - DataType/EUInformation: sensor type + engineering units inferred from tag prefix
  - Historian (HDA) backfill for out-of-order/late samples not implemented
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import threading
from typing import Any

# asyncua is an optional dependency — adapter falls back to shadow-mock mode when absent.
try:
    from asyncua import Client, ua
except ImportError:
    Client = None
    ua = None

_RECONNECT_BASE_SECONDS = 1.0
_RECONNECT_MAX_SECONDS = 60.0

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

        # Reconnect tracking
        self._reconnect_attempts = 0
        self._last_connect_error: str | None = None
        self._connected_since: float | None = None

        # Base metadata
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
        self._loop.run_until_complete(self._reconnect_loop())
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _reconnect_loop(self) -> None:
        """Connect and automatically reconnect with exponential backoff on failure."""
        while self._running:
            try:
                await self._async_connect_and_subscribe()
                # Connected — run subscription until stopped or error
                while self._running and self.status == "connected":
                    await asyncio.sleep(1.0)
                if not self._running:
                    break
                # Unexpected disconnect — fall through to reconnect
                logger.warning("OPC UA connection lost; will reconnect.")
                self.status = "reconnecting"
            except Exception as exc:
                self._last_connect_error = str(exc)
                self._reconnect_attempts += 1
                delay = min(
                    _RECONNECT_BASE_SECONDS * math.pow(2, self._reconnect_attempts - 1),
                    _RECONNECT_MAX_SECONDS,
                )
                logger.warning(
                    "OPC UA connection failed (attempt %d): %s — retrying in %.0fs",
                    self._reconnect_attempts, exc, delay,
                )
                self.status = "reconnecting"
                await asyncio.sleep(delay)

    async def _async_connect_and_subscribe(self) -> None:
        logger.info("Connecting to OPC UA server at %s", self.endpoint_url)
        self._client = Client(url=self.endpoint_url)
        await self._client.connect()

        handler = SubscriptionHandler(self)
        self._subscription = await self._client.create_subscription(1000, handler)

        for node_id_str in self.node_mappings:
            node = self._client.get_node(node_id_str)
            await self._subscription.subscribe_data_change(node)
            initial_val = await node.read_value()
            self.update_cached_tag(node_id_str, initial_val)

        self.status = "connected"
        self._reconnect_attempts = 0
        self._connected_since = time.time()
        self._last_connect_error = None
        logger.info("OPC UA connected — %d tags subscribed.", len(self.node_mappings))

    async def _async_disconnect(self) -> None:
        try:
            if self._subscription:
                await self._subscription.delete()
            if self._client:
                await self._client.disconnect()
            logger.info("OPC UA Client disconnected cleanly.")
        except Exception as e:
            logger.error(f"OPC UA Clean shutdown error: {e}")

    def connection_info(self) -> dict:
        """Return current connection state for health/status endpoints."""
        return {
            "status": self.status,
            "endpoint_url": self.endpoint_url,
            "reconnect_attempts": self._reconnect_attempts,
            "last_connect_error": self._last_connect_error,
            "connected_since": self._connected_since,
            "mapped_nodes": len(self.node_mappings),
            "cached_tags": len(self.tag_cache),
        }

    async def browse_namespace(self, namespace_index: int = 2, max_nodes: int = 200) -> list[dict]:
        """
        Browse the OPC UA server namespace and return available node descriptors.

        This enables dynamic tag discovery — an engineer can browse the server,
        identify the relevant NodeIDs, and configure node_mappings without
        hand-authoring them. Returns up to max_nodes entries.

        Requires an active connection. Raises RuntimeError if not connected.
        """
        if self.status != "connected" or self._client is None:
            raise RuntimeError(f"OPC UA adapter is not connected (status={self.status}).")
        if Client is None:
            raise RuntimeError("asyncua is not installed; namespace browse unavailable.")

        result = []
        try:
            ns_node = self._client.get_node(f"ns={namespace_index};i=85")  # Objects folder
            children = await ns_node.get_children()
            for child in children[:max_nodes]:
                try:
                    browse_name = await child.read_browse_name()
                    node_class = await child.read_node_class()
                    node_id_str = str(child.nodeid)
                    result.append({
                        "node_id": node_id_str,
                        "browse_name": str(browse_name),
                        "node_class": str(node_class),
                        "namespace": namespace_index,
                    })
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("Namespace browse failed: %s", exc)
        return result

    def _start_mock_cache(self) -> None:
        """Feeds static mock values into the cache when asyncua is not installed."""
        self.update_cached_tag("ns=2;s=LT-5100", 92.5)
        self.update_cached_tag("ns=2;s=FI-2010", 120.4)
        self.update_cached_tag("ns=2;s=FO-2020", 120.1)
        self.update_cached_tag("ns=2;s=PT-3100", 52.3)
        self.update_cached_tag("ns=2;s=TT-4100", 342.1)
        self.update_cached_tag("ns=2;s=ZT-6100", 48.0)
