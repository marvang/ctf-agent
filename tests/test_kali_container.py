import inspect
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import src.experiment_utils.docker_ops as docker_ops
import src.experiment_utils.main_experiment_agent as experiment_agent
import src.utils.docker_utils as docker_utils
from src.config.constants import KALI_CONTAINER_NAME

DOCKER_OPS_SUBPROCESS: Any = docker_ops.subprocess  # type: ignore[attr-defined]


class KaliContainerConfigTests(unittest.TestCase):
    def test_session_runtime_kali_names_derive_from_shared_constant(self) -> None:
        from src.config.session_runtime import resolve_session_runtime

        runtime = resolve_session_runtime("test-shared")
        self.assertTrue(runtime.kali_container_name.startswith(KALI_CONTAINER_NAME))

    def test_helper_defaults_use_shared_kali_container_name(self) -> None:
        self.assertEqual(
            inspect.signature(docker_utils.connect_to_docker).parameters["kali_container_name"].default,
            KALI_CONTAINER_NAME,
        )
        self.assertEqual(
            inspect.signature(docker_ops.start_kali_container).parameters["container_name"].default,
            KALI_CONTAINER_NAME,
        )
        self.assertEqual(
            inspect.signature(docker_ops.stop_kali_container).parameters["container_name"].default,
            KALI_CONTAINER_NAME,
        )
        self.assertEqual(
            inspect.signature(experiment_agent.run_experiment_agent).parameters["kali_container_name"].default,
            KALI_CONTAINER_NAME,
        )

    def test_legacy_kali_container_name_is_removed_from_tracked_source(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        tracked_paths = [
            project_root / "main.py",
            project_root / "docker-compose.yml",
            project_root / "scripts" / "run_experiment.py",
        ]
        tracked_paths.extend((project_root / "src").rglob("*.py"))

        for path in tracked_paths:
            with self.subTest(path=path.relative_to(project_root)):
                self.assertNotIn("CHAP-kali-linux", path.read_text())

    def test_compose_service_keeps_local_build_source(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        compose_text = (project_root / "docker-compose.yml").read_text()

        self.assertIn(
            "  ctf-agent-kali:\n    build: .\n    image: ctf-agent-kali\n",
            compose_text,
        )


class StartKaliContainerTests(unittest.TestCase):
    @patch.object(DOCKER_OPS_SUBPROCESS, "run")
    def test_start_kali_container_uses_compose_up_with_shared_name(
        self,
        run_mock: MagicMock,
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        result = docker_ops.start_kali_container()

        self.assertTrue(result)
        run_mock.assert_called_once_with(
            ["docker", "compose", "up", "-d", KALI_CONTAINER_NAME],
            cwd=docker_ops._PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    @patch.object(DOCKER_OPS_SUBPROCESS, "run")
    def test_start_kali_container_standalone_uses_isolated_workspace_mount(
        self,
        run_mock: MagicMock,
    ) -> None:
        run_mock.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            compose_path = Path(temp_dir) / "docker-compose.yml"
            workspace_path = Path(temp_dir) / "ctf-workspaces" / "session-1"
            compose_path.write_text(
                """
services:
  ctf-agent-kali:
    image: ctf-agent-kali
    tty: true
    stdin_open: true
    working_dir: /ctf-workspace
    cap_add:
      - NET_ADMIN
    volumes:
      - ./ctf-workspace:/ctf-workspace
"""
            )

            result = docker_ops.start_kali_container_standalone(
                container_name="ctf-agent-kali-session",
                network_name="target_net_session",
                workspace_dir=str(workspace_path),
                compose_file=compose_path,
            )

            expected_mount = f"{workspace_path.resolve()}:/ctf-workspace"
            expected_vpn_mount = f"{(workspace_path / 'vpn').resolve()}:/ctf-workspace/vpn"

        self.assertTrue(result)
        docker_run_command = run_mock.call_args_list[1].args[0]
        self.assertIn("-i", docker_run_command)
        self.assertIn("-t", docker_run_command)
        self.assertIn("-w", docker_run_command)
        self.assertIn("/ctf-workspace", docker_run_command)
        self.assertIn("-v", docker_run_command)
        self.assertIn(expected_mount, docker_run_command)
        self.assertIn(expected_vpn_mount, docker_run_command)

    @patch.object(DOCKER_OPS_SUBPROCESS, "run")
    def test_start_kali_container_standalone_copies_shared_vpn_material_into_session_workspace(
        self,
        run_mock: MagicMock,
    ) -> None:
        run_mock.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            compose_path = Path(temp_dir) / "docker-compose.yml"
            workspace_path = Path(temp_dir) / "ctf-workspaces" / "session-1"
            shared_vpn_path = Path(temp_dir) / "shared-vpn"
            shared_vpn_path.mkdir()
            (shared_vpn_path / "vpn-connect.sh").write_text("#!/bin/sh\necho connected\n")
            compose_path.write_text(
                """
services:
  ctf-agent-kali:
    image: ctf-agent-kali
    tty: true
    stdin_open: true
    working_dir: /ctf-workspace
    volumes:
      - ./ctf-workspace:/ctf-workspace
"""
            )

            with patch.object(docker_ops, "SHARED_VPN_DIR", str(shared_vpn_path)):
                result = docker_ops.start_kali_container_standalone(
                    container_name="ctf-agent-kali-session",
                    network_name="target_net_session",
                    workspace_dir=str(workspace_path),
                    compose_file=compose_path,
                )

            copied_script = workspace_path / "vpn" / "vpn-connect.sh"
            self.assertTrue(result)
            self.assertTrue(copied_script.exists())
            self.assertEqual(copied_script.read_text(), "#!/bin/sh\necho connected\n")

    @patch.object(DOCKER_OPS_SUBPROCESS, "run")
    def test_start_kali_container_standalone_fails_cleanly_when_session_vpn_dir_cannot_be_reset(
        self,
        run_mock: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            compose_path = Path(temp_dir) / "docker-compose.yml"
            workspace_path = Path(temp_dir) / "ctf-workspaces" / "session-1"
            shared_vpn_path = Path(temp_dir) / "shared-vpn"
            shared_vpn_path.mkdir()
            (workspace_path / "vpn").mkdir(parents=True)
            compose_path.write_text(
                """
services:
  ctf-agent-kali:
    image: ctf-agent-kali
    tty: true
    stdin_open: true
    working_dir: /ctf-workspace
    volumes:
      - ./ctf-workspace:/ctf-workspace
"""
            )

            with (
                patch.object(docker_ops, "SHARED_VPN_DIR", str(shared_vpn_path)),
                patch.object(docker_ops, "_delete_workspace_item", return_value=False) as delete_mock,
            ):
                result = docker_ops.start_kali_container_standalone(
                    container_name="ctf-agent-kali-session",
                    network_name="target_net_session",
                    workspace_dir=str(workspace_path),
                    compose_file=compose_path,
                )

            self.assertFalse(result)
            delete_mock.assert_called_once_with(str(workspace_path / "vpn"), str(workspace_path))
            run_mock.assert_not_called()


class StopKaliContainerTests(unittest.TestCase):
    @patch.object(DOCKER_OPS_SUBPROCESS, "run")
    def test_stop_kali_container_force_removes_named_container(
        self,
        run_mock: MagicMock,
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="removed",
            stderr="",
        )

        result = docker_ops.stop_kali_container()

        self.assertTrue(result)
        run_mock.assert_called_once_with(
            ["docker", "rm", "-f", KALI_CONTAINER_NAME],
            capture_output=True,
            text=True,
        )

    @patch.object(DOCKER_OPS_SUBPROCESS, "run")
    def test_stop_kali_container_succeeds_when_container_is_absent(
        self,
        run_mock: MagicMock,
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="Error response from daemon: No such container: ctf-agent-kali",
        )

        result = docker_ops.stop_kali_container()

        self.assertTrue(result)

    @patch.object(DOCKER_OPS_SUBPROCESS, "run")
    def test_stop_kali_container_fails_on_other_docker_errors(
        self,
        run_mock: MagicMock,
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="permission denied",
        )

        result = docker_ops.stop_kali_container()

        self.assertFalse(result)
