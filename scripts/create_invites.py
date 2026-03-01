"""Generate invite tokens for the forvm platform.

Usage:
    python -m scripts.create_invites --count 10 --label "beta-batch"
"""

import argparse
import asyncio

from forvm.database import async_session
from forvm.services.invite_service import create_invite_tokens


async def main(count: int, label: str | None) -> None:
    async with async_session() as db:
        tokens = await create_invite_tokens(db, count, label)
    print(f"Generated {len(tokens)} invite token(s):")
    for token in tokens:
        print(f"  {token}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate forvm invite tokens")
    parser.add_argument(
        "--count", type=int, default=1, help="Number of tokens to generate"
    )
    parser.add_argument(
        "--label", type=str, default=None, help="Optional label for the batch"
    )
    args = parser.parse_args()
    asyncio.run(main(args.count, args.label))
