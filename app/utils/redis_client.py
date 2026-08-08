import redis.asyncio as redis
import fakeredis.aioredis as fakeredis
import json
from typing import Any, Optional
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_pool: Optional[redis.ConnectionPool] = None
_fake_clients: dict[int, fakeredis.FakeRedis] = {}


async def get_redis() -> redis.Redis:
    global _fake_clients, _pool
    
    if settings.DEBUG:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            loop_id = 0
            
        if loop_id not in _fake_clients:
            logger.info("Using fakeredis for local development/testing")
            _fake_clients[loop_id] = fakeredis.FakeRedis(decode_responses=True)
        return _fake_clients[loop_id]
        
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
    return redis.Redis(connection_pool=_pool)


class RedisCache:
    def __init__(self, client: redis.Redis):
        self.client = client

    async def get(self, key: str) -> Optional[Any]:
        val = await self.client.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await self.client.set(key, serialized, ex=ttl)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def incr(self, key: str, ttl: int = 60) -> int:
        # Simple implementation for incr with expire
        val = await self.client.incr(key)
        await self.client.expire(key, ttl)
        return val

    async def set_interview_state(self, interview_id: str, state: dict) -> None:
        key = f"interview:state:{interview_id}"
        await self.set(key, state, ttl=7200)

    async def get_interview_state(self, interview_id: str) -> Optional[dict]:
        key = f"interview:state:{interview_id}"
        return await self.get(key)

    async def add_conversation_message(self, interview_id: str, message: dict) -> None:
        key = f"interview:messages:{interview_id}"
        await self.client.rpush(key, json.dumps(message))
        await self.client.expire(key, 7200)

    async def get_conversation_history(self, interview_id: str) -> list[dict]:
        key = f"interview:messages:{interview_id}"
        messages = await self.client.lrange(key, 0, -1)
        return [json.loads(m) for m in messages]

    async def update_last_audio_message(self, interview_id: str, new_text: str) -> None:
        key = f"interview:messages:{interview_id}"
        messages = await self.client.lrange(key, 0, -1)
        for i in range(len(messages) - 1, -1, -1):
            msg = json.loads(messages[i])
            if msg["role"] == "candidate" and msg["content"] == "(Audio recording submitted)":
                msg["content"] = new_text
                await self.client.lset(key, i, json.dumps(msg))
                break
