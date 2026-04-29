"""
Tip Infrastructure Detector

Detects wallets using automated transaction infrastructure:
- Nozomi (Temporal): 17 static tip addresses for priority transaction landing
- Jito: 8 static tip payment accounts for bundle inclusion

Wallets that tip these addresses are almost certainly automated —
normal users don't interact with these systems directly.

Sources:
- Nozomi: https://use.temporal.xyz/nozomi/tipping-and-faq
- Jito: https://jito-foundation.gitbook.io/mev/mev-payment-and-distribution/on-chain-addresses
"""

from typing import Dict, List, Optional, Set

# ============================================================================
# Nozomi (Temporal) Tip Addresses — 17 static addresses
# ============================================================================
NOZOMI_TIP_ADDRESSES: Set[str] = {
    "TEMPaMeCRFAS9EKF53Jd6KpHxgL47uWLcpFArU1Fanq",
    "noz3jAjPiHuBPqiSPkkugaJDkJscPuRhYnSpbi8UvC4",
    "noz3str9KXfpKknefHji8L1mPgimezaiUyCHYMDv1GE",
    "noz6uoYCDijhu1V7cutCpwxNiSovEwLdRHPwmgCGDNo",
    "noz9EPNcT7WH6Sou3sr3GGjHQYVkN3DNirpbvDkv9YJ",
    "nozc5yT15LazbLTFVZzoNZCwjh3yUtW86LoUyqsBu4L",
    "nozFrhfnNGoyqwVuwPAW4aaGqempx4PU6g6D9CJMv7Z",
    "nozievPk7HyK1Rqy1MPJwVQ7qQg2QoJGyP71oeDwbsu",
    "noznbgwYnBLDHu8wcQVCEw6kDrXkPdKkydGJGNXGvL7",
    "nozNVWs5N8mgzuD3qigrCG2UoKxZttxzZ85pvAQVrbP",
    "nozpEGbwx4BcGp6pvEdAh1JoC2CQGZdU6HbNP1v2p6P",
    "nozrhjhkCr3zXT3BiT4WCodYCUFeQvcdUkM7MqhKqge",
    "nozrwQtWhEdrA6W8dkbt9gnUaMs52PdAv5byipnadq3",
    "nozUacTVWub3cL4mJmGCYjKZTnE9RbdY5AP46iQgbPJ",
    "nozWCyTPppJjRuw2fpzDhhWbW355fzosWSzrrMYB1Qk",
    "nozWNju6dY353eMkMqURqwQEoM3SFgEKC6psLCSfUne",
    "nozxNBgWohjR75vdspfxR5H9ceC7XXH99xpxhVGt3Bb",
}

# ============================================================================
# Jito Tip Payment Accounts — 8 static addresses
# ============================================================================
JITO_TIP_ADDRESSES: Set[str] = {
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4bVqkfRtQ7NmXwkiNMQbzRd",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUC67HyGE6awqhDwYtPojDxRs4ieER1Pwpb",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
}

# Combined set for quick lookup
ALL_TIP_ADDRESSES: Set[str] = NOZOMI_TIP_ADDRESSES | JITO_TIP_ADDRESSES


def detect_tip_usage(native_transfers: List[Dict]) -> Optional[str]:
    """
    Check if any native SOL transfer in a transaction goes to a known tip address.

    Args:
        native_transfers: List of native transfer dicts from Helius parsed transaction
                         Each has: fromUserAccount, toUserAccount, amount

    Returns:
        "nozomi" if Nozomi tip detected,
        "jito" if Jito tip detected,
        None if no tip detected.
        Nozomi takes priority if both are present (more specific signal).
    """
    nozomi = False
    jito = False

    for nt in native_transfers:
        to_addr = nt.get("toUserAccount", "")
        if to_addr in NOZOMI_TIP_ADDRESSES:
            nozomi = True
        elif to_addr in JITO_TIP_ADDRESSES:
            jito = True

    if nozomi:
        return "nozomi"
    if jito:
        return "jito"
    return None


def detect_tips_in_parsed_tx(parsed_tx: Dict) -> Optional[str]:
    """
    Convenience wrapper: detect tip usage from a full Helius-parsed transaction dict.
    """
    return detect_tip_usage(parsed_tx.get("nativeTransfers", []))
