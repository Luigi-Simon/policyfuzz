"""Peer discussion controls scoped to the owned native OASIS subprocess."""


def install_peer_feed(platform_class):
    original_comment = platform_class.create_comment
    original_quote = platform_class.quote_post

    def single_participant(platform):
        platform.pl_utils._execute_db_command("SELECT COUNT(*) FROM user")
        return platform.db_cursor.fetchone()[0] <= 1

    async def refresh(platform, agent_id):
        operator = "=" if single_participant(platform) else "<>"
        # Read complete source rows ourselves. Some OASIS versions leave
        # num_reports unbound when their comment expander sees a quote first,
        # killing the platform dispatcher while agents wait on its channel.
        platform.pl_utils._execute_db_command(
            "SELECT post_id, user_id, original_post_id, content, quote_content, "
            "created_at, num_likes, num_dislikes, num_shares, num_reports FROM post "
            f"WHERE user_id {operator} ? ORDER BY created_at, post_id",
            (agent_id,),
        )
        rows = platform.db_cursor.fetchall()
        if rows:
            # Participant/round rotation removes the common newest-first
            # ordering bias without changing content or directing sentiment.
            # Rotate BEFORE limiting so older openings remain discoverable.
            step = max(1, int(platform.sandbox_clock.get_time_step()))
            offset = (int(agent_id) + 1 + (step - 1) * max(1, len(rows) // 2)) % len(
                rows
            )
            # A short, rotating view bounds shared attention: showing everyone
            # all 20 openings still lets one appealing post dominate the round.
            # This changes exposure only, not the participant's view or reply.
            rows = (rows[offset:] + rows[:offset])[:5]
        keys = (
            "post_id",
            "user_id",
            "original_post_id",
            "content",
            "quote_content",
            "created_at",
            "num_likes",
            "num_dislikes",
            "num_shares",
            "num_reports",
        )
        posts = []
        for row in rows:
            post = dict(zip(keys, row, strict=True))
            platform.pl_utils._execute_db_command(
                "SELECT comment_id, post_id, user_id, content, created_at, "
                "num_likes, num_dislikes FROM comment WHERE post_id=? "
                "ORDER BY created_at, comment_id",
                (post["post_id"],),
            )
            post["comments"] = [
                dict(
                    zip(
                        (
                            "comment_id",
                            "post_id",
                            "user_id",
                            "content",
                            "created_at",
                            "num_likes",
                            "num_dislikes",
                        ),
                        comment,
                        strict=True,
                    )
                )
                for comment in platform.db_cursor.fetchall()
            ]
            # Keep source IDs and distinguish each author's words.
            if post["original_post_id"] is not None:
                post["content"] = (
                    f"User {post['user_id']} quoted post {post['original_post_id']}. "
                    f"Quote: {post['quote_content'] or ''} Original: {post['content']}"
                )
            posts.append(post)
        platform.pl_utils._record_trace(
            agent_id,
            "refresh",
            {"posts": posts},
            platform.sandbox_clock.get_time_step(),
        )
        return {"success": True, "posts": posts}

    def own_target(platform, agent_id, post_id, *, comment=False):
        if single_participant(platform):
            return False
        if comment:
            kind = platform.pl_utils._get_post_type(post_id) or {}
            if kind.get("type") == "repost":
                post_id = kind["root_post_id"]
        platform.pl_utils._execute_db_command(
            "SELECT user_id FROM post WHERE post_id=?", (post_id,)
        )
        row = platform.db_cursor.fetchone()
        return row is not None and row[0] == agent_id

    async def create_comment(platform, agent_id, message):
        if own_target(platform, agent_id, message[0], comment=True):
            return {
                "success": False,
                "error": "Choose an observed post by another participant; self-replies are unavailable.",
            }
        return await original_comment(platform, agent_id, message)

    async def quote_post(platform, agent_id, message):
        if own_target(platform, agent_id, message[0]):
            return {
                "success": False,
                "error": "Choose an observed post by another participant; self-quotes are unavailable.",
            }
        return await original_quote(platform, agent_id, message)

    platform_class.refresh = refresh
    platform_class.create_comment = create_comment
    platform_class.quote_post = quote_post
