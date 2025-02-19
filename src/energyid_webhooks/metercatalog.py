"""Meter catalog module."""


class MeterCatalog:
    """Meter catalog object."""

    def __init__(self, meters: list[dict]) -> None:
        self.meters = meters

    @property
    def meter_types(self) -> list[str]:
        """Get the meter types in the catalog."""
        return [meter["meterType"] for meter in self.meters]

    @property
    def all_metrics(self) -> list[str]:
        """Get all metrics in the catalog."""
        return list(
            {metric for meter in self.meters for metric in meter["metrics"].keys()}
        )

    @property
    def all_units(self) -> list[str]:
        """Get all units in the catalog."""
        return list(
            {
                unit
                for meter in self.meters
                for metric in meter["metrics"].keys()
                for unit in meter["metrics"][metric]["units"]
            }
        )

    @property
    def all_reading_types(self) -> list[str]:
        """Get all reading types in the catalog."""
        return list(
            {
                reading_type
                for meter in self.meters
                for metric in meter["metrics"].keys()
                for reading_type in meter["metrics"][metric]["readingTypes"]
            }
        )

    def metrics(self, meter_type: str) -> list[dict]:
        """Get the metrics for a meter type."""
        return [
            meter["metrics"]
            for meter in self.meters
            if meter["meterType"] == meter_type
        ][0]

    def metric_names(self, meter_type: str) -> list[str]:
        """Get the metric names for a meter type."""
        return list(self.metrics(meter_type).keys())

    def metric_units(self, meter_type: str, metric: str) -> list[str]:
        """Get the metric units for a meter type and metric."""
        return self.metrics(meter_type)[metric]["units"]

    def metric_reading_types(self, meter_type: str, metric: str) -> list[str]:
        """Get the metric reading types for a meter type and metric."""
        return self.metrics(meter_type)[metric]["readingTypes"]

    def __repr__(self):
        return str(self.meters)
