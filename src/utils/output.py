"""Output formatting utilities for the CTF agent."""


def truncate_output(output: str, max_length: int) -> str:
    """Truncate command output using a head+tail strategy to fit within a character limit.

    Returns the original output unchanged if it's already within the limit,
    otherwise keeps the first and last portions with a truncation warning.
    """
    if len(output) <= max_length:
        return output

    separator = "\n...\n"
    head_len = max_length // 2
    tail_len = max(max_length - head_len - len(separator), 0)
    truncated = output[:head_len]
    if tail_len:
        truncated += separator + output[-tail_len:]
    warning = f"[SYSTEM WARNING: Output truncated. Showing first {head_len} and last {tail_len} of {len(output)} characters]\n\n"
    return warning + truncated
