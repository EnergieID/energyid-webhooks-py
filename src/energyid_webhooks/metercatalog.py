"""Meter catalog module."""

from typing import Any, cast


class MeterCatalog:
    """Meter catalog object."""

    def __init__(self, meters: list[dict[str, Any]]) -> None:
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
                for metric in meter["metrics"].values()
                for unit in metric["units"]
            }
        )

    @property
    def all_reading_types(self) -> list[str]:
        """Get all reading types in the catalog."""
        return list(
            {
                reading_type
                for meter in self.meters
                for metric in meter["metrics"].values()
                for reading_type in metric["readingTypes"]
            }
        )

    def metrics(self, meter_type: str) -> dict[str, Any]:
        """Get the metrics for a meter type."""
        matching_meters = [
            meter["metrics"]
            for meter in self.meters
            if meter["meterType"] == meter_type
        ]
        if not matching_meters:
            raise ValueError(f"No meter found with type {meter_type}")
        # Use cast to ensure the return type matches the declaration
        return cast(dict[str, Any], matching_meters[0])

    def metric_names(self, meter_type: str) -> list[str]:
        """Get the metric names for a meter type."""
        return list(self.metrics(meter_type).keys())

    def metric_units(self, meter_type: str, metric: str) -> list[str]:
        """Get the metric units for a meter type and metric."""
        metrics_dict = self.metrics(meter_type)
        # Use cast to ensure we return List[str]
        return cast(list[str], metrics_dict[metric]["units"])

    def metric_reading_types(self, meter_type: str, metric: str) -> list[str]:
        """Get the metric reading types for a meter type and metric."""
        metrics_dict = self.metrics(meter_type)
        return cast(list[str], metrics_dict[metric]["readingTypes"])

    def __repr__(self) -> str:
        return str(self.meters)
