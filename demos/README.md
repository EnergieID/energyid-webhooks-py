# EnergyID Webhook Demos

This folder contains examples for integrating devices and data pipelines with EnergyID incoming webhooks.

## Node-RED

- `nodered_flow.json`: generic webhook demo with `/hello`, claim retry, single reading upload, batch upload, and a second device example.
- `nodered_mqtt_bridge_flow.json`: MQTT bridge demo that discovers devices from MQTT topics, performs `/hello` per device, caches connection info, buffers readings, and uploads per device according to the returned webhook policy.

Import the JSON file into Node-RED as a new flow tab. Set these values before enabling the MQTT bridge flow:

- `ENERGYID_PROVISIONING_KEY`
- `ENERGYID_PROVISIONING_SECRET`
- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`
- MQTT broker username and password in the imported MQTT broker node, optionally using `${MQTT_BROKER_USER}` and `${MQTT_BROKER_PASSWORD}` placeholders backed by global/process environment variables.

How the MQTT bridge behaves once running:

- `/hello` work is served in this order: forced refreshes (after a `401`/`403`/`404`), claimed devices whose credentials are due for a refresh (`EID_CREDENTIAL_REFRESH_S`, or 6 h before the token expires), then unclaimed devices, longest waiting first, `EID_HELLO_PER_TICK` per 5 s tick (default: 2 to 10, enough to clear the due list in about 5 minutes, e.g. after a restart).
- Every unclaimed device gets one `/hello` per `EID_HELLO_COOLDOWN_S` (default 300 s). After `EID_HELLO_IDLE_AFTER` (default 12) calls without a claim it slows down to `EID_HELLO_IDLE_COOLDOWN_S` (default 1800 s). EnergyID keeps a registration for 60 minutes and renews it on the next `/hello` after it expires, so a device stays claimable as long as the bridge runs. After the device is claimed in EnergyID, its next `/hello` returns upload credentials and uploads start.
- A `409 claim_code_in_use` from `/hello` means another device id already holds that claim code under your provisioning key. The bridge logs the holder and retries after 30 minutes; give each physical device one device id.

Uploads and large fleets:

- `/hello` decides where a device uploads: a Service Bus queue (`*.servicebus.windows.net`) or `https://hooks.energyid.eu/webhook-in`. `/webhook-in` is rate-limited per caller IP (30 requests per 15 minutes), and every device behind one bridge shares that budget. For a fleet, ask EnergyID to route the provisioning key to Service Bus; the devices switch by themselves at their next credential refresh, no flow change needed. The registry summary flags a fleet that is still on `/webhook-in`.
- One request carries one device's readings (up to `EID_MAX_BATCH_SIZE` = 1000 points and `EID_MAX_BATCH_BYTES` = 200 kB). Readings closer together than `EID_MIN_POINT_SPACING_S` (default 60 s) are merged first, latest value per key; EnergyID resamples to the record's interval anyway.
- Devices that are due are served longest-waiting first, so a limited budget rotates over the whole fleet. The number of requests per tick and in flight follows the fleet size automatically (`EID_MAX_SENDS_PER_TICK`, `EID_MAX_INFLIGHT`).
- `429`/`503` pause the whole host, honouring `Retry-After` and doubling up to `EID_HOST_PAUSE_MAX_S`. `400`/`413`/`422` halve the batch until the refused point is found; that point is dropped and counted in the device's `droppedPoints`. `401`/`403`/`404` trigger a fresh `/hello` for that device. Other errors back off that device from 1 to 15 minutes. A batch that gets no response within `EID_INFLIGHT_TIMEOUT_S` (default 120 s) is put back in the buffer and retried.
- Click **Show registry summary** for diagnostics: `payload.problems` lists devices without recent MQTT data, `/hello` errors, failing or stuck uploads, dropped points, unclaimed devices without a recent `/hello`, paused hosts and a fleet on `/webhook-in`. An empty list means healthy. `payload.endpoints`, `payload.minutesSinceLastUpload` (p50/p95/max) and `payload.hosts` give the fleet view.
- Upgrading from the earlier version: import over the existing tab (same node ids). The registry and buffers are kept. If you customised the "Route + extract + register + buffer" node, keep yours: this version does not change it. `EID_BATCH_INTERVAL_S` is no longer used; the upload interval comes from each device's EnergyID upload policy.

`demos/nodered_mqtt_bridge_sim/` holds a simulation that runs the flow's function nodes against mock EnergyID endpoints with a fake clock (`node sim.js <flow.json> <webhook-ip|webhook-device|servicebus> [devices] [claimed] [hours] [publishEveryS]`).

The MQTT bridge demo intentionally contains no provisioning secrets, MQTT credentials, record numbers, claim URLs, or customer-specific device IDs. Do not commit or share an exported flow after filling in flow-level secrets, and do not share runtime context/debug output if it contains claimed records or personal device metadata.

## Python

- `energyid_webhook_quick_demo.ipynb`: compact Python notebook.
- `energyid_webhook_demo.ipynb`: fuller Python notebook.

## Other Examples

- `curl_examples.sh`: raw HTTP examples.
- `nifi_template.xml`: Apache NiFi template.