"""Tests for crypto collector."""

from finn.collectors.crypto import CryptoCollector, CRYPTO_COINS, COINGECKO_IDS


def test_crypto_coins_mapping():
    assert "BTC" in CRYPTO_COINS
    assert CRYPTO_COINS["BTC"] == "BTC-USD"
    assert "ETH" in CRYPTO_COINS


def test_coingecko_ids():
    assert COINGECKO_IDS["BTC"] == "bitcoin"
    assert COINGECKO_IDS["ETH"] == "ethereum"


def test_collector_name():
    collector = CryptoCollector()
    assert collector.name == "crypto"
    assert collector.is_available is True


def test_collector_handles_empty_tickers():
    collector = CryptoCollector()
    # Should not crash with tickers not in our mapping
    signals = collector._collect_yfinance(["NONEXISTENT"])
    assert signals == []
