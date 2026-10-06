"""Deterministic base-Hive piece identities used by Rho's encoder."""


def piece_slot(token: str) -> int:
    limits = {"Q": 1, "S": 2, "B": 2, "G": 3, "A": 3}
    if not isinstance(token, str) or len(token) < 2 or token[0] not in "wb" or token[1] not in limits:
        raise ValueError('invalid base-Hive piece identity')
    if token[1] == 'Q':
        valid = len(token) == 2
    else:
        valid = len(token) == 3 and token[2] in '123' and int(token[2]) <= limits[token[1]]
    if not valid:
        raise ValueError('invalid base-Hive piece identity')
    color_offset = 0 if token[0] == "w" else 11
    bug = token[1]
    bug_offset = {"Q": 0, "S": 1, "B": 3, "G": 5, "A": 8}[bug]
    number = 0 if bug == "Q" else int(token[2]) - 1
    return color_offset + bug_offset + number
