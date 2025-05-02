"""EnergyID Webhook V2 Client.

This module provides a client for interacting with EnergyID Webhook V2 API,
which allows sending measurement data from sensors to EnergyID.
"""

import asyncio
import datetime as dt
from itertools import groupby
import logging
from typing import Any, TypeVar, Union, cast

from aiohttp import ClientSession, ClientError
import backoff
import aiohttp

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")

ValueType = Union[float, int, str]


class Sensor:
    """Represents a sensor that collects and sends measurement data."""

    def __init__(self, sensor_id: str) -> None:
        """
        Initialize a sensor with a unique ID.

        Args:
            sensor_id (str): The unique identifier for the sensor.
        """
        self.sensor_id = sensor_id
        self.value: ValueType | None = None
        self.timestamp: dt.datetime | None = None
        self.last_update_time: dt.datetime | None = None
        self.value_uploaded = True

    def __repr__(self) -> str:
        """
        Return a string representation of the Sensor object.

        Returns:
            str: A string describing the sensor's attributes.
        """
        return f"Sensor(sensor_id={self.sensor_id}, value={self.value}, timestamp={self.timestamp}, last_update_time={self.last_update_time}, value_uploaded={self.value_uploaded})"

    def update(self, value: ValueType, timestamp: dt.datetime | None = None) -> None:
        """
        Update the sensor's value and timestamp.

        Args:
            value (ValueType): The new value for the sensor.
            timestamp (datetime, optional): The timestamp of the update. Defaults to the current UTC time.
        """
        self.value = value
        self.timestamp = timestamp or dt.datetime.now(dt.timezone.utc)
        self.last_update_time = dt.datetime.now(dt.timezone.utc)
        self.value_uploaded = False


class WebhookClient:
    """Client for interacting with the EnergyID Webhook V2 API."""

    HELLO_URL = "https://hooks.energyid.eu/hello"

    def __init__(
        self,
        provisioning_key: str,
        provisioning_secret: str,
        device_id: str,
        device_name: str,
        firmware_version: str | None = None,
        ip_address: str | None = None,
        mac_address: str | None = None,
        local_device_url: str | None = None,
        session: ClientSession | None = None,
        reauth_interval: int = 24,
    ) -> None:
        """
        Initialize the WebhookClient with device and session details.

        Args:
            provisioning_key (str): The provisioning key for the device.
            provisioning_secret (str): The provisioning secret for the device.
            device_id (str): The unique identifier for the device.
            device_name (str): The name of the device.
            firmware_version (str, optional): The firmware version of the device. Defaults to None.
            ip_address (str, optional): The IP address of the device. Defaults to None.
            mac_address (str, optional): The MAC address of the device. Defaults to None.
            local_device_url (str, optional): The local URL of the device. Defaults to None.
            session (ClientSession, optional): An existing aiohttp session. Defaults to None.
            reauth_interval (int, optional): The interval in hours for re-authentication. Defaults to 24.
        """
        self.provisioning_key = provisioning_key
        self.provisioning_secret = provisioning_secret
        self.device_id = device_id
        self.device_name = device_name
        self.firmware_version = firmware_version
        self.ip_address = ip_address
        self.mac_address = mac_address
        self.local_device_url = local_device_url

        self._own_session = session is None
        self.session = session or ClientSession()

        self.is_claimed: bool | None = None
        self.webhook_url: str | None = None
        self.headers: dict[str, str] | None = None
        self.webhook_policy: dict[str, Any] | None = None
        self.uploadInterval: int = 60
        self.auth_valid_until: dt.datetime | None = None
        self.claim_code: str | None = None
        self.claim_url: str | None = None
        self.claim_code_valid_until: dt.datetime | None = None
        self.reauth_interval: int = reauth_interval

        self.sensors: list[Sensor] = []
        self.last_sync_time: dt.datetime | None = None

        self._upload_lock = asyncio.Lock()
        self._auto_sync_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "WebhookClient":
        """
        Enter the asynchronous context manager.

        Returns:
            WebhookClient: The current instance of the WebhookClient.
        """
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Exit the asynchronous context manager and close the client.

        Args:
            exc_type (Any): The exception type, if any.
            exc_val (Any): The exception value, if any.
            exc_tb (Any): The traceback, if any.
        """
        await self.close()

    @property
    def updated_sensors(self) -> list[Sensor]:
        """
        Get a list of sensors with unsynchronized data.

        Returns:
            list[Sensor]: A list of sensors that have not uploaded their values.
        """
        return [sensor for sensor in self.sensors if not sensor.value_uploaded]

    def get_sensor(self, sensor_id: str) -> Sensor | None:
        """
        Retrieve a sensor by its ID.

        Args:
            sensor_id (str): The unique identifier of the sensor.

        Returns:
            Sensor | None: The sensor object if found, otherwise None.
        """
        for sensor in self.sensors:
            if sensor.sensor_id == sensor_id:
                return sensor
        return None

    def create_sensor(self, sensor_id: str) -> Sensor:
        """
        Create a new sensor and add it to the client.

        Args:
            sensor_id (str): The unique identifier for the new sensor.

        Returns:
            Sensor: The newly created sensor object.
        """
        sensor = Sensor(sensor_id)
        self.sensors.append(sensor)
        return sensor

    async def update_sensor(
        self, sensor_id: str, value: ValueType, timestamp: dt.datetime | None = None
    ) -> None:
        """
        Update a sensor's value and timestamp.

        Args:
            sensor_id (str): The unique identifier of the sensor.
            value (ValueType): The new value for the sensor.
            timestamp (datetime, optional): The timestamp of the update. Defaults to the current UTC time.
        """
        sensor = self.get_or_create_sensor(sensor_id)
        async with self._upload_lock:
            sensor.update(value, timestamp)

    def get_or_create_sensor(self, sensor_id: str) -> Sensor:
        """
        Retrieve a sensor by its ID or create it if it does not exist.

        Args:
            sensor_id (str): The unique identifier of the sensor.

        Returns:
            Sensor: The retrieved or newly created sensor object.
        """
        sensor = self.get_sensor(sensor_id)
        if sensor is None:
            sensor = self.create_sensor(sensor_id)
        return sensor

    async def close(self) -> None:
        """
        Close the WebhookClient and release resources.
        """
        if self._auto_sync_task is not None:
            self._auto_sync_task.cancel()
            try:
                await self._auto_sync_task
            except asyncio.CancelledError:
                pass
            self._auto_sync_task = None

        if self._own_session:
            await self.session.close()
            self.session = cast(ClientSession, None)

    async def authenticate(self) -> bool:
        """
        Authenticate the client and retrieve webhook details.

        Returns:
            bool: True if the client is successfully authenticated, otherwise False.
        """
        payload: dict[str, Any] = {
            "deviceId": self.device_id,
            "deviceName": self.device_name,
        }

        if self.firmware_version:
            payload["firmwareVersion"] = self.firmware_version
        if self.ip_address:
            payload["ipAddress"] = self.ip_address
        if self.mac_address:
            payload["macAddress"] = self.mac_address
        if self.local_device_url:
            payload["localDeviceUrl"] = self.local_device_url

        headers = {
            "X-Provisioning-Key": self.provisioning_key,
            "X-Provisioning-Secret": self.provisioning_secret,
        }

        async with self.session.post(
            self.HELLO_URL, json=payload, headers=headers
        ) as response:
            response.raise_for_status()
            data = await response.json()

            if "webhookUrl" in data:
                self.is_claimed = True
                self.webhook_url = data["webhookUrl"]
                self.headers = data["headers"]
                self.webhook_policy = data.get("webhookPolicy", {})
                for key, value in self.webhook_policy.items():
                    setattr(self, key, value)
                self.auth_valid_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                    hours=self.reauth_interval
                )
                _LOGGER.info("Webhook policy attributes set: %s", self.webhook_policy)
                return True
            else:
                self.is_claimed = False
                self.claim_code = data["claimCode"]
                self.claim_url = data["claimUrl"]
                self.claim_code_valid_until = dt.datetime.fromtimestamp(
                    int(data["exp"]), tz=dt.timezone.utc
                )
                return False

    def get_claim_info(self) -> dict[str, Any]:
        """
        Retrieve claim information if the device is not yet claimed.

        Returns:
            dict[str, Any]: A dictionary containing claim information or status.
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
        """
        Ensure the client is authenticated and refresh tokens if needed.

        Returns:
            bool: True if the client is authenticated, otherwise False.
        """
        if self.session.headers is None:
            await self.authenticate()
            return bool(self.is_claimed)

        if self.is_claimed is None:
            await self.authenticate()
            return bool(self.is_claimed)

        if not self.is_claimed:
            return False

        now = dt.datetime.now(dt.timezone.utc)
        should_reauth = False

        if self.auth_valid_until is None:
            should_reauth = True
        else:
            hours_until_expiration = (
                self.auth_valid_until - now
            ).total_seconds() / 3600
            reauth_threshold = 6
            should_reauth = hours_until_expiration <= reauth_threshold

            if should_reauth:
                _LOGGER.info(
                    "Token will expire in %.1f hours, refreshing webhook URL, headers and policy (threshold: %d hours)",
                    hours_until_expiration,
                    reauth_threshold,
                )

        if should_reauth:
            await self.authenticate()

        return bool(self.is_claimed)

    @backoff.on_exception(
        backoff.expo, (ClientError, TimeoutError), max_tries=3, max_time=60
    )
    async def send_data(
        self, data_points: dict[str, Any], timestamp: dt.datetime | int | None = None
    ) -> None:
        """
        Send measurement data to the webhook endpoint.

        Args:
            data_points (dict[str, Any]): A dictionary of sensor data points.
            timestamp (datetime | int | None, optional): The timestamp for the data. Defaults to None.

        Raises:
            ValueError: If the device is not claimed or authentication fails.
            ConnectionError: If authentication cannot be ensured.
        """
        if not await self._ensure_authenticated():
            if not self.is_claimed:
                raise ValueError("Device not claimed. Cannot send data.")
            raise ConnectionError(
                "Failed to ensure authentication before sending data."
            )

        payload = dict(data_points)
        if timestamp:
            payload["ts"] = (
                int(timestamp.timestamp())
                if isinstance(timestamp, dt.datetime)
                else timestamp
            )
        elif "ts" not in payload:
            payload["ts"] = int(dt.datetime.now(dt.timezone.utc).timestamp())

        _LOGGER.debug("Attempting to send data to %s", self.webhook_url)

        if not self.webhook_url or not self.headers:
            _LOGGER.error("Webhook URL or headers missing, cannot send data.")
            raise ValueError(
                "Webhook URL/headers not set, authentication likely failed."
            )

        try:
            async with self.session.post(
                self.webhook_url, json=payload, headers=self.headers
            ) as response:
                response.raise_for_status()
                response_text = await response.text()
                _LOGGER.debug("Send data successful. Response: %s", response_text)
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.warning(
                    "Received 401 Unauthorized sending data. Marking token as potentially expired."
                )
                self.auth_valid_until = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
                    seconds=1
                )
                raise err
            else:
                raise err

    async def synchronize_sensors(self) -> None:
        """
        Synchronize updated sensor data with the webhook endpoint.

        Raises:
            Exception: If data synchronization fails.
        """
        updated = self.updated_sensors
        if not updated:
            return None

        async with self._upload_lock:

            def get_timestamp_key(sensor: Sensor | None) -> int | None:
                if sensor and sensor.timestamp:
                    if isinstance(sensor.timestamp, dt.datetime):
                        return int(sensor.timestamp.timestamp())
                    else:
                        _LOGGER.warning(
                            "Sensor %s has non-datetime timestamp: %s",
                            sensor.sensor_id,
                            sensor.timestamp,
                        )
                        return None
                _LOGGER.warning(
                    "Sensor object or its timestamp is None during sync grouping: %s",
                    sensor,
                )
                return None

            grouped_sensors = groupby(
                sorted(updated, key=get_timestamp_key), key=get_timestamp_key
            )

            for timestamp_key, sensor_iter in grouped_sensors:
                if timestamp_key is None:
                    _LOGGER.warning(
                        "Skipping sensors with invalid timestamp during sync: %s",
                        list(sensor_iter),
                    )
                    continue

                sensors_in_group = list(sensor_iter)
                data_points = {
                    sensor.sensor_id: sensor.value for sensor in sensors_in_group
                }

                try:
                    await self.send_data(data_points, timestamp_key)
                    for sensor in sensors_in_group:
                        sensor.value_uploaded = True
                    self.last_sync_time = dt.datetime.now(dt.timezone.utc)
                except Exception as e:
                    _LOGGER.error(
                        "Failed to send data batch for timestamp %s: %s",
                        timestamp_key,
                        e,
                    )
                    raise

    async def _auto_sync_loop(self, interval: int) -> None:
        """
        Continuously synchronize sensors at a specified interval.

        Args:
            interval (int): The interval in seconds between synchronizations.
        """
        while True:
            try:
                await self.synchronize_sensors()
            except Exception as e:
                _LOGGER.error("Error in auto-sync: %s", e)

            await asyncio.sleep(interval)

    def start_auto_sync(self, interval_seconds: int) -> None:
        """
        Start the automatic synchronization loop.

        Args:
            interval_seconds (int): The interval in seconds for automatic synchronization.
        """
        if self._auto_sync_task is not None:
            self._auto_sync_task.cancel()

        self._auto_sync_task = asyncio.create_task(
            self._auto_sync_loop(interval=interval_seconds)
        )
