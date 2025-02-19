"""Objects for representing webhook policies."""


class WebhookPolicy:
    """Object representation of a webhook policy."""

    def __init__(self, policy: dict) -> None:
        self.policy = policy

    @property
    def allowed_metrics(self) -> list[str]:
        """Get the allowed metrics for this policy."""
        return self.policy["allowedMetrics"]

    @property
    def allowed_interval(self) -> str:
        """Get the shortest allowed interval for this policy."""
        return self.policy["allowedInterval"]

    @property
    def description(self) -> str:
        """Get the description of this policy."""
        return self.policy["description"]

    @property
    def display_name(self) -> str:
        """Get the display name of this policy."""
        return self.policy["displayName"]

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

    def to_dict(self) -> dict:
        """Convert the policy to a dictionary."""
        return self.policy

    @property
    def allowed_intervals(self) -> list[str]:
        """
        Returns a list of allowed intervals for this policy.
        The list is
            P1M - monthly
            P1D - daily
            PT1H - hourly
            PT15M - quarter-hourly
            PT5M - five-minute

        The policy allows all intervals that are higher
        than the allowed interval.
        """
        intervals = ["P1M", "P1D", "PT1H", "PT15M", "PT5M"]
        return intervals[: intervals.index(self.allowed_interval) + 1]
