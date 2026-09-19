"""Hai lop cache, khac nhau ve rui ro khi mat (docs/04-architecture.md muc 4.6):

  MetricResultCache   cachetools.TTLCache trong tien trinh, khoa theo query_id.
                       CHI la toi uu - mat cache khong bao gio sai ket qua, chi
                       cham hon mot chut (chay lai SQL).
  AnswerCache          Bang `ops.answer_cache` (Postgres, qua engine_trace) -
                       dung chung giua cac replica. Khoa la hash cua
                       (cau hoi da chuan hoa, prompt_version, metrics_version,
                       data_version) de tu vo hieu khi doi prompt/catalog/ETL.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cachetools import TTLCache
from sqlalchemy import Engine, text

from app.contracts import Fact
from app.data.engines import get_engine_trace


class MetricResultCache:
    """Cache Fact theo query_id, TTL ngan (mac dinh 300s - config.agent.metric_cache_ttl_s).

    KHONG cache khi `ttl_seconds <= 0` (dung trong profile test de dam bao
    ket qua luon tuoi, xem config/profiles/test.yaml)."""

    def __init__(self, maxsize: int = 256, ttl_seconds: float = 300.0) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: TTLCache[str, Fact] | None = (
            TTLCache(maxsize=maxsize, ttl=ttl_seconds) if ttl_seconds > 0 else None
        )

    def get(self, query_id: str) -> Fact | None:
        if self._cache is None:
            return None
        result: Fact | None = self._cache.get(query_id)
        return result

    def set(self, query_id: str, fact: Fact) -> None:
        if self._cache is not None:
            self._cache[query_id] = fact

    def clear(self) -> None:
        if self._cache is not None:
            self._cache.clear()


def make_cache_key(question_norm: str, prompt_version: str, metrics_version: str,
                    data_version: str) -> str:
    """Khoa cache cau tra loi - tu vo hieu khi BAT KY thanh phan nao trong bon
    thay doi (sua prompt, sua catalog, hoac ETL chay lai)."""
    payload = "|".join((question_norm, prompt_version, metrics_version, data_version))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CachedAnswer:
    answer_md: str
    evidence: dict[str, Any]
    trust_score: float | None
    hit_count: int


class AnswerCache:
    """Doc/ghi `ops.answer_cache` qua `engine_trace` (mkt_trace_rw - chi
    INSERT/SELECT/UPDATE vao schema ops, khong cham mart/raw)."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    @property
    def engine(self) -> Engine:
        return self._engine if self._engine is not None else get_engine_trace()

    def get(self, cache_key: str) -> CachedAnswer | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT answer_md, evidence, trust_score, hit_count "
                    "FROM ops.answer_cache "
                    "WHERE cache_key = :k AND expires_at > now()"
                ),
                {"k": cache_key},
            ).mappings().first()
            if row is None:
                return None
            conn.execute(
                text(
                    "UPDATE ops.answer_cache SET hit_count = hit_count + 1 "
                    "WHERE cache_key = :k"
                ),
                {"k": cache_key},
            )
            conn.commit()
        evidence = row["evidence"] if isinstance(row["evidence"], dict) else json.loads(row["evidence"])
        return CachedAnswer(
            answer_md=row["answer_md"], evidence=evidence,
            trust_score=float(row["trust_score"]) if row["trust_score"] is not None else None,
            hit_count=int(row["hit_count"]) + 1,
        )

    def set(
        self, cache_key: str, answer_md: str, evidence: dict[str, Any],
        trust_score: float | None, ttl_seconds: float,
    ) -> None:
        if ttl_seconds <= 0:
            return  # profile test: answer_cache_ttl_s = 0 -> khong cache
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO ops.answer_cache "
                    "(cache_key, answer_md, evidence, trust_score, expires_at) "
                    "VALUES (:k, :a, :e, :t, :exp) "
                    "ON CONFLICT (cache_key) DO UPDATE SET "
                    "answer_md = EXCLUDED.answer_md, evidence = EXCLUDED.evidence, "
                    "trust_score = EXCLUDED.trust_score, expires_at = EXCLUDED.expires_at, "
                    "created_at = now(), hit_count = 0"
                ),
                {
                    "k": cache_key, "a": answer_md, "e": json.dumps(evidence, default=str),
                    "t": trust_score, "exp": expires_at,
                },
            )
            conn.commit()

    def purge_expired(self) -> int:
        """Xoa cac dong da qua han. Tra ve so dong da xoa - goi tuy y (cron
        hoac luc khoi dong), khong bat buoc vi WHERE expires_at > now() o
        get() da tu bo qua dong het han."""
        with self.engine.connect() as conn:
            result = conn.execute(text("DELETE FROM ops.answer_cache WHERE expires_at <= now()"))
            conn.commit()
            return result.rowcount


__all__ = ["MetricResultCache", "AnswerCache", "CachedAnswer", "make_cache_key"]
