#!/bin/bash
set -e

# EnergyID Webhook API - cURL Examples
# Complete flow: authenticate -> send data -> refresh token
#
# Requirements: curl, jq
# Usage: Set the variables below, then run: bash curl_examples.sh

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROVISIONING_KEY="your-provisioning-key"
PROVISIONING_SECRET="your-provisioning-secret"
DEVICE_ID="my-device-001"
DEVICE_NAME="My Energy Device"

# ---------------------------------------------------------------------------
# Step 1: Authenticate via POST /hello
# ---------------------------------------------------------------------------
# Call /hello to get webhook credentials for a claimed device, or a claim
# code/URL for a device that has not yet been linked to an EnergyID record.
# Re-run this call every 24h to refresh credentials (token expires at 48h).

echo ">>> Step 1: POST /hello"

HELLO_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "https://hooks.energyid.eu/hello" \
  -H "Content-Type: application/json" \
  -H "X-Provisioning-Key: ${PROVISIONING_KEY}" \
  -H "X-Provisioning-Secret: ${PROVISIONING_SECRET}" \
  -d "{\"deviceId\": \"${DEVICE_ID}\", \"deviceName\": \"${DEVICE_NAME}\"}")

HTTP_STATUS=$(echo "${HELLO_RESPONSE}" | tail -n1)
HELLO_BODY=$(echo "${HELLO_RESPONSE}" | sed '$d')

echo "HTTP status: ${HTTP_STATUS}"
echo "Response body:"
echo "${HELLO_BODY}" | jq .

# ---------------------------------------------------------------------------
# Detect claimed vs unclaimed device
# ---------------------------------------------------------------------------
# Claimed:   response contains "webhookUrl" -> credentials ready to use
# Unclaimed: response contains "claimCode"  -> user must visit claimUrl first

if echo "${HELLO_BODY}" | jq -e '.webhookUrl' > /dev/null 2>&1; then
    echo ""
    echo "Device is CLAIMED. Extracting credentials..."

    WEBHOOK_URL=$(echo "${HELLO_BODY}" | jq -r '.webhookUrl')
    AUTH_HEADER=$(echo "${HELLO_BODY}" | jq -r '.headers.authorization')
    TWIN_ID=$(echo "${HELLO_BODY}" | jq -r '.headers["x-twin-id"]')
    RECORD_NAME=$(echo "${HELLO_BODY}" | jq -r '.recordName')
    RECORD_NUMBER=$(echo "${HELLO_BODY}" | jq -r '.recordNumber')

    echo "  webhookUrl:    ${WEBHOOK_URL}"
    echo "  x-twin-id:     ${TWIN_ID}"
    echo "  recordName:    ${RECORD_NAME}"
    echo "  recordNumber:  ${RECORD_NUMBER}"
    echo "  authorization: (omitted for brevity)"

else
    echo ""
    echo "Device is UNCLAIMED."
    echo "  claimCode: $(echo "${HELLO_BODY}" | jq -r '.claimCode')"
    echo "  claimUrl:  $(echo "${HELLO_BODY}" | jq -r '.claimUrl')"
    echo ""
    echo "Visit the claimUrl above to link this device to an EnergyID record,"
    echo "then re-run this script."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 2: Send a single data point
# ---------------------------------------------------------------------------
# POST a single JSON object to the webhook URL.
# The "ts" field (Unix timestamp, seconds) is MANDATORY in every payload.
# Metric keys: el (electricity kWh), el-i (injection kWh), gas (m3),
#   pv (solar kWh), water/dw (drinking water l), pwr (power kW),
#   pwr-i (injection kW), ev (EV charging kWh), bat (battery kWh),
#   bat-soc (battery SOC %), heat (kWh), wind (kWh), chp (cogen kWh),
#   sol (solar heat kWh)

echo ""
echo ">>> Step 2: Send a single data point"

# Use the current Unix timestamp rounded to the nearest minute
TS=$(date +%s)

curl -s -o /dev/null -w "HTTP status: %{http_code}\n" \
  -X POST "${WEBHOOK_URL}" \
  -H "authorization: ${AUTH_HEADER}" \
  -H "x-twin-id: ${TWIN_ID}" \
  -H "Content-Type: application/json" \
  -d "{\"ts\": ${TS}, \"el\": 12345.67, \"gas\": 456.78}"

# ---------------------------------------------------------------------------
# Step 3: Send a batch (array of readings)
# ---------------------------------------------------------------------------
# Batching multiple readings in one request is the preferred approach.
# It reduces the number of API calls and avoids hitting rate limits (429).
# Every object in the array MUST include a "ts" field.
# Use 60-second intervals between readings as a starting point (check
# webhookPolicy.uploadInterval from the /hello response for the exact value).

echo ""
echo ">>> Step 3: Send a batch of readings"

TS0=$((TS - 120))
TS1=$((TS - 60))
TS2=${TS}

curl -s -o /dev/null -w "HTTP status: %{http_code}\n" \
  -X POST "${WEBHOOK_URL}" \
  -H "authorization: ${AUTH_HEADER}" \
  -H "x-twin-id: ${TWIN_ID}" \
  -H "Content-Type: application/json" \
  -d "[
    {\"ts\": ${TS0}, \"el\": 12345.67, \"pv\": 3.10},
    {\"ts\": ${TS1}, \"el\": 12346.12, \"pv\": 3.25},
    {\"ts\": ${TS2}, \"el\": 12346.89, \"pv\": 3.40}
  ]"

# ---------------------------------------------------------------------------
# Step 4: Token refresh (re-call /hello)
# ---------------------------------------------------------------------------
# The authorization token returned by /hello is valid for ~48 hours.
# Refresh it every 24 hours by repeating the exact same /hello call.
# The response structure is identical - just overwrite your stored credentials.
# A 401 response from the data endpoint means the token has expired; call
# /hello immediately to get a new one before retrying the failed request.

echo ""
echo ">>> Step 4: Token refresh - same /hello call as Step 1"
echo "(Run this every 24h, or immediately on a 401 response from the data endpoint)"

REFRESH_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "https://hooks.energyid.eu/hello" \
  -H "Content-Type: application/json" \
  -H "X-Provisioning-Key: ${PROVISIONING_KEY}" \
  -H "X-Provisioning-Secret: ${PROVISIONING_SECRET}" \
  -d "{\"deviceId\": \"${DEVICE_ID}\", \"deviceName\": \"${DEVICE_NAME}\"}")

HTTP_STATUS=$(echo "${REFRESH_RESPONSE}" | tail -n1)
echo "HTTP status: ${HTTP_STATUS}"

# Update credentials from refreshed response
REFRESH_BODY=$(echo "${REFRESH_RESPONSE}" | sed '$d')
WEBHOOK_URL=$(echo "${REFRESH_BODY}" | jq -r '.webhookUrl')
AUTH_HEADER=$(echo "${REFRESH_BODY}" | jq -r '.headers.authorization')
TWIN_ID=$(echo "${REFRESH_BODY}" | jq -r '.headers["x-twin-id"]')
echo "Credentials updated."

# ---------------------------------------------------------------------------
# HTTP Response Codes
# ---------------------------------------------------------------------------
# 200 / 201  Success
# 400        Malformed payload (missing "ts", wrong field names, bad JSON)
# 401        Token expired -> re-call /hello to get fresh credentials
# 403        Webhook disabled for this record (contact EnergyID support)
# 404        Invalid webhook URL (re-authenticate via /hello)
# 429        Rate limited -> respect the Retry-After response header

# ---------------------------------------------------------------------------
# Batch Collection Pattern (pseudocode)
# ---------------------------------------------------------------------------
# Use this pattern in a long-running script to collect readings and send
# them efficiently as batches rather than one request per reading.
#
#   BATCH=()
#   LAST_SEND=$(date +%s)
#   SEND_INTERVAL=3600   # flush batch every hour (or match uploadInterval)
#   REAUTH_INTERVAL=86400  # refresh token every 24h
#   LAST_AUTH=$(date +%s)
#
#   while true; do
#     NOW=$(date +%s)
#
#     # Re-authenticate if 24h have passed
#     if (( NOW - LAST_AUTH >= REAUTH_INTERVAL )); then
#       # re-run /hello, update WEBHOOK_URL / AUTH_HEADER / TWIN_ID
#       LAST_AUTH=${NOW}
#     fi
#
#     # Read sensor values
#     EL=$(read_electricity_meter)
#     PV=$(read_solar_meter)
#     BATCH+=("{\"ts\": ${NOW}, \"el\": ${EL}, \"pv\": ${PV}}")
#
#     # Flush batch on interval
#     if (( NOW - LAST_SEND >= SEND_INTERVAL )); then
#       PAYLOAD="[$(IFS=,; echo "${BATCH[*]}")]"
#       curl -s -X POST "${WEBHOOK_URL}" \
#         -H "authorization: ${AUTH_HEADER}" \
#         -H "x-twin-id: ${TWIN_ID}" \
#         -H "Content-Type: application/json" \
#         -d "${PAYLOAD}"
#       BATCH=()
#       LAST_SEND=${NOW}
#     fi
#
#     sleep 60
#   done
