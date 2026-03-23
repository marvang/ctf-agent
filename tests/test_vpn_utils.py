import unittest
from unittest.mock import Mock

from src.utils.docker_exec import get_container_ips
from src.utils.vpn import connect_vpn, disconnect_vpn, select_vpn_connect_script


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

    def test_disconnect_vpn_uses_environment_disconnect_helper_for_htb(self) -> None:
        container = Mock()
        container.exec_run.return_value = (0, b"VPN disconnected")

        disconnected = disconnect_vpn(container, environment="htb", connect_script="connect-htb.sh")

        self.assertTrue(disconnected)
        container.exec_run.assert_called_once_with(
            ["bash", "-c", "cd /ctf-workspace/vpn/htb && ./disconnect-htb.sh"]
        )


class SelectVpnScriptTests(unittest.TestCase):
    def test_select_vpn_script_accepts_explicit_match(self) -> None:
        script = select_vpn_connect_script(["alpha.sh", "beta.sh"], "beta.sh")

        self.assertEqual(script, "beta.sh")

    def test_select_vpn_script_ignores_disconnect_helpers(self) -> None:
        script = select_vpn_connect_script(["connect-htb.sh", "disconnect-htb.sh"])

        self.assertEqual(script, "connect-htb.sh")

    def test_select_vpn_script_returns_only_script_when_unambiguous(self) -> None:
        script = select_vpn_connect_script(["vpn-connect.sh"])

        self.assertEqual(script, "vpn-connect.sh")

    def test_select_vpn_script_raises_when_multiple_scripts_exist(self) -> None:
        with self.assertRaisesRegex(ValueError, "Specify --vpn-script explicitly"):
            select_vpn_connect_script(["alpha.sh", "beta.sh"])


if __name__ == "__main__":
    unittest.main()
