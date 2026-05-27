from . import config


def read_public_address() -> str | None:
    path = config.PATHS["wallet_info"]
    try:
        for line in path.read_text().splitlines():
            if "**Address" in line:
                return line.split("`")[1]
    except (IndexError, FileNotFoundError, OSError):
        return None
    return None
