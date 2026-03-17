"""PTY-based session manager for Docker command execution via pexpect.

Experimental alternative to the blocking docker exec + thread model in docker_exec.py.
Opt-in behind USE_PTY_MODE flag in the agent entry points.
"""

import re
import shlex
import time

import pexpect

INTERACTIVE_PROMPT_PATTERNS = [
    re.compile(r"[Pp]assword\s*:"),
    re.compile(r"[Pp]assphrase\s*:"),
    re.compile(r"\[Y/n\]"),
    re.compile(r"\[y/N\]"),
    re.compile(r"\(yes/no\)"),
    re.compile(r"\(yes/no/\[fingerprint\]\)"),
    re.compile(r"[Ll]ogin\s*:"),
    re.compile(r"[Uu]sername\s*:"),
    re.compile(r"Continue\?"),
    re.compile(r"Are you sure"),
]

# Pre-built expect list: raw pattern strings + EOF + TIMEOUT sentinels.
# Cached at module level so _collect_output doesn't rebuild it every call.
_EXPECT_PATTERNS: list = [p.pattern for p in INTERACTIVE_PROMPT_PATTERNS]
_EXPECT_PATTERNS.append(pexpect.EOF)
_EXPECT_PATTERNS.append(pexpect.TIMEOUT)


# Values treated as empty/filler when resolving ambiguous both-fields-set responses.
_FILLER_VALUES = {"", "none", "n/a", "nothing"}


def resolve_pty_fields(shell_command: str, stdin_input: str) -> tuple[str, str]:
    """Disambiguate when both shell_command and stdin_input are non-empty.

    Returns the resolved (shell_command, stdin_input) pair with at most one non-empty.
    """
    shell_stripped = shell_command.strip()
    stdin_stripped = stdin_input.strip()

    if not (shell_stripped and stdin_stripped):
        return shell_command, stdin_input

    if stdin_stripped.lower() in _FILLER_VALUES:
        return shell_command, ""
    if shell_stripped.lower() in _FILLER_VALUES:
        return "", stdin_input

    print("Warning: both shell_command and stdin_input set. Preferring shell_command.")
    return shell_command, ""


def dispatch_pty_command(
    pty_manager: "PtySessionManager",
    shell_command: str,
    stdin_input: str,
) -> tuple[str, bool, int | None]:
    """Run a resolved PTY action (exec or stdin write).

    Caller should first pass through resolve_pty_fields() to ensure at most one
    field is non-empty.
    """
    shell_stripped = shell_command.strip()
    stdin_stripped = stdin_input.strip()

    if shell_stripped:
        return pty_manager.exec_command(shell_command)
    if stdin_stripped:
        return pty_manager.write_stdin(stdin_input)
    return "", True, None


class PtySessionManager:
    """Manage a single PTY session inside a Docker container via pexpect."""

    def __init__(
        self,
        container_name: str,
        idle_timeout: float = 300,
        prompt_idle: float = 2.0,
        max_session_lifetime: int = 1800,
    ):
        self.container_name = container_name
        self.idle_timeout = idle_timeout  # 5 minutes default
        self.prompt_idle = prompt_idle  # 2 seconds after prompt detection
        self.max_session_lifetime = max_session_lifetime  # 30 minutes
        self._session: pexpect.spawn | None = None
        self._session_start: float | None = None

    def exec_command(self, command: str) -> tuple[str, bool, int | None]:
        """Execute a command in the container. Returns (output, process_exited, exit_code_or_none)."""
        self._kill_session()

        quoted = shlex.quote(command)
        spawn_cmd = f"docker exec -it {self.container_name} bash -lc {quoted}"

        self._session = pexpect.spawn(spawn_cmd, timeout=self.idle_timeout, encoding="utf-8")
        self._session_start = time.time()

        return self._collect_output()

    def write_stdin(self, text: str) -> tuple[str, bool, int | None]:
        """Send input to the running session. Returns (new_output, process_exited, exit_code_or_none)."""
        if self._session is None or not self._session.isalive():
            return "No active session to write to.", True, None

        self._session.sendline(text)
        return self._collect_output()

    def cleanup(self) -> None:
        """Kill current session if any."""
        self._kill_session()

    def _kill_session(self) -> None:
        """Terminate the current pexpect session if one is active."""
        if self._session is not None:
            if self._session.isalive():
                self._session.terminate(force=True)
            self._session = None
            self._session_start = None

    def _collect_output(self) -> tuple[str, bool, int | None]:
        """Read output until idle timeout, prompt detection, or process exit.

        Returns (collected_output, process_exited, exit_code_or_none).
        """
        if self._session is None:
            return "", True, None

        output_parts: list[str] = []
        process_exited = False
        exit_code: int | None = None

        # Check session lifetime cap
        if self._session_start is not None:
            elapsed = time.time() - self._session_start
            if elapsed >= self.max_session_lifetime:
                self._kill_session()
                return "Session exceeded maximum lifetime.", True, None

        while True:
            # Check lifetime cap on each loop iteration
            if self._session_start is not None:
                elapsed = time.time() - self._session_start
                if elapsed >= self.max_session_lifetime:
                    output_parts.append("\nSession exceeded maximum lifetime.")
                    self._kill_session()
                    return "".join(output_parts), True, None

            try:
                idx = self._session.expect(_EXPECT_PATTERNS, timeout=self.idle_timeout)
            except pexpect.TIMEOUT:
                # Idle timeout reached
                if self._session.before:
                    output_parts.append(self._session.before)
                break
            except pexpect.EOF:
                if self._session.before:
                    output_parts.append(self._session.before)
                process_exited = True
                exit_code = self._extract_exit_code()
                break

            # Collect text before match
            if self._session.before:
                output_parts.append(self._session.before)

            eof_idx = len(INTERACTIVE_PROMPT_PATTERNS)
            timeout_idx = eof_idx + 1

            if idx == eof_idx:
                # EOF
                process_exited = True
                exit_code = self._extract_exit_code()
                break
            elif idx == timeout_idx:
                # Idle timeout
                break
            else:
                # Interactive prompt detected - include the matched text
                if self._session.after:
                    output_parts.append(self._session.after)

                # Switch to short prompt_idle timeout to catch trailing output
                try:
                    self._session.expect(
                        [pexpect.EOF, pexpect.TIMEOUT],
                        timeout=self.prompt_idle,
                    )
                    if self._session.before:
                        output_parts.append(self._session.before)
                except pexpect.EOF:
                    if self._session.before:
                        output_parts.append(self._session.before)
                    process_exited = True
                    exit_code = self._extract_exit_code()
                except pexpect.TIMEOUT:
                    if self._session.before:
                        output_parts.append(self._session.before)
                break

        return "".join(output_parts).strip(), process_exited, exit_code

    def _extract_exit_code(self) -> int | None:
        """Try to extract the exit code from the finished pexpect session."""
        if self._session is None:
            return None
        try:
            self._session.close()
            return self._session.exitstatus
        except Exception:
            return None
