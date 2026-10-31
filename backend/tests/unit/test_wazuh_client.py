"""Regression checks for the merged real/fake Wazuh client seam; no live calls."""
from unittest.mock import Mock, patch

import pytest

from actions.wazuh_client import (
    FakeWazuhClient, RealWazuhClient, Settings, UndoNotSupported,
    WazuhApiError, WazuhUnavailable,
)
from config import Config


def settings():
    return Settings('https://manager:55000', 'https://indexer:9200',
                    'user', 'secret', 'reader', 'secret', 'root-ca.pem', '003')


def client():
    with patch('actions.wazuh_client.ssl.create_default_context'):
        return RealWazuhClient(settings())


def test_config_passed_by_main_is_supported():
    config = Config(wazuh_api_url='https://manager:55000',
                    wazuh_indexer_url='https://indexer:9200',
                    wazuh_ca_cert='backend/certs/root-ca.pem')
    with patch('actions.wazuh_client.ssl.create_default_context'):
        real = RealWazuhClient(config)
    assert real.settings.agent_id == '003'
    assert '192.168.1.1' in real._never_block
    assert real.settings.ca_cert.endswith('backend\\certs\\root-ca.pem') or real.settings.ca_cert.endswith('backend/certs/root-ca.pem')


def test_transport_error_matches_approval_handler():
    assert issubclass(WazuhApiError, WazuhUnavailable)


def test_health_matches_backend_contract_and_rejects_empty_search():
    real = client()
    real._api = Mock(return_value={'data': {'affected_items': [
        {'id': '003', 'status': 'active'}]}})
    real._request = Mock(return_value={'hits': {'hits': []}, '_shards': {'failed': 0}})
    assert real.health() == {'api_ok': True, 'indexer_ok': True, 'agent_active': True}
    real._request.return_value = {}
    with pytest.raises(WazuhUnavailable):
        real.health()


def test_block_refuses_missing_safety_list_and_wrong_agent():
    real = client()
    real._api = Mock()
    with pytest.raises(WazuhUnavailable):
        real.block_ip('003', '192.168.1.57')
    with pytest.raises(WazuhUnavailable):
        real.block_ip('001', '192.168.1.57', never_block=set())
    with pytest.raises(WazuhUnavailable):
        real.block_ip('003', '192.168.1.1', never_block={'192.168.1.1'})
    real._api.assert_not_called()


def test_configured_list_is_used_by_two_argument_backend_call():
    real = client()
    real._never_block = {'192.168.1.1'}
    real._api = Mock(return_value={'data': {'total_affected_items': 1}})
    assert real.block_ip('003', '192.168.1.57')['accepted'] is True
    assert real._api.call_args.kwargs['params'] == {'agents_list': '003'}


def test_fake_and_undo_are_preserved():
    fake = FakeWazuhClient()
    fake.block_ip('003', '192.168.1.57')
    assert fake.calls == [('block_ip', '003', '192.168.1.57')]
    with pytest.raises(UndoNotSupported):
        client().unblock_ip('003', '192.168.1.57')
