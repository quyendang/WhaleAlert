from app.collectors.evm import EvmCollector

MaticCollector = lambda: EvmCollector("MATIC")  # noqa: E731
