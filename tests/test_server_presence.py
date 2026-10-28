"""Stage 7b: server presence (auto-discovery) tests."""

import pytest

from backend import server_presence


def test_loopback_and_nonroutable_addresses_are_not_publishable():
    assert not server_presence._is_publishable("")
    assert not server_presence._is_publishable("127.0.0.1")
    assert not server_presence._is_publishable("169.254.10.2")
    assert not server_presence._is_publishable("192.168.56.1")  # VirtualBox
    assert not server_presence._is_publishable("192.168.137.1")  # ICS hotspot


def test_hotspot_and_lan_addresses_are_publishable():
    assert server_presence._is_publishable("10.88.155.17")
    assert server_presence._is_publishable("192.168.43.1")
    assert server_presence._is_publishable("172.20.10.1")


def test_pick_lan_ip_returns_a_reachable_address_or_empty():
    ip = server_presence.pick_lan_ip()
    if ip:
        assert server_presence._is_publishable(ip)
    # Empty is acceptable when no network interface is up at all.


def test_start_presence_disabled_without_service_account(monkeypatch):
    import asyncio

    from backend import auth as stage7_auth

    monkeypatch.setattr(stage7_auth, "is_service_account_configured", lambda: False)
    result = asyncio.run(server_presence.start_presence(8000))
    assert result is None
    assert server_presence._task is None
