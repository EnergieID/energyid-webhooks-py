from typing import Dict, List

class WebhookPayload:
    def __init__(self, remote_id: str, remote_name: str, metric: str, metric_kind: str, unit: str, interval: str, data: List[List]):
        self.remote_id = remote_id
        self.remote_name = remote_name
        self.metric = metric
        self.metric_kind = metric_kind
        self.unit = unit
        self.interval = interval
        self.data = data

    def to_dict(self) -> Dict:
        return {
            'remoteId': self.remote_id,
            'remoteName': self.remote_name,
            'metric': self.metric,
            'metricKind': self.metric_kind,
            'unit': self.unit,
            'interval': self.interval,
            'data': self.data
        }
    
    @classmethod
    def from_dict(cls, d: Dict):
        return cls(
            remote_id=d['remoteId'],
            remote_name=d['remoteName'],
            metric=d['metric'],
            metric_kind=d['metricKind'],
            unit=d['unit'],
            interval=d['interval'],
            data=d['data']
        )