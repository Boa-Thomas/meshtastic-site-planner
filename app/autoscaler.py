"""
Celery worker autoscaler.

Monitors Redis queue depth and scales Docker Compose worker services
up/down based on demand. Requires Docker socket access.

Environment variables:
    REDIS_HOST / REDIS_PORT: Redis connection (default: redis:6379)
    MIN_LIGHT_WORKERS: Minimum light worker replicas (default: 1)
    MAX_LIGHT_WORKERS: Maximum light worker replicas (default: 4)
    MIN_HEAVY_WORKERS: Minimum heavy worker replicas (default: 1)
    MAX_HEAVY_WORKERS: Maximum heavy worker replicas (default: 3)
    SCALE_DOWN_DELAY: Seconds of empty queue before scaling down (default: 120)
    CHECK_INTERVAL: Seconds between queue checks (default: 10)
    COMPOSE_PROJECT: Docker Compose project name for container filtering
"""

import logging
import os
import time

import docker
import redis

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("autoscaler")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

MIN_LIGHT = int(os.environ.get("MIN_LIGHT_WORKERS", "1"))
MAX_LIGHT = int(os.environ.get("MAX_LIGHT_WORKERS", "4"))
MIN_HEAVY = int(os.environ.get("MIN_HEAVY_WORKERS", "1"))
MAX_HEAVY = int(os.environ.get("MAX_HEAVY_WORKERS", "3"))

SCALE_DOWN_DELAY = int(os.environ.get("SCALE_DOWN_DELAY", "120"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "10"))
COMPOSE_PROJECT = os.environ.get("COMPOSE_PROJECT", "meshtastic-site-planner")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_queue_depths(r: redis.Redis) -> dict:
    """Return number of pending messages per Celery queue."""
    return {
        "default": r.llen("default") or 0,
        "heavy": r.llen("heavy") or 0,
    }


def count_service_containers(client: docker.DockerClient, service: str) -> int:
    """Count running containers for a Docker Compose service."""
    filters = {
        "label": [
            f"com.docker.compose.project={COMPOSE_PROJECT}",
            f"com.docker.compose.service={service}",
        ],
        "status": "running",
    }
    return len(client.containers.list(filters=filters))


def scale_service(client: docker.DockerClient, service: str, target: int) -> None:
    """
    Scale a Docker Compose service to *target* replicas by starting or
    stopping individual containers. This avoids shelling out to
    ``docker compose`` and works directly through the Docker API.

    When scaling UP, new containers are created from the same image/config
    as existing ones. When scaling DOWN, the newest containers are stopped
    and removed first.
    """
    current = count_service_containers(client, service)
    if target == current:
        return

    logger.info(f"Scaling {service}: {current} -> {target}")

    if target > current:
        # Find an existing container to clone config from
        filters = {
            "label": [
                f"com.docker.compose.project={COMPOSE_PROJECT}",
                f"com.docker.compose.service={service}",
            ],
        }
        existing = client.containers.list(filters=filters, limit=1)
        if not existing:
            logger.warning(f"No existing containers for {service}, cannot scale up")
            return

        ref = existing[0]
        image = ref.image.tags[0] if ref.image.tags else ref.image.id

        # Extract network name
        networks = list(ref.attrs.get("NetworkSettings", {}).get("Networks", {}).keys())
        network_name = networks[0] if networks else None

        for i in range(target - current):
            name = f"{COMPOSE_PROJECT}-{service}-scaled-{int(time.time())}-{i}"
            kwargs = {
                "image": image,
                "command": ref.attrs["Config"]["Cmd"],
                "environment": {
                    k: v for k, v in (
                        e.split("=", 1) for e in ref.attrs["Config"].get("Env", [])
                    )
                },
                "detach": True,
                "name": name,
                "labels": {
                    "com.docker.compose.project": COMPOSE_PROJECT,
                    "com.docker.compose.service": service,
                    "autoscaler.managed": "true",
                },
                "mem_limit": ref.attrs["HostConfig"].get("Memory") or None,
            }

            # Replicate volume mounts
            mounts = ref.attrs["HostConfig"].get("Mounts") or []
            binds = ref.attrs["HostConfig"].get("Binds") or []
            if binds:
                kwargs["volumes"] = binds

            if network_name:
                kwargs["network"] = network_name

            try:
                client.containers.run(**kwargs)
                logger.info(f"Started {name}")
            except Exception as e:
                logger.error(f"Failed to start {name}: {e}")

    else:
        # Scale down — remove autoscaler-managed containers first
        filters = {
            "label": [
                f"com.docker.compose.project={COMPOSE_PROJECT}",
                f"com.docker.compose.service={service}",
                "autoscaler.managed=true",
            ],
            "status": "running",
        }
        managed = client.containers.list(filters=filters)

        # Only remove autoscaler-managed containers (never touch Compose-created ones)
        to_remove = min(current - target, len(managed))
        targets = managed[:to_remove]

        for c in targets:
            try:
                logger.info(f"Stopping {c.name}")
                c.stop(timeout=30)
                c.remove()
            except Exception as e:
                logger.error(f"Failed to stop {c.name}: {e}")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    logger.info(
        f"Autoscaler started — light=[{MIN_LIGHT},{MAX_LIGHT}] "
        f"heavy=[{MIN_HEAVY},{MAX_HEAVY}] "
        f"check={CHECK_INTERVAL}s cooldown={SCALE_DOWN_DELAY}s"
    )

    r = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT), db=1)
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")

    idle_since: float | None = None

    while True:
        try:
            depths = get_queue_depths(r)
            total_pending = depths["default"] + depths["heavy"]

            current_light = count_service_containers(client, "worker")
            current_heavy = count_service_containers(client, "worker-heavy")

            if total_pending > 0:
                idle_since = None

                # Scale light workers based on default queue
                target_light = max(MIN_LIGHT, min(depths["default"] + 1, MAX_LIGHT))
                # Scale heavy workers based on heavy queue
                target_heavy = max(MIN_HEAVY, min(depths["heavy"] + 1, MAX_HEAVY))

                if target_light != current_light:
                    scale_service(client, "worker", target_light)
                if target_heavy != current_heavy:
                    scale_service(client, "worker-heavy", target_heavy)

            else:
                # Queue is empty — start cooldown timer
                if idle_since is None:
                    idle_since = time.time()

                idle_duration = time.time() - idle_since

                if idle_duration >= SCALE_DOWN_DELAY:
                    # Scale down to minimums
                    if current_light > MIN_LIGHT:
                        scale_service(client, "worker", MIN_LIGHT)
                    if current_heavy > MIN_HEAVY:
                        scale_service(client, "worker-heavy", MIN_HEAVY)

            if total_pending > 0 or (idle_since and time.time() - idle_since < SCALE_DOWN_DELAY + 10):
                logger.info(
                    f"queues={depths} workers=light:{current_light}/heavy:{current_heavy} "
                    f"idle={'%.0fs' % (time.time() - idle_since) if idle_since else 'no'}"
                )

        except redis.ConnectionError:
            logger.warning("Redis connection lost, retrying...")
        except Exception as e:
            logger.error(f"Autoscaler error: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
