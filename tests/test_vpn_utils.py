import unittest
from unittest.mock import Mock

from src.utils.docker_exec import get_container_ips
from src.utils.vpn import connect_vpn


class ContainerIpTests(unittest.TestCase):
    def test_get_container_ips_ignores_tun0_stderr_output(self) -> None:
        container = Mock()
        container.exec_run.side_effect = [
            (0, b"2: eth0    inet 172.20.0.5/16 brd 172.20.255.255 scope global eth0"),
            (0, b'Device "tun0" does not exist.\n'),
        ]

        ips = get_container_ips(container, use_vpn=True)

        self.assertEqual(ips, {"eth0": "172.20.0.5"})


class ConnectVpnTests(unittest.TestCase):
    def test_connect_vpn_succeeds_when_script_exits_zero(self) -> None:
        container = Mock()
        container.exec_run.return_value = (0, b"VPN script completed")

        connected = connect_vpn(container, environment="private")

        self.assertTrue(connected)

    def test_connect_vpn_fails_when_script_exits_nonzero(self) -> None:
        container = Mock()
        container.exec_run.return_value = (1, b"VPN script failed")

        connected = connect_vpn(container, environment="private")

        self.assertFalse(connected)


if __name__ == "__main__":
    unittest.main()
