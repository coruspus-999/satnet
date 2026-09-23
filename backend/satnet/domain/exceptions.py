class SatNetError(Exception): pass
class TLEParseError(SatNetError): pass
class TLEValidationError(SatNetError): pass
class TLEFetchError(SatNetError): pass
class PropagationError(SatNetError): pass
class ConjunctionCalculationError(SatNetError): pass
class ProbabilityCalculationError(SatNetError): pass
class MLInferenceError(SatNetError): pass
