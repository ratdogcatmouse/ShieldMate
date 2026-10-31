"""ShieldMate Wazuh transport (Python 3.10+, standard library): talks to Wazuh and nothing else.

Reading alerts into ShieldMate lives in backend/ingest/wazuh.py (WazuhSource).
This is an integration module, NOT a replacement for backend.py or owner routes.
No alert automatically executes a block. See INTEGRATION_REVIEW.md.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import logging
import os
import re
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)


class WazuhUnavailable(RuntimeError):
    """Transport failure handled by the approval flow as wazuh_unavailable."""


class UndoNotSupported(Exception):
    """Undo is disabled until lab test T5.07 passes."""


class WazuhApiError(WazuhUnavailable):
    """Safe to map to wazuh_unavailable / HTTP 502; no upstream body/secrets."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class Settings:
    # Ask Ishaan for the manager hostname/IP (55000) and indexer hostname/IP (9200).
    # These are your lab's services, not API keys obtained from wazuh.com.
    api_url: str
    indexer_url: str
    api_user: str
    api_password: str = field(repr=False)
    indexer_user: str
    indexer_password: str = field(repr=False)
    ca_cert: str
    # Ishaan obtains the real ID from Dashboard -> Agents or GET /agents.
    agent_id: str
    agent_name: str = 'RECEPTION-PC'
    # Ishaan must verify this exact configured command at the lab gate.
    command: str = 'netsh3600'
    timeout: float = 5

    @classmethod
    def from_environment(cls) -> Settings:
        # Your app/config.py must load backend/.env first. os.environ does not
        # automatically read .env. Never send this configuration to the frontend.
        names = ('WAZUH_API_URL', 'WAZUH_INDEXER_URL', 'WAZUH_API_USER',
                 'WAZUH_API_PASSWORD', 'WAZUH_INDEXER_USER',
                 'WAZUH_INDEXER_PASSWORD', 'WAZUH_CA_CERT', 'WAZUH_AGENT_ID')
        values = {name: os.environ.get(name, '').strip() for name in names}
        if any(not value for value in values.values()):
            raise ValueError('Missing Wazuh settings: ' + ', '.join(
                name for name, value in values.items() if not value))
        return cls(
            values['WAZUH_API_URL'], values['WAZUH_INDEXER_URL'],
            values['WAZUH_API_USER'], os.environ['WAZUH_API_PASSWORD'],
            values['WAZUH_INDEXER_USER'], os.environ['WAZUH_INDEXER_PASSWORD'],
            values['WAZUH_CA_CERT'], values['WAZUH_AGENT_ID'],
            os.environ.get('WAZUH_AGENT_NAME', 'RECEPTION-PC'),
            os.environ.get('WAZUH_AR_COMMAND', 'netsh3600'),
            float(os.environ.get('WAZUH_TIMEOUT_SECONDS', '5')))


class RealWazuhClient:
    def __init__(self, settings: Settings | None = None):
        # main.build_context passes Config, whose fields use wazuh_* names.
        # Read the registered agent and safety list from the same seed as the DB.
        self._never_block: set[str] | None = None
        if settings is not None and not isinstance(settings, Settings):
            config = settings
            seed = json.loads(config.seed_path.read_text(encoding='utf-8'))
            device = next((d for d in seed['devices']
                           if d['agent_name'] == 'RECEPTION-PC'), None)
            if not device or not device.get('wazuh_agent_id'):
                raise ValueError('Set RECEPTION-PC wazuh_agent_id in the seed before live mode')
            self._never_block = {str(ipaddress.IPv4Address(item['ip']))
                                 for item in seed['clinic']['never_block']}
            if not config.wazuh_ca_cert:
                raise ValueError('WAZUH_CA_CERT is required for live mode')
            ca = Path(config.wazuh_ca_cert)
            if not ca.is_absolute():
                ca = config.seed_path.resolve().parents[2] / ca
            settings = Settings(
                config.wazuh_api_url, config.wazuh_indexer_url,
                config.wazuh_api_user, config.wazuh_api_password,
                config.wazuh_indexer_user, config.wazuh_indexer_password,
                str(ca), str(device['wazuh_agent_id']), device['agent_name'],
                config.wazuh_ar_command, config.wazuh_timeout_seconds)
        self.settings = settings or Settings.from_environment()
        for url in (self.settings.api_url, self.settings.indexer_url):
            parsed = urllib.parse.urlsplit(url)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment
                    or parsed.path not in ('', '/')):
                raise ValueError('Wazuh URLs must be HTTPS origins without credentials')
        if not re.fullmatch(r'\d{3,}', self.settings.agent_id) or self.settings.agent_id == '000':
            raise ValueError('Use the registered Windows agent ID, never manager 000')
        if self.settings.timeout <= 0:
            raise ValueError('Timeout must be positive')
        # Obtain root-ca.pem from Ishaan's Wazuh installation. Use a hostname/IP
        # present in the server certificate. Do not disable certificate checking.
        self._tls = ssl.create_default_context(cafile=self.settings.ca_cert)
        # Python 3.13+ adds VERIFY_X509_STRICT, which rejects Wazuh's self-made root CA
        # (no keyUsage extension). Chain and hostname checks stay fully on.
        self._tls.verify_flags &= ~ssl.VERIFY_X509_STRICT
        self._token: str | None = None
        self._auth_lock = threading.RLock()

    @staticmethod
    def _basic(user: str, password: str) -> str:
        return 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()

    def _request(self, base: str, method: str, path: str, *,
                 authorization: str, params: dict | None = None,
                 body: dict | None = None, raw: bool = False) -> Any:
        url = base.rstrip('/') + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        headers = {'Authorization': authorization, 'Accept': 'application/json'}
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        # Reject redirects so Basic/Bearer credentials never follow another origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self._tls), NoRedirect())
        try:
            with opener.open(request, timeout=self.settings.timeout) as response:
                # Bound memory use even if an upstream service misbehaves.
                maximum = 8 * 1024 * 1024
                content = response.read(maximum + 1)
                if len(content) > maximum:
                    raise WazuhApiError('Wazuh response exceeded the size limit')
                text = content.decode('utf-8')
            return text.strip() if raw else json.loads(text)
        except urllib.error.HTTPError as exc:
            # Keep the status for token refresh, but do not expose raw error bodies.
            error = WazuhApiError(f'Wazuh returned HTTP {exc.code}')
            error.status_code = exc.code
            exc.close()
            raise error from None
        except (OSError, ValueError) as exc:
            raise WazuhApiError('Wazuh connection, TLS, timeout or response failure') from None

    def _api(self, method: str, path: str, **kwargs) -> dict:
        with self._auth_lock:
            for attempt in range(2):
                if self._token is None:
                    token = self._request(
                        self.settings.api_url, 'POST', '/security/user/authenticate',
                        params={'raw': 'true'}, raw=True,
                        authorization=self._basic(self.settings.api_user,
                                                  self.settings.api_password))
                    if not isinstance(token, str) or not token:
                        raise WazuhApiError('Wazuh authentication returned no token')
                    self._token = token
                try:
                    result = self._request(self.settings.api_url, method, path,
                                           authorization='Bearer ' + self._token, **kwargs)
                except WazuhApiError as exc:
                    if getattr(exc, 'status_code', None) == 401 and attempt == 0:
                        self._token = None
                        continue  # Retry SAME operation once; do not retry a 403.
                    raise
                self._check_result(result)
                return result
        raise WazuhApiError('Wazuh authentication failed')

    @staticmethod
    def _check_result(result: dict) -> None:
        if not isinstance(result, dict):
            raise WazuhApiError('Unexpected Wazuh response')
        data = result.get('data', {})
        if not isinstance(data, dict) or result.get('error', 0) or data.get('total_failed_items', 0) or data.get('failed_items'):
            raise WazuhApiError('Wazuh rejected the operation')

    def _indexer(self, method: str, path: str, **kwargs) -> dict:
        result = self._request(
            self.settings.indexer_url, method, path,
            authorization=self._basic(self.settings.indexer_user,
                                      self.settings.indexer_password), **kwargs)
        if (not isinstance(result, dict) or result.get('error') or result.get('timed_out')
                or not isinstance(result.get('_shards', {}), dict)
                or result.get('_shards', {}).get('failed', 0)):
            raise WazuhApiError('Indexer returned an incomplete/failed search')
        if method != 'DELETE' and (
                not isinstance(result.get('hits'), dict)
                or not isinstance(result['hits'].get('hits'), list)):
            raise WazuhApiError('Indexer response is missing search hits')
        return result

    def alert_hits(self, start: datetime, end: datetime):
        """Scroll a fixed snapshot: process ALL pages, including equal timestamps."""
        scroll_id = None
        try:
            page = self._indexer('POST', '/wazuh-alerts-4.x-*/_search',
                params={'scroll': '1m'}, body={
                    'size': 100, 'sort': ['_doc'],
                    'query': {'bool': {'filter': [
                        {'range': {'timestamp': {'gte': iso(start), 'lte': iso(end)}}},
                        {'terms': {'agent.name': [self.settings.agent_name]}}
                    ]}}})
            while True:
                scroll_id = page.get('_scroll_id', scroll_id)
                hits = page.get('hits', {}).get('hits')
                if not isinstance(hits, list):
                    raise WazuhApiError('Indexer response is missing hits')
                if not hits:
                    return
                if not scroll_id:
                    raise WazuhApiError('Indexer did not return a scroll cursor')
                yield from hits
                page = self._indexer('POST', '/_search/scroll',
                                     body={'scroll': '1m', 'scroll_id': scroll_id})
        finally:
            if scroll_id:
                try:
                    self._indexer('DELETE', '/_search/scroll', body={'scroll_id': [scroll_id]})
                except WazuhApiError:
                    log.warning('Could not clear Wazuh search cursor; it will expire')

    def health(self) -> dict:
        # Schedule every 30 s, independently from ingestion. No cluster-admin API.
        result = self._api('GET', '/agents', params={'agents_list': self.settings.agent_id})
        items = result.get('data', {}).get('affected_items', [])
        active = any(str(item.get('id')) == self.settings.agent_id
                     and item.get('status') == 'active' for item in items)
        self._indexer('POST', '/wazuh-alerts-4.x-*/_search', body={
            'size': 1, 'query': {'term': {'agent.name': self.settings.agent_name}}})
        # Match Config.Context/contract.WazuhHealth, including the fake seam.
        return {'api_ok': True, 'indexer_ok': True, 'agent_active': active}

    def block_ip(self, agent_id: str, ip: str, *, never_block: set[str] | None = None) -> dict:
        """INTERNAL ONLY: call after a persisted approval/standing-rule decision.

        Return means command accepted by Wazuh, not proven Windows enforcement.
        Never expose this method directly as an unauthenticated HTTP endpoint.
        """
        protected = never_block if never_block is not None else self._never_block
        if protected is None:
            raise WazuhUnavailable('A never-block list is required before dispatch')
        try:
            target = validate_target(ip, protected)
        except ValueError:
            raise WazuhUnavailable('Refused unsafe block target') from None
        if agent_id != self.settings.agent_id:
            raise WazuhUnavailable('Refused: agent is outside the configured lab scope')
        # Final spec uses configured netsh3600, NOT !netsh.exe or an arbitrary
        # command from an alert/request. Ishaan configures timeout and dummy rule.
        if not re.fullmatch(r'netsh\d+', self.settings.command):
            raise WazuhUnavailable('Expected a lab-verified configured netsh timeout command')
        body = {'command': self.settings.command, 'arguments': [],
                'alert': {'data': {'srcip': target}}}
        result = self._api('PUT', '/active-response',
                           params={'agents_list': agent_id}, body=body)
        if result.get('data', {}).get('total_affected_items') != 1:
            raise WazuhApiError('Wazuh did not acknowledge exactly one target agent')
        # Store only sanitized response metadata in actions.wazuh_response.
        return {'accepted': True, 'confirmed': False, 'request': body}

    def unblock_ip(self, agent_id: str, ip: str) -> dict:
        """Unblock support is intentionally disabled until lab test T5.07 proves it."""
        raise UndoNotSupported('No verified undo command is configured')


def validate_target(ip: str, never_block: set[str]) -> str:
    try:
        target = str(ipaddress.IPv4Address(ip))
    except ipaddress.AddressValueError:
        raise ValueError('Refused: target must be a valid IPv4 address') from None
    protected = {str(ipaddress.IPv4Address(value)) for value in never_block}
    # Private LAN attacker IPs ARE allowed by the spec; do not use is_global.
    if target in protected:
        raise ValueError('Refused: address is on the never-block list')
    return target


def __getattr__(name: str):
    """``normalise`` and ``WazuhPoller`` moved to ingest/wazuh.py; old imports keep working.

    Resolved lazily because ingest.wazuh imports this module (a top-level import would be circular).
    """
    if name in ('normalise', 'WazuhPoller'):
        from ingest import wazuh
        return getattr(wazuh, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


class WazuhClient(Protocol):
    def block_ip(self, agent_id: str, ip: str) -> dict: ...      # raises WazuhUnavailable
    def unblock_ip(self, agent_id: str, ip: str) -> dict: ...    # raises UndoNotSupported
    def health(self) -> dict: ...                                 # {api_ok, indexer_ok, agent_active}


class FakeWazuhClient:
    """Records every call in ``.calls`` and sends nothing. Used by every test except Gate T5."""

    def __init__(self, fail_with: Exception | None = None):
        self.calls: list[tuple[str, str, str]] = []
        self.fail_with = fail_with          # tests set this to simulate a Wazuh outage

    def block_ip(self, agent_id: str, ip: str) -> dict:
        self.calls.append(("block_ip", agent_id, ip))
        if self.fail_with:
            raise self.fail_with
        return {"fake": True, "agent_id": agent_id, "ip": ip}

    def unblock_ip(self, agent_id: str, ip: str) -> dict:
        self.calls.append(("unblock_ip", agent_id, ip))
        if self.fail_with:
            raise self.fail_with
        return {"fake": True, "agent_id": agent_id, "ip": ip}

    def health(self) -> dict:
        return {"api_ok": None, "indexer_ok": None, "agent_active": None}
