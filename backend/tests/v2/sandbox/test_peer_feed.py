import sqlite3
from types import SimpleNamespace

import pytest

from app.v2.sandbox.peer_feed import install_peer_feed


def platform_type():
    class Platform:
        def __init__(self):
            self.db = sqlite3.connect(":memory:")
            self.db_cursor = self.db.cursor()
            self.db.execute("CREATE TABLE user (user_id INTEGER)")
            self.db.execute(
                "CREATE TABLE post (post_id INTEGER, user_id INTEGER, original_post_id INTEGER, content TEXT, quote_content TEXT, created_at INTEGER, num_likes INTEGER, num_dislikes INTEGER, num_shares INTEGER)"
            )
            self.db.executemany("INSERT INTO user VALUES (?)", [(0,), (1,)])
            self.db.executemany(
                "INSERT INTO post VALUES (?, ?, NULL, ?, NULL, 0, 0, 0, 0)",
                [(1, 0, "Own post"), (2, 1, "Peer post")],
            )
            self.pl_utils = SimpleNamespace(
                _execute_db_command=self.db_cursor.execute,
                _add_comments_to_posts=lambda rows: [
                    {"post_id": r[0], "user_id": r[1], "content": r[3]} for r in rows
                ],
                _record_trace=lambda *args: None,
                _get_post_type=lambda _: {"type": "original"},
            )
            self.sandbox_clock = SimpleNamespace(get_time_step=lambda: 1)

        async def refresh(self, agent_id):
            return {"success": True, "posts": [{"post_id": 1, "user_id": 0}]}

        async def create_comment(self, agent_id, message):
            return {"success": True, "target": message[0]}

        async def quote_post(self, agent_id, message):
            return {"success": True, "target": message[0]}

    return Platform


@pytest.mark.asyncio
async def test_feed_uses_real_peer_posts_and_does_not_rewrite_sources():
    cls = platform_type()
    install_peer_feed(cls)
    platform = cls()
    result = await platform.refresh(0)
    assert result["posts"] == [{"post_id": 2, "user_id": 1, "content": "Peer post"}]
    assert platform.db.execute(
        "SELECT content FROM post WHERE post_id=1"
    ).fetchone() == ("Own post",)


@pytest.mark.asyncio
async def test_self_reply_is_rejected_never_retargeted():
    cls = platform_type()
    install_peer_feed(cls)
    platform = cls()
    assert (await platform.create_comment(0, (1, "Reply")))["success"] is False
    assert await platform.create_comment(0, (2, "Reply")) == {
        "success": True,
        "target": 2,
    }
    assert (await platform.quote_post(0, (1, "Quote")))["success"] is False


@pytest.mark.asyncio
async def test_single_participant_preserves_native_feed():
    cls = platform_type()
    install_peer_feed(cls)
    platform = cls()
    platform.db.execute("DELETE FROM user WHERE user_id=1")
    assert (await platform.refresh(0))["posts"][0]["post_id"] == 1
