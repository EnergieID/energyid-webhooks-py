"""Object representation of the payload that is sent to the webhook."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class WebhookPayload:
    """Object representation of the payload that is sent to the webhook."""

    remote_id: str
    remote_name: str
    metric: str
    metric_kind: str
    unit: str
    interval: str
    data: List[List]

    def to_dict(self) -> Dict:
        """Convert the payload to a dictionary."""
        return {
            "remoteId": self.remote_id,
            "remoteName": self.remote_name,
            "metric": self.metric,
            "metricKind": self.metric_kind,
            "unit": self.unit,
            "interval": self.interval,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WebhookPayload":
        """Create a payload from a dictionary."""
        return cls(
            remote_id=data["remoteId"],
            remote_name=data["remoteName"],
            metric=data["metric"],
            metric_kind=data["metricKind"],
            unit=data["unit"],
            interval=data["interval"],
            data=data["data"],
        )

    def __repr__(self) -> str:
        return str(self.to_dict())
