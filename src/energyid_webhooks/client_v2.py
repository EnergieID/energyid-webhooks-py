"""EnergyID Webhook V2 Client.

This module provides a client for interacting with EnergyID Webhook V2 API,
which allows sending measurement data from sensors to EnergyID.
"""

import asyncio
import datetime as dt
import logging
from typing import Any, Optional, TypeVar, Union, cast

from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")

ValueType = Union[float, int, str]


class Sensor:
    """Represents a sensor that can send measurements to EnergyID."""

    def __init__(
        self, sensor_id: str, webhook_client: Optional["WebhookClient"] = None
    ) -> None:
        """Initialize a sensor.

        Args:
            sensor_id: Unique identifier for the sensor
            webhook_client: Optional webhook client this sensor belongs to
        """
        self.sensor_id = sensor_id
        self.webhook_client = webhook_client

        # State
        self.value: ValueType | None = None
        self.timestamp: dt.datetime | None = None
        self.last_update_time: dt.datetime | None = None
        self.value_uploaded = False

    def update(self, value: ValueType, timestamp: dt.datetime | None = None) -> None:
        """Update the sensor value.

        Args:
            value: The new sensor value
            timestamp: Optional timestamp for the measurement, defaults to current time
        """
        self.value = value
        self.timestamp = timestamp or dt.datetime.now(dt.timezone.utc)
        self.last_update_time = dt.datetime.now(dt.timezone.utc)
        self.value_uploaded = False

        # Notify client if available
        if self.webhook_client:
            self.webhook_client.notify_sensor_update(self)


class WebhookClient:
    """Client for interacting with EnergyID Webhook V2 API."""

    HELLO_URL = "https://hooks.energyid.eu/hello"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        device_id: str,
        device_name: str,
        firmware_version: str | None = None,
        ip_address: str | None = None,
        mac_address: str | None = None,
        local_device_url: str | None = None,
        session: ClientSession | None = None,
        auto_sync_interval: int | None = None,
        reauth_interval: int = 24,  # Default to 24 hours as recommended
    ) -> None:
        """Initialize the webhook client.

        Args:
            client_id: The provisioning key from EnergyID
            client_secret: The provisioning secret from EnergyID
            device_id: Unique identifier for the device
            device_name: Human-readable name for the device
            firmware_version: Optional firmware version
            ip_address: Optional IP address
            mac_address: Optional MAC address
            local_device_url: Optional URL for local device configuration
            session: Optional aiohttp client session
            auto_sync_interval: If set, automatically sync data at this interval (seconds)
            reauth_interval: Hours between token refresh (default 24)
        """
        # Device information
        self.client_id = client_id
        self.client_secret = client_secret
        self.device_id = device_id
        self.device_name = device_name
        self.firmware_version = firmware_version
        self.ip_address = ip_address
        self.mac_address = mac_address
        self.local_device_url = local_device_url

        # Create or store session
        self._own_session = session is None
        self.session = session or ClientSession()

        # Authentication state
        self.is_claimed: bool | None = None
        self.webhook_url: str | None = None
        self.headers: dict[str, str] | None = None
        self.webhook_policy: dict[str, Any] | None = None
        self.auth_valid_until: dt.datetime | None = None
        self.claim_code: str | None = None
        self.claim_url: str | None = None
        self.claim_code_valid_until: dt.datetime | None = None
        self.reauth_interval: int = reauth_interval

        # Sensors
        self.sensors: dict[str, Sensor] = {}
        self.updated_sensors: set[str] = set()
        self.last_sync_time: dt.datetime | None = None

        # Lock for data upload
        self._upload_lock = asyncio.Lock()

        # Auto-sync
        self._auto_sync_task: asyncio.Task[None] | None = None
        if auto_sync_interval:
            self.start_auto_sync(auto_sync_interval)

    async def __aenter__(self) -> "WebhookClient":
        """Enter context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        await self.close()

    def add_sensor(self, sensor_id: str) -> Sensor:
        """Add a sensor to the client.

        Args:
            sensor_id: Unique identifier for the sensor

        Returns:
            The new or existing sensor
        """
        if sensor_id in self.sensors:
            return self.sensors[sensor_id]

        sensor = Sensor(sensor_id, self)
        self.sensors[sensor_id] = sensor
        return sensor

    def update_sensor(
        self, sensor_id: str, value: ValueType, timestamp: dt.datetime | None = None
    ) -> None:
        """Update a sensor's value.

        Args:
            sensor_id: Unique identifier for the sensor
            value: The new sensor value
            timestamp: Optional timestamp for the measurement
        """
        sensor = self.get_or_create_sensor(sensor_id)
        sensor.update(value, timestamp)

    def get_or_create_sensor(self, sensor_id: str) -> Sensor:
        """Get an existing sensor or create a new one.

        Args:
            sensor_id: Unique identifier for the sensor

        Returns:
            The existing or new sensor
        """
        if sensor_id not in self.sensors:
            self.add_sensor(sensor_id)
        return self.sensors[sensor_id]

    def notify_sensor_update(self, sensor: Sensor) -> None:
        """Called when a sensor is updated.

        Args:
            sensor: The updated sensor
        """
        self.updated_sensors.add(sensor.sensor_id)

    async def close(self) -> None:
        """Close the client and clean up resources."""
        if self._auto_sync_task is not None:
            self._auto_sync_task.cancel()
            try:
                await self._auto_sync_task
            except asyncio.CancelledError:
                pass
            self._auto_sync_task = None

        if self._own_session and self.session is not None:
            await self.session.close()
            # We need to set self.session to None, but mypy complains due to the type.
            # We'll use a cast to avoid the error:
            self.session = cast(ClientSession, None)

    async def authenticate(self) -> bool:
        """Authenticate with the EnergyID webhook service.

        Returns:
            True if device is claimed, False otherwise
        """
        # Prepare the device provisioning payload
        payload: dict[str, Any] = {
            "deviceId": self.device_id,
            "deviceName": self.device_name,
        }

        # Add optional fields if present
        if self.firmware_version:
            payload["firmwareVersion"] = self.firmware_version
        if self.ip_address:
            payload["ipAddress"] = self.ip_address
        if self.mac_address:
            payload["macAddress"] = self.mac_address
        if self.local_device_url:
            payload["localDeviceUrl"] = self.local_device_url

        # Set up authentication headers
        headers = {
            "X-Provisioning-Key": self.client_id,
            "X-Provisioning-Secret": self.client_secret,
        }

        # Make the request
        async with self.session.post(
            self.HELLO_URL, json=payload, headers=headers
        ) as response:
            response.raise_for_status()
            data = await response.json()

            # Check if the device is already claimed
            if "webhookUrl" in data:
                # Device is claimed and ready to receive data
                self.is_claimed = True
                self.webhook_url = data["webhookUrl"]
                self.headers = data["headers"]
                self.webhook_policy = data["webhookPolicy"]

                # Set auth valid until (token is valid for 48h, but we'll refresh after 24h)
                self.auth_valid_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                    hours=24
                )

                # Parse allowed interval
                webhook_policy = self.webhook_policy or {}
                if "allowedInterval" in webhook_policy:
                    _LOGGER.info(
                        "Webhook allows interval: %s",
                        webhook_policy.get("allowedInterval"),
                    )
                if "allowedMetrics" in webhook_policy:
                    _LOGGER.info(
                        "Webhook allows metrics: %s",
                        webhook_policy.get("allowedMetrics"),
                    )

                return True
            else:
                # Device needs to be claimed
                self.is_claimed = False
                self.claim_code = data["claimCode"]
                self.claim_url = data["claimUrl"]
                self.claim_code_valid_until = dt.datetime.fromtimestamp(
                    int(data["exp"]), tz=dt.timezone.utc
                )

                return False

    def get_claim_info(self) -> dict[str, Any]:
        """Get information needed to claim the device.

        Returns:
            Dictionary with claim information
        """
        if self.is_claimed:
            return {"status": "already_claimed"}

        if not self.claim_code or not self.claim_url:
            return {
                "status": "not_authenticated",
                "message": "Call authenticate() first",
            }

        valid_until = ""
        if self.claim_code_valid_until is not None:
            valid_until = self.claim_code_valid_until.isoformat()

        return {
            "status": "needs_claiming",
            "claim_code": self.claim_code,
            "claim_url": self.claim_url,
            "valid_until": valid_until,
        }

    async def _ensure_authenticated(self) -> bool:
        """Ensure the client has valid authentication.

        Returns:
            True if the device is claimed, False otherwise
        """
        # Check if we have authentication info
        if self.is_claimed is None:
            await self.authenticate()
            return bool(self.is_claimed)

        # If device is not claimed, nothing more to do
        if not self.is_claimed:
            return False

        # Check if token needs refreshing
        now = dt.datetime.now(dt.timezone.utc)
        should_reauth = False

        if self.auth_valid_until is None:
            # No valid_until time, consider it expired
            should_reauth = True
        else:
            # Calculate how many hours remain before token expires
            hours_until_expiration = (
                self.auth_valid_until - now
            ).total_seconds() / 3600

            # Set a reasonable threshold - reauth when less than 6 hours remain
            # This gives plenty of buffer while avoiding too frequent refreshes
            reauth_threshold = 6  # hours
            should_reauth = hours_until_expiration <= reauth_threshold

            if should_reauth:
                _LOGGER.info(
                    "Token will expire in %.1f hours, refreshing now (threshold: %d hours)",
                    hours_until_expiration,
                    reauth_threshold,
                )

        if should_reauth:
            await self.authenticate()

        return bool(self.is_claimed)

    async def send_data(self, data_points: dict[str, Any]) -> str | None:
        """Send data points to EnergyID.

        Args:
            data_points: Dictionary of metric keys and values
                         with an optional 'ts' key for timestamp

        Returns:
            Response from the server
        """
        # Ensure we're authenticated and claimed
        if not await self._ensure_authenticated():
            raise ValueError(
                "Device not claimed. Call authenticate() and complete claiming process"
            )

        # Create a copy of the data points to avoid modifying the original
        payload = dict(data_points)

        # Add timestamp if not provided (current time in seconds)
        if "ts" not in payload:
            payload["ts"] = int(dt.datetime.now(dt.timezone.utc).timestamp())

        # Debug output
        _LOGGER.debug("Sending data to %s", self.webhook_url)
        _LOGGER.debug("Headers: %s", self.headers)
        _LOGGER.debug("Payload: %s", payload)

        # Make sure we have a webhook URL
        if self.webhook_url is None:
            raise ValueError("No webhook URL available")

        # Send data to webhook
        try:
            if self.headers is None:
                # This shouldn't happen after _ensure_authenticated()
                raise ValueError("No authentication headers available")

            async with self.session.post(
                self.webhook_url, json=payload, headers=self.headers
            ) as response:
                # Handle expired token case
                if response.status == 401:
                    _LOGGER.info("Token expired (401), re-authenticating...")

                    # Re-authenticate
                    await self.authenticate()

                    if self.webhook_url is None or self.headers is None:
                        raise ValueError("Failed to refresh authentication")

                    # Retry the request
                    async with self.session.post(
                        self.webhook_url, json=payload, headers=self.headers
                    ) as retry_response:
                        retry_response.raise_for_status()
                        resp_text = await retry_response.text()
                        _LOGGER.debug("Response status: %s", retry_response.status)
                        return resp_text
                else:
                    response.raise_for_status()
                    resp_text = await response.text()
                    _LOGGER.debug("Response status: %s", response.status)
                    return resp_text
        except Exception as e:
            _LOGGER.error("Error sending data: %s", e)
            raise

    async def send_batch_data(
        self,
        metrics_data: dict[str, ValueType | dt.datetime],
        timestamp: dt.datetime | int | None = None,
    ) -> str | None:
        """Send multiple metrics in a single request.

        Args:
            metrics_data: Dictionary of metric keys and values
            timestamp: Optional timestamp (defaults to current time)

        Returns:
            Response from the server
        """
        # Create payload
        payload: dict[str, Any] = dict(metrics_data)  # Make a copy

        # Add timestamp if provided or use current time
        if timestamp:
            if isinstance(timestamp, dt.datetime):
                payload["ts"] = int(timestamp.timestamp())
            else:
                # Already an int timestamp
                payload["ts"] = timestamp
        else:
            payload["ts"] = int(dt.datetime.now(dt.timezone.utc).timestamp())

        return await self.send_data(payload)

    async def synchronize_sensors(self) -> str | None:
        """Synchronize all updated sensors to EnergyID.

        Returns:
            Server response if data was sent, None otherwise
        """
        if not self.updated_sensors:
            _LOGGER.debug("No sensors to synchronize")
            return None

        # Get the current time before starting sync
        sync_time = dt.datetime.now(dt.timezone.utc)

        # Lock to prevent concurrent uploads
        async with self._upload_lock:
            # Group sensors by timestamp rounded to the nearest second
            sensors_by_time: dict[int, list[Sensor]] = {}

            for sensor_id in list(self.updated_sensors):
                sensor = self.sensors[sensor_id]

                # Get timestamp or use current time
                ts = sensor.timestamp or sync_time
                ts_second = int(ts.timestamp())

                if ts_second not in sensors_by_time:
                    sensors_by_time[ts_second] = []

                sensors_by_time[ts_second].append(sensor)

            # Create data points for each time group and send them
            responses: list[str] = []
            for ts_second, sensors in sensors_by_time.items():
                data_points: dict[str, Any] = {"ts": ts_second}

                for sensor in sensors:
                    if sensor.value is not None:
                        data_points[sensor.sensor_id] = sensor.value

                if (
                    len(data_points) > 1
                ):  # Only send if we have data beyond the timestamp
                    response = await self.send_data(data_points)
                    if response is not None:
                        responses.append(response)

                    # Mark sensors as uploaded
                    for sensor in sensors:
                        sensor.value_uploaded = True
                        self.updated_sensors.discard(sensor.sensor_id)

            # Update sync time
            self.last_sync_time = sync_time

            if responses:
                return responses[-1]  # Return the last response

            return None

    async def _auto_sync_loop(self) -> None:
        """Background task to automatically synchronize sensors."""
        while True:
            try:
                await self.synchronize_sensors()
            except Exception as e:
                _LOGGER.error("Error in auto-sync: %s", e)

            await asyncio.sleep(self._auto_sync_interval)

    def start_auto_sync(self, interval_seconds: int) -> None:
        """Start automatic synchronization at the specified interval.

        Args:
            interval_seconds: Sync interval in seconds
        """
        self._auto_sync_interval = interval_seconds

        if self._auto_sync_task is not None:
            self._auto_sync_task.cancel()

        self._auto_sync_task = asyncio.create_task(self._auto_sync_loop())
