"""T4.02: refused targets fall back to advice only."""
import pytest

from actions.targets import check_target

NEVER = [{"ip": "192.168.1.1", "label": "the clinic router"},
         {"ip": "192.168.1.5", "label": "the Wazuh server"},
         {"ip": "192.168.1.9", "label": "the ShieldMate laptop"}]


def test_good_ip_is_allowed():
    assert check_target("192.168.1.57", NEVER) == (True, None)


@pytest.mark.parametrize("ip,label", [("192.168.1.1", "the clinic router"),
                                      ("192.168.1.5", "the Wazuh server"),
                                      ("192.168.1.9", "the ShieldMate laptop")])
def test_never_block_list_is_refused_with_a_reason(ip, label):
    assert check_target(ip, NEVER) == (False, f"{ip} is {label}")


@pytest.mark.parametrize("bad", [None, "", "   ", "not-an-ip", "300.1.1.1", "192.168.1", "::1",
                                 "fe80::1", "192.168.1.57 ", "192.168.01.57"])
def test_invalid_empty_and_ipv6_are_refused(bad):
    ok, reason = check_target(bad, NEVER)
    assert not ok and reason
