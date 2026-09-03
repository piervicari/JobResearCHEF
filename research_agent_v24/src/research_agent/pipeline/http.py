"""Rate-limited HTTP client with bounded retries, redirects, bodies and public destinations."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import random
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from research_agent.pipeline.cache import FileResponseCache


class FetchError(RuntimeError):
    def __init__(self, message: str, *, attempts: tuple[FetchAttempt, ...]) -> None:
        super().__init__(message)
        self.attempts = attempts


class UnsafeDestinationError(FetchError):
    """The requested URL or one of its redirects is outside the public HTTP boundary."""


class ResponseTooLargeError(FetchError):
    """A response exceeded the configured body budget."""


class TooManyRedirectsError(FetchError):
    """A redirect chain exceeded the configured safety cap."""


class RequestBudgetExceededError(FetchError):
    """A per-host or overall request budget was exhausted."""


class HostCircuitOpenError(FetchError):
    """The host is blocked for the rest of the run after an access-control signal."""


class AccessChallengeError(FetchError):
    """A response strongly matched a bot or human-verification challenge."""


@dataclass(frozen=True)
class FetchRequest:
    url: str
    headers: dict[str, str] | None = None
    allow_cache: bool = True
    method: str = "GET"
    json_body: dict[str, object] | None = None
    form_body: dict[str, str] | None = None


@dataclass(frozen=True)
class FetchAttempt:
    status_code: int | None
    error_type: str | None
    elapsed_seconds: float
    url: str = ""
    retry_index: int = 0
    redirect: bool = False


@dataclass(frozen=True)
class FetchResponse:
    requested_url: str
    final_url: str
    status_code: int
    network_status_code: int
    headers: dict[str, str]
    content: bytes
    fetched_at: datetime
    attempts: tuple[FetchAttempt, ...]
    from_cache: bool
    not_modified: bool
    response_sha256: str

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            encoding = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        return self.content.decode(encoding, errors="replace")

    def json(self) -> Any:
        import json

        return json.loads(self.content)


@dataclass
class _HostState:
    semaphore: asyncio.Semaphore
    start_lock: asyncio.Lock
    next_start_at: float = 0.0


class DomainRateLimiter:
    def __init__(
        self,
        *,
        global_concurrency: int,
        per_domain_concurrency: int,
        per_domain_min_interval_seconds: float,
        jitter_seconds: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self._global = asyncio.Semaphore(global_concurrency)
        self._per_domain_concurrency = per_domain_concurrency
        self._interval = per_domain_min_interval_seconds
        self._jitter = jitter_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._random = random_value
        self._hosts: dict[str, _HostState] = {}

    def _host_state(self, host: str) -> _HostState:
        if host not in self._hosts:
            self._hosts[host] = _HostState(
                semaphore=asyncio.Semaphore(self._per_domain_concurrency),
                start_lock=asyncio.Lock(),
            )
        return self._hosts[host]

    async def run(self, host: str, operation: Callable[[], Awaitable[Any]]) -> Any:
        state = self._host_state(host)
        async with self._global, state.semaphore:
            async with state.start_lock:
                wait_seconds = max(0.0, state.next_start_at - self._monotonic())
                if wait_seconds:
                    await self._sleep(wait_seconds)
                state.next_start_at = (
                    self._monotonic() + self._interval + self._jitter * self._random()
                )
            return await operation()


class HttpFetcher:
    RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
    REDIRECT_STATUSES = {301, 302, 303, 307, 308}
    CIRCUIT_BREAKER_STATUSES = {401, 403, 429}
    _CHALLENGE_MARKERS = (
        b"<title>just a moment...</title>",
        b"cf-chl-",
        # ``cf-turnstile`` alone is intentionally NOT a hard challenge marker.
        # Legitimate job/application pages may embed a Turnstile widget while the
        # vacancy content itself is fully accessible (observed on Wazuh).
        b"verify you are human",
        b"unusual traffic from your computer network",
        b"px-captcha",
        b"perimeterx",
        b"botmanager_support@radware.com",
        b"validate.perfdrive.com",
    )
    _CHALLENGE_HOSTS = {"validate.perfdrive.com"}

    def __init__(
        self,
        *,
        global_concurrency: int = 8,
        per_domain_concurrency: int = 1,
        per_domain_min_interval_seconds: float = 1.0,
        request_timeout_seconds: float = 20.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 30.0,
        max_retry_after_seconds: float = 60.0,
        jitter_seconds: float = 0.5,
        max_response_bytes: int = 10_000_000,
        max_redirects: int = 10,
        max_requests_per_host_per_run: int = 100,
        max_requests_per_run: int = 1_000,
        allow_private_networks: bool = False,
        allow_https_to_http_redirects: bool = False,
        resolve_dns: bool = True,
        user_agent: str = "research-agent-pier/0.2",
        initially_blocked_hosts: dict[str, str] | None = None,
        cache: FileResponseCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be at least 1")
        if max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        if max_requests_per_host_per_run < 1 or max_requests_per_run < 1:
            raise ValueError("Request budgets must be at least 1")
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._max_retry_after = max_retry_after_seconds
        self._jitter = jitter_seconds
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._max_requests_per_host = max_requests_per_host_per_run
        self._max_requests = max_requests_per_run
        self._allow_private_networks = allow_private_networks
        self._allow_https_to_http_redirects = allow_https_to_http_redirects
        self._resolve_dns = resolve_dns
        self._cache = cache
        self._sleep = sleep
        self._random = random_value
        self._budget_lock = asyncio.Lock()
        self._request_count = 0
        self._host_request_counts: dict[str, int] = {}
        self._blocked_hosts = {
            host.rstrip(".").casefold(): reason
            for host, reason in (initially_blocked_hosts or {}).items()
        }
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=request_timeout_seconds,
            headers={"User-Agent": user_agent},
            limits=httpx.Limits(
                max_connections=global_concurrency,
                max_keepalive_connections=global_concurrency,
            ),
        )
        self._limiter = DomainRateLimiter(
            global_concurrency=global_concurrency,
            per_domain_concurrency=per_domain_concurrency,
            per_domain_min_interval_seconds=per_domain_min_interval_seconds,
            jitter_seconds=jitter_seconds,
            sleep=sleep,
            random_value=random_value,
        )

    async def __aenter__(self) -> HttpFetcher:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def host_request_counts(self) -> dict[str, int]:
        return dict(self._host_request_counts)

    @property
    def blocked_hosts(self) -> dict[str, str]:
        return dict(self._blocked_hosts)

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        method = request.method.strip().upper()
        if method not in {"GET", "POST"}:
            raise FetchError(f"Unsupported HTTP method: {method}", attempts=())
        if request.json_body is not None and request.form_body is not None:
            raise FetchError("Requests cannot include both json_body and form_body", attempts=())
        if method == "GET" and (request.json_body is not None or request.form_body is not None):
            raise FetchError("GET requests cannot include a request body", attempts=())
        cached = (
            self._cache.get(request.url)
            if self._cache and request.allow_cache and method == "GET"
            else None
        )
        if cached and len(cached.content) > self._max_response_bytes:
            raise ResponseTooLargeError(
                f"Cached response exceeds {self._max_response_bytes} bytes for {request.url}",
                attempts=(),
            )
        headers = {"Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
        headers.update(request.headers or {})
        if cached:
            for key, value in cached.conditional_headers.items():
                headers.setdefault(key, value)

        attempts: list[FetchAttempt] = []
        for retry_index in range(self._max_retries + 1):
            current_url = request.url
            current_method = method
            current_json = request.json_body
            current_form = request.form_body
            response: httpx.Response | None = None
            content = b""
            redirect_count = 0
            while True:
                try:
                    await self._validate_destination(current_url)
                except ValueError as exc:
                    raise UnsafeDestinationError(str(exc), attempts=tuple(attempts)) from exc
                parsed = urlsplit(current_url)
                started = time.monotonic()
                try:
                    response, content = await self._limiter.run(
                        parsed.hostname or "",
                        lambda target_url=current_url, target_method=current_method,
                        target_json=current_json, target_form=current_form: self._guarded_request(
                            target_url,
                            headers,
                            method=target_method,
                            json_body=target_json,
                            form_body=target_form,
                        ),
                    )
                except (RequestBudgetExceededError, HostCircuitOpenError) as exc:
                    raise type(exc)(str(exc), attempts=tuple(attempts)) from exc
                except ResponseTooLargeError as exc:
                    elapsed = time.monotonic() - started
                    attempts.append(
                        FetchAttempt(
                            status_code=None,
                            error_type=type(exc).__name__,
                            elapsed_seconds=elapsed,
                            url=current_url,
                            retry_index=retry_index,
                        )
                    )
                    raise ResponseTooLargeError(str(exc), attempts=tuple(attempts)) from exc
                except httpx.HTTPError as exc:
                    elapsed = time.monotonic() - started
                    attempts.append(
                        FetchAttempt(
                            status_code=None,
                            error_type=type(exc).__name__,
                            elapsed_seconds=elapsed,
                            url=current_url,
                            retry_index=retry_index,
                        )
                    )
                    response = None
                    break

                elapsed = time.monotonic() - started
                location = response.headers.get("Location")
                is_redirect = response.status_code in self.REDIRECT_STATUSES and bool(location)
                attempts.append(
                    FetchAttempt(
                        status_code=response.status_code,
                        error_type=None,
                        elapsed_seconds=elapsed,
                        url=current_url,
                        retry_index=retry_index,
                        redirect=is_redirect,
                    )
                )
                blocking_reason = self._blocking_reason(response, content)
                challenge_detected = self._contains_challenge(content) or self._is_challenge_url(
                    current_url
                )
                if challenge_detected:
                    raise AccessChallengeError(
                        "Access challenge detected at "
                        f"{current_url}: {blocking_reason or 'known challenge endpoint'}",
                        attempts=tuple(attempts),
                    )
                if response.status_code == 429:
                    raise HostCircuitOpenError(
                        f"Host circuit opened after HTTP 429 from {current_url}",
                        attempts=tuple(attempts),
                    )
                if not is_redirect:
                    break
                if redirect_count >= self._max_redirects:
                    raise TooManyRedirectsError(
                        f"Redirect limit of {self._max_redirects} exceeded for {request.url}",
                        attempts=tuple(attempts),
                    )
                next_url = urljoin(current_url, location or "")
                if (
                    urlsplit(current_url).scheme == "https"
                    and urlsplit(next_url).scheme == "http"
                    and not self._allow_https_to_http_redirects
                ):
                    raise UnsafeDestinationError(
                        f"HTTPS-to-HTTP redirect is not allowed: {current_url} -> {next_url}",
                        attempts=tuple(attempts),
                    )
                current_url = next_url
                if response.status_code == 303 or (
                    response.status_code in {301, 302} and current_method == "POST"
                ):
                    current_method = "GET"
                    current_json = None
                    current_form = None
                redirect_count += 1
                headers.pop("If-None-Match", None)
                headers.pop("If-Modified-Since", None)

            if response is not None and response.status_code not in self.RETRYABLE_STATUSES:
                return self._build_response(
                    request,
                    response,
                    content,
                    cached,
                    tuple(attempts),
                )
            if retry_index >= self._max_retries:
                break
            delay = self._retry_delay(response, retry_index)
            await self._sleep(delay)

        last = attempts[-1]
        detail = (
            f"HTTP {last.status_code}"
            if last.status_code is not None
            else last.error_type or "error"
        )
        raise FetchError(
            f"Fetch failed for {request.url} after {len(attempts)} requests: {detail}",
            attempts=tuple(attempts),
        )

    async def _guarded_request(
        self,
        url: str,
        headers: dict[str, str],
        *,
        method: str,
        json_body: dict[str, object] | None,
        form_body: dict[str, str] | None,
    ) -> tuple[httpx.Response, bytes]:
        host = (urlsplit(url).hostname or "").rstrip(".").casefold()
        async with self._budget_lock:
            if reason := self._blocked_hosts.get(host):
                raise HostCircuitOpenError(
                    f"Host circuit is open for {host}: {reason}", attempts=()
                )
            host_count = self._host_request_counts.get(host, 0)
            if host_count >= self._max_requests_per_host:
                raise RequestBudgetExceededError(
                    f"Per-host request budget of {self._max_requests_per_host} "
                    f"exhausted for {host}",
                    attempts=(),
                )
            if self._request_count >= self._max_requests:
                raise RequestBudgetExceededError(
                    f"Overall request budget of {self._max_requests} exhausted", attempts=()
                )
            self._host_request_counts[host] = host_count + 1
            self._request_count += 1

        response, content = await self._request_once(
            url,
            headers,
            method=method,
            json_body=json_body,
            form_body=form_body,
        )
        if reason := self._blocking_reason(response, content):
            async with self._budget_lock:
                self._blocked_hosts.setdefault(host, reason)
        return response, content

    @classmethod
    def _blocking_reason(cls, response: httpx.Response, content: bytes) -> str | None:
        if response.status_code in cls.CIRCUIT_BREAKER_STATUSES:
            return f"HTTP {response.status_code}"
        if cls._contains_challenge(content):
            return "access challenge"
        return None

    @classmethod
    def _contains_challenge(cls, content: bytes) -> bool:
        sample = content[:200_000].lower()
        return any(marker in sample for marker in cls._CHALLENGE_MARKERS)

    @classmethod
    def _is_challenge_url(cls, url: str) -> bool:
        return (urlsplit(url).hostname or "").casefold() in cls._CHALLENGE_HOSTS

    async def _request_once(
        self,
        url: str,
        headers: dict[str, str],
        *,
        method: str,
        json_body: dict[str, object] | None,
        form_body: dict[str, str] | None,
    ) -> tuple[httpx.Response, bytes]:
        async with self._client.stream(
            method,
            url,
            headers=headers,
            json=json_body,
            data=form_body,
        ) as response:
            if response.status_code in self.REDIRECT_STATUSES and response.headers.get("Location"):
                return response, b""
            declared_length = response.headers.get("Content-Length")
            if declared_length:
                try:
                    if int(declared_length) > self._max_response_bytes:
                        raise ResponseTooLargeError(
                            "Response Content-Length exceeds "
                            f"{self._max_response_bytes} bytes for {url}",
                            attempts=(),
                        )
                except ValueError:
                    pass
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > self._max_response_bytes:
                    raise ResponseTooLargeError(
                        f"Response body exceeds {self._max_response_bytes} bytes for {url}",
                        attempts=(),
                    )
                chunks.append(chunk)
            return response, b"".join(chunks)

    async def _validate_destination(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"Invalid HTTP(S) URL: {url}")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError(f"Credentials in URL are not allowed: {url}")
        host = parsed.hostname.rstrip(".").casefold()
        if self._allow_private_networks:
            return
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            raise ValueError(f"Non-public destination is not allowed: {host}")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            if not address.is_global:
                raise ValueError(f"Non-public destination is not allowed: {address}")
            return
        if not self._resolve_dns:
            return
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            records = await asyncio.get_running_loop().getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise ValueError(f"DNS resolution failed for {host}: {exc}") from exc
        addresses = {record[4][0] for record in records}
        if not addresses:
            raise ValueError(f"DNS resolution returned no addresses for {host}")
        non_public = sorted(
            value for value in addresses if not ipaddress.ip_address(value).is_global
        )
        if non_public:
            raise ValueError(
                f"DNS for {host} includes non-public address(es): {', '.join(non_public)}"
            )

    def _retry_delay(self, response: httpx.Response | None, retry_index: int) -> float:
        if response is not None and response.status_code == 429:
            if retry_after := response.headers.get("Retry-After"):
                parsed = _parse_retry_after(retry_after)
                if parsed is not None:
                    return min(parsed, self._max_retry_after)
        exponential = min(self._backoff_base * (2**retry_index), self._backoff_max)
        return exponential + self._jitter * self._random()

    def _build_response(
        self,
        request: FetchRequest,
        response: httpx.Response,
        response_content: bytes,
        cached: object | None,
        attempts: tuple[FetchAttempt, ...],
    ) -> FetchResponse:
        if response.status_code == 304:
            if cached is None:
                raise FetchError(
                    f"Received 304 without cached content for {request.url}", attempts=attempts
                )
            content = cached.content  # type: ignore[attr-defined]
            status_code = cached.status_code  # type: ignore[attr-defined]
            final_url = cached.final_url  # type: ignore[attr-defined]
            cached_headers = cached.headers  # type: ignore[attr-defined]
            response_headers = {**cached_headers, **dict(response.headers)}
            from_cache = True
            not_modified = True
        else:
            content = response_content
            status_code = response.status_code
            final_url = str(response.url)
            response_headers = dict(response.headers)
            from_cache = False
            not_modified = False
            if (
                self._cache
                and request.allow_cache
                and request.method.strip().upper() == "GET"
                and response.status_code == 200
            ):
                self._cache.store(
                    url=request.url,
                    final_url=final_url,
                    status_code=status_code,
                    headers=response_headers,
                    content=content,
                )

        return FetchResponse(
            requested_url=request.url,
            final_url=final_url,
            status_code=status_code,
            network_status_code=response.status_code,
            headers={key.lower(): value for key, value in response_headers.items()},
            content=content,
            fetched_at=datetime.now(UTC),
            attempts=attempts,
            from_cache=from_cache,
            not_modified=not_modified,
            response_sha256=hashlib.sha256(content).hexdigest(),
        )


def _parse_retry_after(value: str) -> float | None:
    stripped = value.strip()
    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(stripped)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, (parsed - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None
