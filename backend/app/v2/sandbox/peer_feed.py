"""Peer discussion controls scoped to the owned native OASIS subprocess."""


def install_peer_feed(platform_class):
    original_refresh = platform_class.refresh
    original_comment = platform_class.create_comment
    original_quote = platform_class.quote_post

    def single_participant(platform):
        platform.pl_utils._execute_db_command("SELECT COUNT(*) FROM user")
        return platform.db_cursor.fetchone()[0] <= 1

    async def refresh(platform, agent_id):
        if single_participant(platform):
            return await original_refresh(platform, agent_id)
        # The native relevance feed may show only one's own opening. This
        # bounded peer feed uses actual source rows and native comment expansion.
        platform.pl_utils._execute_db_command(
            "SELECT post_id, user_id, original_post_id, content, quote_content, "
            "created_at, num_likes, num_dislikes, num_shares FROM post "
            "WHERE user_id <> ? ORDER BY created_at DESC, post_id DESC LIMIT 20",
            (agent_id,),
        )
        posts = platform.pl_utils._add_comments_to_posts(platform.db_cursor.fetchall())
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
            kind = platform.pl_utils._get_post_type(post_id)
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
