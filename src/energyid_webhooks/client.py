from typing import Dict, List, Optional
import aiohttp

import requests

from .metercatalog import MeterCatalog


class WebhookClient:
    meter_catalog_url = "https://api.energyid.eu/api/v1/catalogs/meters"

    def __init__(self, webhook_url: str, session: Optional[requests.Session] = None):
        self.webhook_url = webhook_url
        self.session = session if session is not None else requests.Session()

        self._meter_catalog = None

    def get(self) -> Dict:
        r = self.session.get(url=self.webhook_url)
        r.raise_for_status()
        return r.json()
    
    def post(self, data: Dict):
        r = self.session.post(url=self.webhook_url, json=data)
        r.raise_for_status()
        return
    
    @property
    def meter_catalog(self) -> MeterCatalog:
        if self._meter_catalog is None:
            self._meter_catalog = self.get_meter_catalog()
        return self._meter_catalog
    
    def get_meter_catalog(self) -> MeterCatalog:
        r = self.session.get(url=self.meter_catalog_url)
        r.raise_for_status()
        return MeterCatalog(r.json())
    

class WebhookClientAsync(WebhookClient):
    def __init__(self, webhook_url: str, session: Optional[aiohttp.ClientSession] = None):
        session = session if session is not None else aiohttp.ClientSession()
        super(WebhookClientAsync, self).__init__(webhook_url=webhook_url, session=session)

    async def get(self) -> Dict:
        async with self.session.get(url=self.webhook_url) as r:
            r.raise_for_status()
            return await r.json()
        
    async def post(self, data: Dict):
        async with self.session.post(url=self.webhook_url, json=data) as r:
            r.raise_for_status()
            return
        
    async def get_meter_catalog(self) -> MeterCatalog:
        async with self.session.get(url=self.meter_catalog_url) as r:
            r.raise_for_status()
            d = await r.json()
            return MeterCatalog(d)
        
    @property
    async def meter_catalog(self) -> MeterCatalog:
        if self._meter_catalog is None:
            self._meter_catalog = await self.get_meter_catalog()
        return self._meter_catalog