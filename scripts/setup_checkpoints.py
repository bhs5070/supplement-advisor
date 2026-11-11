"""Run once during deployment, before API and workers start."""

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from supplement_advisor.config import get_settings


async def setup() -> None:
    url = make_url(get_settings().database_url).set(drivername="postgresql")
    async with AsyncPostgresSaver.from_conn_string(
        url.render_as_string(hide_password=False)
    ) as saver:
        await saver.setup()


if __name__ == "__main__":
    asyncio.run(setup())
