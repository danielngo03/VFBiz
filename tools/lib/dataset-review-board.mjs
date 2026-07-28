import { createHash } from "node:crypto";

const SEATS = new Map([
  ["quality-integrity", "dataset-quality-reviewer"],
  ["domain-experience", "golden-domain-reviewer"],
  ["risk-assurance", "risk-reviewer"],
]);

const DIGEST = /^sha256:[a-f0-9]{64}$/;
const RECOMMENDATIONS = new Set([
  "recommend",
  "reject",
  "needs-human-decision",
]);
const IDENTITY = /^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$/;

function canonicalBoardDigest(board, reviews, recommendation) {
  const canonical = {
    authorActorIds: [...(board.authorActorIds ?? [])].sort(),
    authorClaimIds: [...(board.authorClaimIds ?? [])].sort(),
    authorRunIds: [...(board.authorRunIds ?? [])].sort(),
    generatorActorIds: [...(board.generatorActorIds ?? [])].sort(),
    generatorClaimIds: [...(board.generatorClaimIds ?? [])].sort(),
    generatorRunIds: [...(board.generatorRunIds ?? [])].sort(),
    policyDigest: board.policyDigest,
    provenanceDigest: board.provenanceDigest,
    recommendation,
    reviews: [...reviews]
      .sort((left, right) => left.seat.localeCompare(right.seat))
      .map((review) => ({
        actorId: review.actorId,
        claimId: review.claimId,
        evidenceDigest: review.evidenceDigest,
        expiresAt: review.expiresAt,
        observedAt: review.observedAt,
        recommendation: review.recommendation,
        role: review.role,
        runId: review.runId,
        seat: review.seat,
      })),
    rubricDigest: board.rubricDigest,
    subjectDigest: board.subjectDigest,
  };
  return `sha256:${createHash("sha256").update(JSON.stringify(canonical)).digest("hex")}`;
}

function unique(values) {
  return new Set(values).size === values.length;
}

export function validateDatasetReviewBoard(board, { now = Date.now() } = {}) {
  const errors = [];
  const reviews = Array.isArray(board?.reviews) ? board.reviews : [];
  const expectedDigests = [
    ["subjectDigest", board?.subjectDigest],
    ["rubricDigest", board?.rubricDigest],
    ["policyDigest", board?.policyDigest],
    ["provenanceDigest", board?.provenanceDigest],
  ];

  for (const [name, digest] of expectedDigests)
    if (!DIGEST.test(digest ?? "")) errors.push(`${name} is not canonical`);

  if (reviews.length !== SEATS.size)
    errors.push(`expected ${SEATS.size} review seats`);

  const bySeat = new Map();
  for (const review of reviews) {
    if (!SEATS.has(review.seat)) {
      errors.push(`unknown review seat: ${review.seat ?? "missing"}`);
      continue;
    }
    if (bySeat.has(review.seat)) errors.push(`duplicate seat: ${review.seat}`);
    bySeat.set(review.seat, review);
    if (review.role !== SEATS.get(review.seat))
      errors.push(`${review.seat} uses an unauthorized role`);
    if (!RECOMMENDATIONS.has(review.recommendation))
      errors.push(`${review.seat} has an invalid recommendation`);
    for (const field of ["actorId", "runId", "claimId"])
      if (!IDENTITY.test(review[field] ?? ""))
        errors.push(`${review.seat} has a missing or invalid ${field}`);
    if (!DIGEST.test(review.evidenceDigest ?? ""))
      errors.push(`${review.seat} has no canonical evidenceDigest`);
    const observedAt = Date.parse(review.observedAt ?? "");
    const expiresAt = Date.parse(review.expiresAt ?? "");
    if (!Number.isFinite(observedAt) || !Number.isFinite(expiresAt))
      errors.push(`${review.seat} has invalid evidence timestamps`);
    else if (expiresAt <= observedAt)
      errors.push(`${review.seat} evidence is already expired`);
    else if (expiresAt <= now)
      errors.push(`${review.seat} evidence expired before validation`);
    for (const [name, digest] of expectedDigests)
      if (review[name] !== digest)
        errors.push(`${review.seat} has stale ${name}`);
    if (review.authority !== "evidence")
      errors.push(`${review.seat} attempted non-evidence authority`);
  }
  for (const seat of SEATS.keys())
    if (!bySeat.has(seat)) errors.push(`missing review seat: ${seat}`);

  for (const field of ["actorId", "runId", "claimId"])
    if (!unique(reviews.map((review) => review[field])))
      errors.push(`review seats do not have distinct ${field}`);

  for (const field of [
    "authorActorIds",
    "authorRunIds",
    "authorClaimIds",
    "generatorActorIds",
    "generatorRunIds",
    "generatorClaimIds",
  ]) {
    const identities = board?.[field];
    if (!Array.isArray(identities) || identities.length === 0)
      errors.push(`${field} is required for independence checks`);
    else if (
      identities.some((identity) => !IDENTITY.test(identity ?? "")) ||
      !unique(identities)
    )
      errors.push(`${field} contains an invalid or duplicate identity`);
  }

  const excluded = new Set([
    ...(board?.authorActorIds ?? []),
    ...(board?.generatorActorIds ?? []),
    ...(board?.authorRunIds ?? []),
    ...(board?.generatorRunIds ?? []),
    ...(board?.authorClaimIds ?? []),
    ...(board?.generatorClaimIds ?? []),
  ]);
  for (const review of reviews)
    for (const value of [review.actorId, review.runId, review.claimId])
      if (value && excluded.has(value))
        errors.push(
          `${review.seat} is not independent from the author/generator`,
        );

  const providers = reviews.map((review) => review.provider).filter(Boolean);
  if (
    new Set(providers).size === reviews.length &&
    (!unique(reviews.map((review) => review.actorId).filter(Boolean)) ||
      !unique(reviews.map((review) => review.runId).filter(Boolean)) ||
      !unique(reviews.map((review) => review.claimId).filter(Boolean)))
  )
    errors.push("provider diversity does not establish reviewer independence");

  if (board?.humanDecision !== undefined)
    errors.push("human approval must use a separate authority envelope");

  const recommendations = reviews.map((review) => review.recommendation);
  const recommendation = recommendations.includes("reject")
    ? "reject"
    : recommendations.length === SEATS.size &&
        recommendations.every((value) => value === "recommend")
      ? "recommend"
      : "needs-human-decision";

  if (recommendation !== "recommend")
    errors.push("review board did not reach a unanimous recommendation");

  return {
    valid: errors.length === 0,
    recommendation,
    boardDigest: canonicalBoardDigest(board, reviews, recommendation),
    errors,
  };
}

export const DATASET_REVIEW_BOARD_SEATS = Object.freeze(
  Object.fromEntries(SEATS),
);
