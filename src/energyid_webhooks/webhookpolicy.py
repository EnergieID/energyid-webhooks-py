from typing import Dict, List

class WebhookPolicy:
    def __init__(self, policy: Dict):
        self.policy = policy
    
    @property
    def allowed_metrics(self) -> List[str]:
        return self.policy['allowedMetrics']
    
    @property
    def allowed_interval(self) -> str:
        return self.policy['allowedInterval']
    
    @property
    def description(self) -> str:
        return self.policy['description']
    
    @property
    def display_name(self) -> str:
        return self.policy['displayName']
    
    def __repr__(self):
        return str(self.policy)
    
    def __str__(self):
        return self.__repr__()
    
    def __eq__(self, other):
        return self.policy == other.policy
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __hash__(self):
        return hash(self.policy)
    
    def to_dict(self) -> Dict:
        return self.policy
    
    @property
    def allowed_intervals(self) -> List[str]:
        """
        Returns a list of allowed intervals for this policy.
        The list is
            P1M - monthly
            P1D - daily
            PT1H - hourly
            PT15M - quarter-hourly
            PT5M - five-minute

        The policy allows all intervals that are higher up the list than the allowed interval.
        """
        intervals = ['P1M', 'P1D', 'PT1H', 'PT15M', 'PT5M']
        return intervals[:intervals.index(self.allowed_interval)+1]