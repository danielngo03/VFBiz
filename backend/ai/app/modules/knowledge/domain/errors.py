class KnowledgeReleaseError(RuntimeError):
    """Base error for a fail-closed Knowledge Release decision."""


class InvalidKnowledgeTransition(KnowledgeReleaseError):
    pass


class SourceApprovalRejected(KnowledgeReleaseError):
    pass


class KnowledgeAuthorizationRejected(KnowledgeReleaseError):
    pass


class KnowledgeConcurrencyConflict(KnowledgeReleaseError):
    pass
