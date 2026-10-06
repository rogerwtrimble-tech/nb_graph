"""Unit tests: no database or NetBox needed."""
import pytest
from fastapi import HTTPException

from app.graph import parse_id
from app.provision import SERVICES, eligible_services


def iface(name, itype, parent=None):
    return {'name': name, 'type': {'value': itype}, 'parent': parent}


@pytest.mark.parametrize('name,itype,expected', [
    ('wan0', 'virtual', ['hsi']),
    ('voip1', 'virtual', ['voip']),
    ('eth1', '1000base-t', ['ethernet']),
    ('pon0', 'gpon', []),
    ('eth1', 'virtual', []),
])
def test_eligible_services(name, itype, expected):
    assert eligible_services(iface(name, itype)) == expected


def test_subinterfaces_are_never_eligible():
    assert eligible_services(iface('eth1.101', 'virtual', parent={'id': 1})) == []


def test_service_catalogue():
    assert set(SERVICES) == {'hsi', 'voip', 'ethernet'}
    assert SERVICES['hsi']['vid'] == 100 and SERVICES['voip']['vid'] == 200


def test_parse_id():
    assert parse_id('device:42') == ('device', 42)
    with pytest.raises(HTTPException):
        parse_id('device')
    with pytest.raises(HTTPException):
        parse_id('device:abc')
