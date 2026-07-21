import asyncio
import csv
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, select

# --------- Config ---------
DATABASE_URL = "sqlite+aiosqlite:///./webapp/.data/localdata.db"
OUTPUT_CSV = "./webapp/.data/evaluation_dump.csv"
INDEX_JSONL = "./webapp/static/synthetic_outputs/index.jsonl"
Base = declarative_base()


class EvaluationSyntheticCases(Base):
    __tablename__ = "synthetic_cases"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    graph_id = Column(String)
    element_id = Column(String)
    Q1 = Column(String)
    Q2 = Column(String)
    Q3 = Column(String)
    Q4 = Column(String)
    Q5 = Column(String)


def load_index_jsonl(jsonl_path: str) -> dict:
    """Load JSONL index into a dictionary keyed by uid."""
    index = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            uid = entry.get("uid")
            if uid:
                index[uid] = entry
    return index


async def dump():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    index_data = load_index_jsonl(INDEX_JSONL)

    async with async_session() as session:
        result = await session.execute(select(EvaluationSyntheticCases))
        rows = result.scalars().all()

        with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "username", "graph_id", "element_id",
                "Q1", "Q2", "Q3", "Q4", "Q5",
                "html_file", "is_control", "model", "text_file"
            ])

            for row in rows:
                index_entry = index_data.get(row.element_id, {})
                print(f"[{row.username}] {row.graph_id} | {row.element_id}")
                print(f"  Q1={row.Q1} Q2={row.Q2} Q3={row.Q3} Q4={row.Q4} Q5={row.Q5}")
                print(f"  + from index: {index_entry}")
                print("-" * 60)

                writer.writerow([
                    row.username,
                    row.graph_id,
                    row.element_id,
                    row.Q1,
                    row.Q2,
                    row.Q3,
                    row.Q4,
                    row.Q5,
                    index_entry.get("html_file"),
                    index_entry.get("is_control"),
                    index_entry.get("model"),
                    index_entry.get("text_file"),
                ])


if __name__ == "__main__":
    asyncio.run(dump())
