from typing import Dict, List

class MeterCatalog:
    def __init__(self, meters: List[Dict]):
        self.meters = meters
        
    
    @property
    def meter_types(self) -> List[str]:
        return [meter['meterType'] for meter in self.meters]
    
    def metrics(self, meter_type: str) -> List[Dict]:
        return [meter['metrics'] for meter in self.meters if meter['meterType'] == meter_type][0]
    
    def metric_names(self, meter_type: str) -> List[str]:
        return list(self.metrics(meter_type).keys())
    
    def metric_units(self, meter_type: str, metric: str) -> List[str]:
        return self.metrics(meter_type)[metric]['units']
    
    def metric_reading_types(self, meter_type: str, metric: str) -> List[str]:
        return self.metrics(meter_type)[metric]['readingTypes']
