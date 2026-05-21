"""SlimTorq simulator service entrypoint — async shell that ``await``s
the server built by :mod:`server`. Run with ``python -m src.main``.
"""

import asyncio

from src.server import run


async def main() -> None:
    await run()


if __name__ == "__main__":
    asyncio.run(main())
