"""Deterministic base-Hive piece identities used by Rho's encoder."""


def piece_slot(token: str) -> int:
    color_offset = 0 if token[0] == "w" else 11
    bug = token[1]
    bug_offset = {"Q": 0, "S": 1, "B": 3, "G": 5, "A": 8}[bug]
    number = 0 if bug == "Q" else int(token[2]) - 1
    return color_offset + bug_offset + number
