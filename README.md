# energyid-webhooks

Python package for interfacing with EnergyID Webhooks (supports both V1 and V2 APIs)

## Installation

```bash
pip install energyid-webhooks
```

## Features

- **V2 API support** with device provisioning and claiming
- Authentication with automatic token renewal
- Smart sensor bundling for efficient data transmission
- Async support
- Full type hints

## Type Checking

This package is fully type-hinted and checked with strict mypy settings.

## V2 API Usage (Recommended)

The V2 API includes device provisioning, authentication, and smart bundling:

```python
import asyncio
from energyid_webhooks import WebhookClient

# Create the client
client = WebhookClient(
    client_id="your_provisioning_key",
    client_secret="your_provisioning_secret",
    device_id="unique_device_id",
    device_name="My Device",
    reauth_interval=24  # Hours between token refresh
)

async def main():
    # Authenticate with EnergyID
    is_claimed = await client.authenticate()

    if not is_claimed:
        # Device needs to be claimed
        claim_info = client.get_claim_info()
        print(f"Claim your device at {claim_info['claim_url']} with code {claim_info['claim_code']}")
        # Wait for claiming...
        return

    # Add and update sensors
    client.update_sensor("el", 1250.5)  # Electricity consumption
    client.update_sensor("pv", 3560.2)  # Solar production

    # Synchronize with EnergyID
    await client.synchronize_sensors()

    # Or enable automatic synchronization
    client.start_auto_sync(interval_seconds=300)  # Every 5 minutes

    # Don't forget to close when done
    await client.close()

asyncio.run(main())
```

## V1 API Usage (Legacy)

The original API is still available for backward compatibility:

```python
from energyid_webhooks import WebhookClientV1, WebhookPayload

url = "https://app.energyid.eu/integrations/WebhookIn/..."

client = WebhookClientV1(url)

# Post some data to the webhook
data = {
    'remoteId': 'my-solar-inverter',
    'remoteName': 'My Solar Panels',
    'metric': 'solarPhotovoltaicProduction',
    'metricKind': 'total',
    'unit': 'kWh',
    'interval': 'P1D',
    'data': [['2022-10-05T08:00+0200', 0.004]]
}

client.post(data)
```

## V1 Async Usage (Legacy)

```python
import asyncio
from energyid_webhooks import WebhookClientAsyncV1

url = "https://app.energyid.eu/integrations/WebhookIn/..."

client = WebhookClientAsyncV1(url)

async def main():
    data = {
        'remoteId': 'my-solar-inverter',
        'remoteName': 'My Solar Panels',
        'metric': 'solarPhotovoltaicProduction',
        'metricKind': 'total',
        'unit': 'kWh',
        'interval': 'P1D',
        'data': [['2022-10-05T08:00+0200', 0.004]]
    }

    await client.post(data)

asyncio.run(main())
```

## Demo Notebook

See [energyid_webhook_demo.ipynb](demos/energyid_webhook_demo.ipynb) for a complete V2 API demo.

## Development

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
