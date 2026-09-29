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

- Every unclaimed device gets one `/hello` per `EID_HELLO_COOLDOWN_S` (default 300 s), oldest first. EnergyID keeps the device's registration for 60 minutes and renews it on the next `/hello` after it expires, so a device stays claimable as long as the bridge runs. After the device is claimed in EnergyID, its next `/hello` returns webhook credentials and uploads start.
- A `409 claim_code_in_use` from `/hello` means another device id already holds that claim code under your provisioning key. The bridge logs the holder and retries after 30 minutes; give each physical device one device id.
- A batch that gets no response within `EID_INFLIGHT_TIMEOUT_S` (default 120 s) is put back in the buffer and retried. `401`/`403`/`404` on upload trigger a fresh `/hello` for that device.
- Click **Show registry summary** for diagnostics: `payload.problems` lists devices without recent MQTT data, `/hello` errors, failing or stuck uploads, and unclaimed devices without a recent `/hello`. An empty list means healthy.

The MQTT bridge demo intentionally contains no provisioning secrets, MQTT credentials, record numbers, claim URLs, or customer-specific device IDs. Do not commit or share an exported flow after filling in flow-level secrets, and do not share runtime context/debug output if it contains claimed records or personal device metadata.

## Python

- `energyid_webhook_quick_demo.ipynb`: compact Python notebook.
- `energyid_webhook_demo.ipynb`: fuller Python notebook.

## Other Examples

- `curl_examples.sh`: raw HTTP examples.
- `nifi_template.xml`: Apache NiFi template.