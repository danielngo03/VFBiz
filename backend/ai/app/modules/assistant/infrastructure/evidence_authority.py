from app.modules.assistant.domain import EvidenceReference, GraphControlState


class FailClosedEvidenceAuthority:
    """Reject every evidence reference until a real approval authority exists.

    Mirrors `FailClosedClaimSupportValidator` (inference module) and
    `FailClosedEntityRevalidator`: an unapproved-by-default answer to "is
    this evidence approved" is the safe response, not a stub — a
    customer-facing automaker chatbot must never let a citation through that
    nothing has actually verified against the active knowledge revision.
    """

    async def validate(
        self,
        *,
        references: tuple[EvidenceReference, ...],
        control: GraphControlState,
    ) -> bool:
        _ = references, control
        return False
