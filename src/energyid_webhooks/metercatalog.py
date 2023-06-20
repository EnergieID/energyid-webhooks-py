from typing import Dict, List

class MeterCatalog:
    def __init__(self, meters: List[Dict]):
        self.meters = meters
        
    
    @property
    def meter_types(self) -> List[str]:
        return [meter['meterType'] for meter in self.meters]
    
    @property
    def all_metrics(self) -> List[str]:
        return list(set([metric for meter in self.meters for metric in meter['metrics'].keys()]))
    
    @property
    def all_units(self) -> List[str]:
        return list(set([unit for meter in self.meters for metric in meter['metrics'].keys() for unit in meter['metrics'][metric]['units']]))
    
    @property
    def all_reading_types(self) -> List[str]:
        return list(set([reading_type for meter in self.meters for metric in meter['metrics'].keys() for reading_type in meter['metrics'][metric]['readingTypes']]))
    
    def metrics(self, meter_type: str) -> List[Dict]:
        return [meter['metrics'] for meter in self.meters if meter['meterType'] == meter_type][0]
    
    def metric_names(self, meter_type: str) -> List[str]:
        return list(self.metrics(meter_type).keys())
    
    def metric_units(self, meter_type: str, metric: str) -> List[str]:
        return self.metrics(meter_type)[metric]['units']
    
    def metric_reading_types(self, meter_type: str, metric: str) -> List[str]:
        return self.metrics(meter_type)[metric]['readingTypes']
