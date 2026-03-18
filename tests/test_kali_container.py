import inspect
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
import scripts.run_experiment as run_experiment
import src.experiment_utils.docker_ops as docker_ops
import src.experiment_utils.main_experiment_agent as experiment_agent
import src.utils.docker_utils as docker_utils
from src.config.constants import KALI_CONTAINER_NAME


class KaliContainerConfigTests(unittest.TestCase):
    def test_shared_kali_container_name_is_used_across_entrypoints(self) -> None:
        self.assertEqual(main.KALI_CONTAINER_NAME, KALI_CONTAINER_NAME)  # type: ignore[attr-defined]
        self.assertEqual(run_experiment.KALI_CONTAINER_NAME, KALI_CONTAINER_NAME)  # type: ignore[attr-defined]

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
    @patch.object(docker_ops.subprocess, "run")  # type: ignore[attr-defined]
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


class StopKaliContainerTests(unittest.TestCase):
    @patch.object(docker_ops.subprocess, "run")  # type: ignore[attr-defined]
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

    @patch.object(docker_ops.subprocess, "run")  # type: ignore[attr-defined]
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

    @patch.object(docker_ops.subprocess, "run")  # type: ignore[attr-defined]
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
