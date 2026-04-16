from __future__ import annotations

from typing import Iterable

from app.models.schemas import AllowedCommand, CommandPolicyDecision


class RuntimeCommandPolicy:
    """Strict allowlist policy for governed runtime observation commands."""

    def __init__(self) -> None:
        self._allowlist = self._build_allowlist()

    def allowlist(self) -> list[AllowedCommand]:
        return list(self._allowlist)

    def decide(
        self,
        *,
        command_name: str,
        args: list[str],
        platform: str,
        mode: str,
    ) -> CommandPolicyDecision:
        if platform != "macos" or mode != "live":
            return CommandPolicyDecision(
                command_name=command_name,
                args=args,
                allowed=False,
                reason="Runtime command orchestration is only enabled for macOS live observation.",
                safety_class="denied",
                platform=platform,
                mode=mode,
            )

        allowed = next(
            (
                cmd
                for cmd in self._allowlist
                if cmd.command_name == command_name and cmd.args == args
            ),
            None,
        )
        if allowed is None:
            return CommandPolicyDecision(
                command_name=command_name,
                args=args,
                allowed=False,
                reason="Command arguments are not allowlisted for runtime observation.",
                safety_class="denied",
                platform=platform,
                mode=mode,
            )

        return CommandPolicyDecision(
            command_name=command_name,
            args=args,
            allowed=True,
            reason="Command matched strict macOS live read-only allowlist.",
            safety_class=allowed.safety_class,
            platform=platform,
            mode=mode,
        )

    def is_allowlisted(self, command_name: str, args: Iterable[str]) -> bool:
        args_list = list(args)
        return any(
            cmd.command_name == command_name and cmd.args == args_list
            for cmd in self._allowlist
        )

    def _build_allowlist(self) -> list[AllowedCommand]:
        return [
            AllowedCommand(
                command_name="hostname",
                args=[],
                safety_class="identity",
                platform="macos",
                mode="live",
                description="Collect hostname identity.",
            ),
            AllowedCommand(
                command_name="sw_vers",
                args=["-productVersion"],
                safety_class="identity",
                platform="macos",
                mode="live",
                description="Collect macOS product version.",
            ),
            AllowedCommand(
                command_name="uname",
                args=["-s"],
                safety_class="identity",
                platform="macos",
                mode="live",
                description="Collect operating system kernel name.",
            ),
            AllowedCommand(
                command_name="sysctl",
                args=["-n", "kern.boottime"],
                safety_class="resource",
                platform="macos",
                mode="live",
                description="Collect boot time for uptime approximation.",
            ),
            AllowedCommand(
                command_name="sysctl",
                args=["-n", "hw.memsize"],
                safety_class="resource",
                platform="macos",
                mode="live",
                description="Collect total memory size.",
            ),
            AllowedCommand(
                command_name="vm_stat",
                args=[],
                safety_class="resource",
                platform="macos",
                mode="live",
                description="Collect virtual memory statistics.",
            ),
            AllowedCommand(
                command_name="ps",
                args=["-A", "-o", "%cpu="],
                safety_class="resource",
                platform="macos",
                mode="live",
                description="Collect CPU usage approximation.",
            ),
            AllowedCommand(
                command_name="ps",
                args=["-Arc", "-o", "pid=,comm=,%cpu=,rss=,state="],
                safety_class="process",
                platform="macos",
                mode="live",
                description="Collect top process table sample.",
            ),
            AllowedCommand(
                command_name="df",
                args=["-k", "/"],
                safety_class="storage",
                platform="macos",
                mode="live",
                description="Collect root filesystem disk usage.",
            ),
            AllowedCommand(
                command_name="lsof",
                args=["-nP", "-iTCP", "-sTCP:LISTEN"],
                safety_class="network",
                platform="macos",
                mode="live",
                description="Collect listening TCP ports.",
            ),
            AllowedCommand(
                command_name="netstat",
                args=["-anv", "-p", "tcp"],
                safety_class="network",
                platform="macos",
                mode="live",
                description="Fallback listening TCP inspection when lsof is unavailable.",
            ),
        ]
