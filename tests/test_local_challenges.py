import subprocess
import tempfile
import unittest
from textwrap import dedent
from unittest.mock import patch

import src.experiment_utils.docker_ops as docker_ops
from src.config.constants import (
    LOCAL_CHALLENGES_COMPOSE_FILE,
    LOCAL_CHALLENGES_NETWORK_NAME,
    LOCAL_CHALLENGES_ROOT,
    get_local_challenge_container_name,
    get_session_challenge_name,
    get_session_network_name,
    get_session_subnet_from_id,
    normalize_session_id,
)
from src.utils.user_interface import discover_local_ctf_challenges


class LocalChallengesTests(unittest.TestCase):
    def test_container_names_match_vm_names(self) -> None:
        self.assertEqual(get_local_challenge_container_name("vm3"), "vm3")

    def test_network_name_is_generic(self) -> None:
        self.assertEqual(LOCAL_CHALLENGES_NETWORK_NAME, "target_net")

    def test_local_challenge_root_uses_new_pack_name(self) -> None:
        self.assertEqual(LOCAL_CHALLENGES_ROOT.name, "autopenbench_improved")

    def test_discover_local_ctf_challenges_reads_new_location(self) -> None:
        self.assertEqual(discover_local_ctf_challenges()[0], "vm0")
        self.assertEqual(discover_local_ctf_challenges()[-1], "vm10")

    def test_session_resource_names_are_normalized(self) -> None:
        session_id = " Review Session #6 "

        self.assertEqual(normalize_session_id(session_id), "review-session-6")
        self.assertEqual(get_session_network_name(session_id), "target_net_review-sessi")
        self.assertEqual(get_session_challenge_name("vm3", session_id), "vm3-review-sessi")

    def test_session_subnets_use_separate_private_range(self) -> None:
        subnet = get_session_subnet_from_id("parallel-run")

        self.assertRegex(subnet, r"^10\.\d+\.\d+\.0/24$")


class LocalChallengeDockerLifecycleTests(unittest.TestCase):
    @patch.object(docker_ops.subprocess, "run")
    def test_start_container_force_recreates_fresh_service_container(
        self,
        run_mock,
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        compose_content = dedent(
            """
            services:
              vm3:
                image: vm3
                networks:
                  target_net:
                    ipv4_address: 192.168.5.3
            networks:
              target_net:
                external: true
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yml") as compose_file:
            compose_file.write(compose_content)
            compose_file.flush()

            ip = docker_ops.start_container("vm3", compose_file=compose_file.name)

        self.assertEqual(ip, "192.168.5.3")
        run_mock.assert_called_once_with(
            [
                "docker",
                "compose",
                "-f",
                compose_file.name,
                "up",
                "-d",
                "--force-recreate",
                "vm3",
            ],
            check=True,
        )

    @patch.object(docker_ops.subprocess, "run")
    def test_stop_container_removes_service_container(
        self,
        run_mock,
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        result = docker_ops.stop_container("vm3")

        self.assertEqual(result, "vm3 removed")
        run_mock.assert_called_once_with(
            [
                "docker",
                "compose",
                "-f",
                str(LOCAL_CHALLENGES_COMPOSE_FILE),
                "rm",
                "-f",
                "-s",
                "vm3",
            ],
            check=True,
        )

    @patch.object(docker_ops.subprocess, "run")
    def test_start_challenge_container_standalone_uses_compose_runtime_settings_without_host_ports(
        self,
        run_mock,
    ) -> None:
        run_mock.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0),
            subprocess.CompletedProcess(args=[], returncode=0),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="10.210.33.21\n", stderr=""),
        ]
        compose_content = dedent(
            """
            services:
              vm3:
                image: vm3
                platform: linux/amd64
                tty: true
                init: true
                restart: unless-stopped
                command: bash -c "service ssh start && tail -f /dev/null"
                ports:
                  - 2222:22
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yml") as compose_file:
            compose_file.write(compose_content)
            compose_file.flush()

            ip = docker_ops.start_challenge_container_standalone(
                "vm3",
                "vm3-session",
                "target_net_session",
                compose_file=compose_file.name,
            )

        self.assertEqual(ip, "10.210.33.21")

        run_calls = run_mock.call_args_list
        self.assertEqual(run_calls[0].args[0], ["docker", "rm", "-f", "vm3-session"])
        docker_run_command = run_calls[1].args[0]
        self.assertIn("--platform", docker_run_command)
        self.assertIn("linux/amd64", docker_run_command)
        self.assertIn("--init", docker_run_command)
        self.assertIn("--restart", docker_run_command)
        self.assertIn("unless-stopped", docker_run_command)
        self.assertIn("-t", docker_run_command)
        self.assertIn("bash", docker_run_command)
        self.assertIn("-c", docker_run_command)
        self.assertNotIn("-p", docker_run_command)
