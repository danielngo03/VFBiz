from app.modules.assistant.domain import GlobalEntityReference, GraphControlState


class FailClosedEntityRevalidator:
    """Discard every carried-over entity until a real catalog check exists.

    `migrate_checkpoint_with_authority` only calls this when a graph/policy/
    knowledge revision upgrade happened mid-conversation (see
    `graph/migrations.py`); returning nothing forces the customer to
    reconfirm rather than silently trusting a stale reference against
    authority this adapter cannot actually check yet. Never fabricate a
    confirmation: an empty result is the safe, honest answer, not a stub.
    """

    async def revalidate(
        self,
        entities: tuple[GlobalEntityReference, ...],
        *,
        control: GraphControlState,
    ) -> tuple[GlobalEntityReference, ...]:
        _ = entities, control
        return ()
