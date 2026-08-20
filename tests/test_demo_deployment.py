from pathlib import Path

import yaml


class ComposeLoader(yaml.SafeLoader):
    """Compose's !override merge tag is not part of plain YAML."""


ComposeLoader.add_constructor("!override", lambda loader, node: loader.construct_sequence(node))


def load_demo_service() -> dict:
    overlay = yaml.load(
        Path("docker-compose.demo.yml").read_text(encoding="utf-8"), Loader=ComposeLoader
    )
    return overlay["services"]


def test_demo_overlay_publishes_the_application_on_loopback_only() -> None:
    base = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    assert base["services"]["valuebridge"]["ports"] == ["8000:8000"]

    ports = load_demo_service()["valuebridge"]["ports"]

    assert ports == ["127.0.0.1:8090:8000"]


def test_demo_overlay_turns_on_demo_mode_with_the_host_env_file() -> None:
    valuebridge = load_demo_service()["valuebridge"]

    assert valuebridge["environment"]["VALUEBRIDGE_DEMO_MODE"] == "1"
    assert valuebridge["env_file"] == ["../.env"]


def test_demo_overlay_keeps_the_runtime_volume_and_mounts_the_policy_index() -> None:
    volumes = load_demo_service()["valuebridge"]["volumes"]

    assert "valuebridge-runtime:/app/runtime" in volumes
    assert "../policy_embeddings.json:/app/data/policy_embeddings.json:ro" in volumes


def test_caddy_terminates_tls_for_the_demo_hostname() -> None:
    caddy = load_demo_service()["caddy"]
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")

    assert caddy["ports"] == ["80:80", "443:443"]
    assert "./deploy/Caddyfile:/etc/caddy/Caddyfile:ro" in caddy["volumes"]
    assert "valuebridge.62-238-40-66.sslip.io" in caddyfile
    assert "reverse_proxy valuebridge:8000" in caddyfile


def test_certificate_storage_survives_the_nightly_volume_reset() -> None:
    reset = Path("deploy/valuebridge-demo-reset.service").read_text(encoding="utf-8")
    assert "down -v" in reset

    volumes = load_demo_service()["caddy"]["volumes"]
    caddy_data = [volume for volume in volumes if ":/data" in volume]

    assert caddy_data == ["../caddy-data:/data"]


def test_demo_overlay_stamps_the_build_and_redacts_the_question_audit() -> None:
    valuebridge = load_demo_service()["valuebridge"]

    assert valuebridge["build"]["args"]["BUILD_SHA"] == "${BUILD_SHA:-dev}"
    assert valuebridge["environment"]["VALUEBRIDGE_REDACT_QA_AUDIT"] == "1"


def test_the_image_carries_the_build_sha_it_was_built_with() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "ARG BUILD_SHA=dev" in dockerfile
    assert "ENV VALUEBRIDGE_BUILD_SHA=$BUILD_SHA" in dockerfile


def test_each_service_owns_its_runtime_volume() -> None:
    base = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    assert base["services"]["mockdesk"]["volumes"] == ["mockdesk-runtime:/app/runtime"]
    assert base["services"]["valuebridge"]["volumes"] == ["valuebridge-runtime:/app/runtime"]
    assert set(base["volumes"]) == {"mockdesk-runtime", "valuebridge-runtime"}


def test_the_demo_overlay_does_not_recouple_the_runtime_volumes() -> None:
    overlay = load_demo_service()

    assert "volumes" not in overlay["mockdesk"]
    assert not [
        volume
        for volume in overlay["valuebridge"]["volumes"]
        if volume.startswith("mockdesk-runtime")
    ]
