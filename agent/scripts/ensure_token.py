from __future__ import annotations

import secrets
import sys
from pathlib import Path


TOKEN_KEY = "PBXPULSE_AGENT_TOKEN"


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".env")
    if not env_path.exists():
        print(f"{env_path} does not exist. Create it from .env.example first.")
        return 1

    lines = env_path.read_text(encoding="utf-8").splitlines()
    token = secrets.token_urlsafe(32)
    found = False
    changed = False
    updated: list[str] = []

    for line in lines:
        if line.startswith(f"{TOKEN_KEY}="):
            found = True
            current = line.split("=", 1)[1].strip()
            if current:
                print(f"{TOKEN_KEY} is already set.")
                updated.append(line)
            else:
                print(f"Generated {TOKEN_KEY}.")
                updated.append(f"{TOKEN_KEY}={token}")
                changed = True
            continue
        updated.append(line)

    if not found:
        print(f"Generated {TOKEN_KEY}.")
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(f"{TOKEN_KEY}={token}")
        changed = True

    if changed:
        env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
