"""Docker connection utilities"""
import docker
import docker.errors
from typing import Optional, Tuple


def connect_to_docker(container_name: str = "kali-linux") -> Tuple[Optional[object], Optional[object]]:
    """
    Connect to Docker and retrieve container

    Args:
        container_name: Name of the Docker container to connect to

    Returns:
        Tuple of (docker_client, container) if successful, (None, None) if failed
    """
    try:
        docker_client = docker.from_env()
        container = docker_client.containers.get(container_name)
        print("\n✅ Docker connected")
        return docker_client, container
    except docker.errors.NotFound:
        print(f"\n❌ Docker container '{container_name}' not found")
        print("💡 Run: docker compose up -d")
        return None, None
    except Exception as e:
        print(f"\n❌ Docker error: {e}")
        return None, None
