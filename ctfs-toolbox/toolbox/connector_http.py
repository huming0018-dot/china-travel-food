"""P1 http-public connector (P1-REPAIR-02).

Uses stdlib http.client for complete HTTP/1.1 parsing (chunked bodies,
Content-Length buffering) instead of a hand-written parser. The TLS socket is
pinned to one already-verified public IP with SNI set to the original hostname
and default certificate verification.

Boundaries:
- https only, public hostnames / public literal IPs (mixed private+public DNS
  results reject the whole source, not just filter); one verified IP is chosen,
  never re-sent across another IP;
- redirects rejected (real status kept);
- HTTP errors keep real status + whitelisted headers + budgeted body/partial
  hash + UTC time + failure kind; failure payload is persisted by the crawler
  but never becomes a successful RAW input;
- body bounded by per-request budget; connection/read timeout and a hard
  deadline; no cookies/auth values recorded; no asset downloads.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
import threading
import queue
from urllib.parse import urlsplit

from .connector import Attempt, Connector, ConnectorError, FetchContext
from .validators import ValidatorError, safe_url, stamp

_HEADER_WHITELIST = frozenset((
    "content-type", "content-length", "last-modified", "etag", "date", "cache-control",
))
_READ_CHUNK = 64 * 1024


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_global


class _VerifiedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to one verified public IP, SNI = host."""

    def __init__(self, host: str, ip: str, timeout: float, context: ssl.SSLContext):
        super().__init__(host, timeout=timeout, context=context)
        self._verified_ip = ip

    def connect(self) -> None:
        raw = socket.create_connection((self._verified_ip, 443), timeout=self.timeout)
        raw.settimeout(self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
        self.sock.do_handshake()
        peer = self.sock.getpeername()[0]
        if peer != self._verified_ip or not _is_public_ip(peer):
            raise ConnectorError(f"peer IP {peer} not in verified public address set")


class HttpPublicConnector(Connector):
    name = "http-public"

    def fetch(self, ctx: FetchContext) -> Attempt:
        source = ctx.source
        source_id = source.get("source_id", "?")
        url = source.get("url", "")
        started = stamp()
        max_bytes = int(source.get("max_bytes") or ctx.max_bytes or 1_000_000)
        timeout = float(ctx.timeout_seconds or 30.0)
        deadline = time.monotonic() + timeout
        code, headers, body = None, {}, b""
        conn, timer, resp = None, None, None
        transport_sockets = []
        expired = threading.Event()
        def result(ok, error=None, kind=None):
            return Attempt(ok=ok, source_id=source_id, url=url, connector=self.name,
                           started_at=started, finished_at=stamp(), code=code,
                           bytes_count=len(body), sha256=_sha(body) if body or code is not None else None,
                           body=body if body or code is not None else None, headers=headers,
                           error=error, error_kind=kind)
        def abort():
            expired.set()
            # shutdown wakes a blocked HTTPResponse file read, including a slow
            # header/body drip; close alone leaves makefile's socket alive.
            for sock in transport_sockets + [getattr(conn, "sock", None)]:
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
        try:
            if max_bytes > ctx.max_bytes:
                raise ConnectorError("source max_bytes exceeds context budget cap")
            safe_url(url, "fetch URL")
            parsed = urlsplit(url)
            host = parsed.hostname
            if parsed.port not in (None, 443):
                raise ConnectorError("only default https port 443 allowed")
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            # A daemon resolves once. Timed-out DNS never progresses to GET.
            answers = queue.Queue(maxsize=1)
            def resolve_once():
                try:
                    answers.put((True, self._public_addresses(host)))
                except Exception as exc:
                    answers.put((False, exc))
            resolver = threading.Thread(target=resolve_once, daemon=True)
            resolver.start()
            try:
                valid, ips = answers.get(timeout=max(0.001, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise ConnectorError("DNS hard deadline exceeded") from exc
            if not valid:
                raise ips
            if not ips:
                raise ConnectorError("no public addresses for host")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ConnectorError("hard deadline exceeded")
            conn = _VerifiedHTTPSConnection(host, sorted(ips)[0], remaining,
                                            ssl.create_default_context())
            timer = threading.Timer(max(0.001, deadline - time.monotonic()), abort)
            timer.daemon = True
            timer.start()
            conn.request("GET", path, headers={"User-Agent": "ctfs-toolbox/0.5.0",
                         "Accept": "application/json", "Accept-Encoding": "identity"})
            transport_sockets.append(getattr(conn, "sock", None))
            resp = conn.getresponse()
            transport_sockets.append(getattr(getattr(getattr(resp, "fp", None), "raw", None), "_sock", None))
            code = resp.status
            all_headers = resp.getheaders()
            headers = {k.lower(): v for k, v in all_headers if k.lower() in _HEADER_WHITELIST}
            lengths = [v.strip() for k, v in all_headers if k.lower() == "content-length"]
            declared = None
            if lengths:
                if len(set(lengths)) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                    raise ConnectorError("invalid or ambiguous content-length")
                declared = int(lengths[0])
                if declared > max_bytes:
                    raise ConnectorError(f"body exceeds budget ({declared} > {max_bytes})")
            transfer = [v.lower().strip() for k, v in all_headers if k.lower() == "transfer-encoding"]
            if transfer and (declared is not None or transfer != ["chunked"]):
                raise ConnectorError("ambiguous HTTP body framing")
            while True:
                if expired.is_set() or time.monotonic() >= deadline:
                    raise ConnectorError("hard deadline exceeded")
                try:
                    # read1 returns received bytes without waiting to fill 64 KiB.
                    # A real stdlib response is used; a compatible plugin fake can
                    # expose read only for deterministic offline transport probes.
                    reader = getattr(resp, "read1", resp.read)
                    part = reader(min(_READ_CHUNK, max_bytes + 1 - len(body)))
                except http.client.IncompleteRead as exc:
                    body += exc.partial[:max(0, max_bytes + 1 - len(body))]
                    raise ConnectorError("truncated HTTP body") from exc
                if not part:
                    break
                body += part
                if len(body) > max_bytes:
                    raise ConnectorError("body exceeds budget")
            if expired.is_set() or time.monotonic() >= deadline:
                raise ConnectorError("hard deadline exceeded")
            if declared is not None and len(body) != declared:
                raise ConnectorError(f"truncated HTTP body ({len(body)} != {declared})")
            if 300 <= code < 400:
                return result(False, f"redirect rejected (HTTP {code})", "redirect-rejected")
            if not 200 <= code < 300:
                return result(False, f"HTTP error {code}", "http-error")
            return result(True)
        except ConnectorError as exc:
            return result(False, str(exc), _kind_of(str(exc)))
        except ValidatorError as exc:
            return result(False, str(exc), "unsafe-url")
        except socket.timeout as exc:
            return result(False, f"timeout: {exc}", "timeout")
        except ssl.SSLError as exc:
            return result(False, f"tls: {exc}", "tls-failed")
        except Exception as exc:
            return result(False, f"unknown: {exc}", "timeout" if expired.is_set() else "unknown")
        finally:
            if timer is not None:
                timer.cancel()
            if resp is not None and hasattr(resp, "close"):
                resp.close()
            if conn is not None:
                conn.close()

    @staticmethod
    def _public_addresses(host: str) -> set[str]:
        """Resolve once; any private/loopback result rejects the whole set."""
        try:
            infos = socket.getaddrinfo(host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ConnectorError(f"DNS resolution failed: {exc}") from exc
        ips: set[str] = set()
        for _family, _stype, _proto, _canon, sockaddr in infos:
            ip = sockaddr[0]
            if not _is_public_ip(ip):
                raise ConnectorError(
                    f"host resolved to non-public address {ip}; whole source rejected")
            ips.add(ip)
        return ips


def _sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _kind_of(message: str) -> str:
    low = message.lower()
    if "truncated" in low or "framing" in low or "content-length" in low:
        return "invalid-response"
    if "redirect" in low:
        return "redirect-rejected"
    if "budget" in low or "exceeds" in low:
        return "budget-exceeded"
    if "certificate" in low or "ssl" in low or "tls" in low:
        return "tls-failed"
    if "dns" in low or "address" in low or "resolve" in low:
        return "address-unavailable"
    if "http error" in low:
        return "http-error"
    if "timeout" in low or "deadline" in low:
        return "timeout"
    return "unknown"
