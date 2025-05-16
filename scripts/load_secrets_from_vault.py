import os
from pathlib import Path
from typing import Any

from hvac import Client


def get_vault_client() -> Client:
    token: str | None = os.getenv("VAULT_TOKEN")
    if not token:
        msg: str = "VAULT_TOKEN not set"
        raise RuntimeError(msg)
    return Client(
        url="https://127.0.0.1:8200",
        token=token,
        verify="/etc/ssl/certs/ca-certificates.crt",
    )


def get_secrets() -> dict[str, Any]:
    client: Client = get_vault_client()
    secrets: dict[str, Any] = {}

    paths: dict[str, str] = {
        "spotify": "grimwaves-api/dev/streaming/spotify",
    }

    for path in paths.values():
        data: dict[str, Any] = client.secrets.kv.v2.read_secret_version(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            mount_point="secret",
            path=path,
            raise_on_deleted_version=True,
        )["data"]["data"]
        for k, v in data.items():  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if path.endswith("spotify"):
                match k.lower():  # pyright: ignore[reportUnknownMemberType]
                    case "client_id":
                        secrets["GRIMWAVES_SPOTIFY_CLIENT_ID"] = v
                    case "client_secret":
                        secrets["GRIMWAVES_SPOTIFY_CLIENT_SECRET"] = v
                    case _:  # pyright: ignore[reportUnknownVariableType]
                        pass
            else:
                secrets[f"GRIMWAVES_{k.upper()}"] = v  # pyright: ignore[reportUnknownMemberType]

    return secrets


def write_env_file(path: str = ".env") -> None:
    secrets: dict[str, Any] = get_secrets()
    with Path(path).open("w") as f:
        for k, v in secrets.items():
            _ = f.write(f"{k}={v}\n")
    print(f"✅ Wrote {len(secrets)} secrets to {path}")


if __name__ == "__main__":
    write_env_file()
