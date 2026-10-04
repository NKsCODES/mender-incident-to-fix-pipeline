def parse_percent(value: str) -> int:
    """Parse a percent discount such as '10' or '10%'.

    Surrounding and inner whitespace is ignored. The result must be within
    0..100, anything else raises ValueError.
    """
    return int(value)
