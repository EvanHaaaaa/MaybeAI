import ipaddress
import socket
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse


class SSRFValidationError(ValueError):
    """Raised when an outbound URL fails SSRF / scheme / host validation."""


DEFAULT_ALLOWED_SCHEMES: Tuple[str, ...] = ("http", "https", "ws", "wss")

_LOOPBACK_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
})

_METADATA_HOSTNAMES = frozenset({
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
})

_METADATA_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.100.100.200/32"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fd00:ec2::254/128"),
)

IPAddr = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _normalize_allowlist(allowlist: Optional[Iterable[str]]) -> List[str]:
    if not allowlist:
        return []
    entries: List[str] = []
    for item in allowlist:
        val = str(item or "").strip().lower()
        if val:
            entries.append(val)
    return entries


def _parse_ip_literal(host: str) -> Optional[IPAddr]:
    clean = host.strip().strip("[]")
    if "%" in clean:
        clean = clean.split("%", 1)[0]
    try:
        return ipaddress.ip_address(clean)
    except ValueError:
        return None


def _is_allowlisted(
    hostname: str,
    ips: Sequence[IPAddr],
    allowlist_entries: Sequence[str],
) -> bool:
    if not allowlist_entries:
        return False
    host_l = hostname.lower()
    for entry in allowlist_entries:
        if entry == host_l:
            return True
        if entry.startswith("*.") and len(entry) > 2:
            suffix = entry[1:]  # ".example.com"
            if host_l.endswith(suffix) and len(host_l) > len(suffix):
                return True
        if "/" in entry:
            try:
                net = ipaddress.ip_network(entry, strict=False)
                if any(ip in net for ip in ips):
                    return True
            except ValueError:
                continue
        else:
            entry_ip = _parse_ip_literal(entry)
            if entry_ip is not None and any(ip == entry_ip for ip in ips):
                return True
    return False


def _unwrap_ip(ip_obj: IPAddr) -> IPAddr:
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        return ip_obj.ipv4_mapped
    return ip_obj


def _validate_ip_address(ip_obj: IPAddr, allow_private: bool, hostname: str) -> None:
    ip = _unwrap_ip(ip_obj)
    if ip.is_link_local or any(ip in net for net in _METADATA_NETWORKS):
        raise SSRFValidationError(
            f"Outbound URL host '{hostname}' resolves to blocked link-local/metadata IP '{ip}'."
        )
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        raise SSRFValidationError(
            f"Outbound URL host '{hostname}' resolves to non-routable IP '{ip}'."
        )
    if not allow_private and (ip.is_loopback or ip.is_private):
        raise SSRFValidationError(
            f"Outbound URL host '{hostname}' resolves to private/loopback IP '{ip}' (allow_private=False)."
        )


def _resolve_hostname_ips(hostname: str, port: Optional[int]) -> List[IPAddr]:
    try:
        infos = socket.getaddrinfo(hostname, port or None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFValidationError(
            f"Failed to resolve outbound URL hostname '{hostname}': {exc}"
        ) from exc

    ips: List[IPAddr] = []
    for family, _, _, _, sockaddr in infos:
        if family in (socket.AF_INET, socket.AF_INET6) and sockaddr:
            parsed = _parse_ip_literal(str(sockaddr[0]))
            if parsed is not None and parsed not in ips:
                ips.append(parsed)
    if not ips:
        raise SSRFValidationError(f"Outbound URL hostname '{hostname}' resolved to no IP addresses.")
    return ips


def _format_host_header(hostname: str, port: Optional[int], netloc: str) -> str:
    clean_netloc = netloc.rsplit("@", 1)[-1] if netloc else ""
    if clean_netloc:
        return clean_netloc
    if ":" in hostname and not hostname.startswith("["):
        base = f"[{hostname}]"
    else:
        base = hostname
    return f"{base}:{port}" if port is not None else base


def _validate_and_resolve(
    url: str,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allow_private: bool = False,
    allowlist: Optional[Iterable[str]] = None,
) -> Tuple[str, str, str]:
    raw = str(url or "").strip()
    if not raw:
        raise SSRFValidationError("Outbound URL must not be empty.")

    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise SSRFValidationError(f"Malformed outbound URL '{raw}': {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    allowed_set = {str(s).strip().lower() for s in allowed_schemes if str(s).strip()}
    if not scheme or scheme not in allowed_set:
        raise SSRFValidationError(
            f"Unsupported URL scheme '{scheme}'. Allowed schemes: {sorted(allowed_set)}."
        )

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise SSRFValidationError(f"Outbound URL '{raw}' is missing a hostname.")

    host_header = _format_host_header(hostname, parsed.port, parsed.netloc)
    allowlist_entries = _normalize_allowlist(allowlist)
    literal_ip = _parse_ip_literal(hostname)

    if literal_ip is not None:
        if _is_allowlisted(hostname, [literal_ip], allowlist_entries):
            return raw, str(_unwrap_ip(literal_ip)), host_header
        _validate_ip_address(literal_ip, allow_private=allow_private, hostname=hostname)
        return raw, str(_unwrap_ip(literal_ip)), host_header

    if _is_allowlisted(hostname, [], allowlist_entries):
        resolved_ips = _resolve_hostname_ips(hostname, parsed.port)
        return raw, str(_unwrap_ip(resolved_ips[0])), host_header

    if hostname in _METADATA_HOSTNAMES:
        raise SSRFValidationError(f"Outbound URL host '{hostname}' is a blocked metadata hostname.")

    if hostname in _LOOPBACK_HOSTNAMES:
        if not allow_private:
            raise SSRFValidationError(
                f"Outbound URL host '{hostname}' is a loopback hostname (allow_private=False)."
            )
        try:
            resolved_ips = _resolve_hostname_ips(hostname, parsed.port)
            pinned = str(_unwrap_ip(resolved_ips[0]))
        except SSRFValidationError:
            pinned = "::1" if hostname == "ip6-loopback" else "127.0.0.1"
        return raw, pinned, host_header

    resolved_ips = _resolve_hostname_ips(hostname, parsed.port)
    if _is_allowlisted(hostname, resolved_ips, allowlist_entries):
        return raw, str(_unwrap_ip(resolved_ips[0])), host_header

    for ip_obj in resolved_ips:
        _validate_ip_address(ip_obj, allow_private=allow_private, hostname=hostname)

    return raw, str(_unwrap_ip(resolved_ips[0])), host_header


def validate_outbound_url(
    url: str,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allow_private: bool = False,
    allowlist: Optional[Iterable[str]] = None,
) -> str:
    """
    Validates an outbound URL against SSRF risks.
    Checks scheme, rejects metadata/link-local/unspecified/multicast/reserved IPs,
    and rejects loopback/RFC1918/private ranges unless `allow_private=True` or
    explicitly present in `allowlist`.
    """
    validated_url, _, _ = _validate_and_resolve(
        url,
        allowed_schemes=allowed_schemes,
        allow_private=allow_private,
        allowlist=allowlist,
    )
    return validated_url


def resolve_and_pin_host(
    url: str,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allow_private: bool = False,
    allowlist: Optional[Iterable[str]] = None,
) -> Tuple[str, str, str]:
    """
    Validates an outbound URL against SSRF risks and pins its resolved IP.
    Returns `(validated_url, pinned_ip, host_header)` to prevent DNS-rebinding TOCTOU.
    """
    return _validate_and_resolve(
        url,
        allowed_schemes=allowed_schemes,
        allow_private=allow_private,
        allowlist=allowlist,
    )


def create_pinned_connector(hostname: str, pinned_ip: str, **connector_kwargs: Any) -> Any:
    """
    Creates an `aiohttp.TCPConnector` whose DNS resolver is pinned to `pinned_ip`
    for `hostname`, preventing DNS rebinding between validation and connect.
    """
    import aiohttp
    from aiohttp.abc import AbstractResolver

    clean_host = (hostname or "").strip().strip("[]").lower()
    ip_obj = ipaddress.ip_address(str(pinned_ip).strip().strip("[]"))
    family = socket.AF_INET6 if ip_obj.version == 6 else socket.AF_INET

    class _PinnedResolver(AbstractResolver):
        async def resolve(
            self,
            host: str,
            port: int = 0,
            family: int = socket.AF_UNSPEC,
        ) -> List[Dict[str, Any]]:
            target = (host or "").strip().strip("[]").lower()
            if target != clean_host:
                raise SSRFValidationError(
                    f"Pinned connector refused unexpected host '{host}' (expected '{clean_host}')."
                )
            return [
                {
                    "hostname": host,
                    "host": str(ip_obj),
                    "port": port,
                    "family": family if family != socket.AF_UNSPEC else (
                        socket.AF_INET6 if ip_obj.version == 6 else socket.AF_INET
                    ),
                    "proto": 0,
                    "flags": socket.AI_NUMERICHOST,
                }
            ]

        async def close(self) -> None:
            return None

    return aiohttp.TCPConnector(resolver=_PinnedResolver(), **connector_kwargs)
