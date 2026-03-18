from app.collectors.evm import EvmCollector

BscCollector = lambda: EvmCollector("BSC")  # noqa: E731
