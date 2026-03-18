"""Known wallet/exchange address labels."""

# Well-known exchange and protocol addresses
KNOWN_LABELS: dict[str, str] = {
    # Ethereum - Exchanges
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance",
    "0xd551234ae421e3bcba99a0da6d736074f22192ff": "Binance",
    "0x564286362092d8e7936f0549571a803b203aaced": "Binance",
    "0x0681d8db095565fe8a346fa0277bffde9c0edbbf": "Binance",
    "0xfe9e8709d3215310075d67e3ed32a380ccf451c8": "Binance",
    "0x4e9ce36e442e55ecd9025b9a6e0d88485d628a67": "Binance",
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance Cold Wallet",
    "0x8103683202aa8da10536036edec88c27cad7b584": "Binance",
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance",
    "0x9696f59e4d72e237be84ffd425dcad154bf96976": "Binance",
    "0xa910f92acdaf488fa6ef02174fb86208ad7722ba": "Binance",
    "0x4b1a99467a284cc690e3237bc69105956816f762": "Binance",

    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
    "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": "Coinbase",
    "0x3cd751e6b0078be393132286c442345e5dc49699": "Coinbase",
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": "Coinbase",
    "0xeb2629a2734e272bcc07bda959863f316f4bd4cf": "Coinbase",
    "0x02466e547bfdab679fc49e96bbfc62b9747d997c": "Coinbase",
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase Cold Wallet",

    # Kraken
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
    "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13": "Kraken",
    "0xe853c56864a2ebe4576a807d26fdc4a0ada51919": "Kraken",
    "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
    "0xfa52274dd61e1643d2205169732f29114bc240b3": "Kraken",

    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": "OKX",
    "0xa7efae728d2936e78bda97dc267687568dd593f3": "OKX",

    # Huobi
    "0x6748f50f686bfbca6fe8ad62b22228b87f31ff2b": "Huobi",
    "0xfdb16996831753d5331ff813c29a93c76834a0ad": "Huobi",
    "0xeee28d484628d41a82d01e21d12e2e78d69920da": "Huobi",
    "0x1062a747393198f70f71ec65a582423dba7e5ab3": "Huobi",

    # Uniswap
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 Router 2",

    # Bitcoin exchanges (simplified - BTC uses different address format)
    "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s": "Binance BTC",
    "3E35SFZkfLMGo4qX5aVs1bBDSnAuGgBH33": "Bitfinex BTC",
    "385cR5DM96n1HvBDMzLHPYcw89fZAXULJP": "Bitfinex BTC",
    "1LQoWist8KkaUXSPKZHNvEyfrEkPHzSsCd": "Coinbase BTC",

    # TRON exchanges
    "TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9": "Binance TRX",
    "TKVTyqfLAcpPSGtfPGAmy5A1QJbpivDEyp": "Huobi TRX",
    "TGjgkFPfFmKxKPYGzrYkMfRVfFCKHdBCKb": "OKX TRX",
}


def get_label(address: str) -> str:
    """Return known label for address or 'Unknown'."""
    if not address:
        return "Unknown"
    return KNOWN_LABELS.get(address.lower(), KNOWN_LABELS.get(address, "Unknown"))
