# energyid-webhooks-py
Light weight Python package to interface with EnergyID Webhooks

## Installation
```bash
pip install energyid-webhooks
```
## Type Checking
This package is fully type-hinted and checked with strict mypy settings.

## Usage

Get your URL at https://app.energyid.eu/integrations/WebhookIn

```python
from energyid_webhooks import WebhookClient

url = "https://app.energyid.eu/integrations/WebhookIn/..."

client = WebhookClient(url)

# Get some information about the webhook

print(client.get())

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

## Async usage

```python
import asyncio
from energyid_webhooks import WebhookClientAsync

url = "https://app.energyid.eu/integrations/WebhookIn/..."

client = WebhookClientAsync(url)

async def main():
    # Get some information about the webhook

    print(await client.get())

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

    await client.post(data)

asyncio.run(main())
```

## Demo Notebook

See [demo.ipynb](src/demo.ipynb) for a demo notebook.

## Development

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
