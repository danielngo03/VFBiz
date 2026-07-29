#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import yaml from "js-yaml";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contractRegistry = await loadContractRegistry();
const datasetManifestV3ContractId =
  "https://vfbiz.example/contracts/ai/dataset-release-manifest/v3";
const datasetManifestV4ContractId =
  "https://vfbiz.example/contracts/ai/dataset-release-manifest/v4";
const contractPath = (contractId) => {
  const entry = contractRegistry.byId.get(contractId);
  if (!entry) throw new Error(`AI contract is not registered: ${contractId}`);
  return entry.canonicalPath;
};
const schemaPaths = [
  "contracts/json-schema/citation.schema.json",
  contractPath(datasetManifestV4ContractId),
  contractPath("https://vfbiz.example/contracts/ai/release-manifest/v3"),
  contractPath(
    "https://vfbiz.example/contracts/ai/conversation-turn-protocol/v1",
  ),
  contractPath(
    "https://vfbiz.example/contracts/ai/conversation-public-event/v1",
  ),
  contractPath("https://vfbiz.example/contracts/ai/execution-assertion/v1"),
];
const conversationEventSchemaPath = contractPath(
  "https://vfbiz.example/contracts/ai/conversation-public-event/v1",
);
const publicClientPath = "packages/api-client/src/generated.ts";
const conversationCandidatePath =
  "contracts/openapi/customer-conversation-candidate-v1.yaml";
const requiredConversationOperationIds = [
  "createConversationSession",
  "getConversationSession",
  "closeConversationSession",
  "enqueueConversationMessage",
  "listConversationMessages",
  "streamConversationEvents",
  "cancelConversationTurn",
  "requestConversationHandoff",
];
const ajv = new Ajv2020({ strict: true, allErrors: true });
addFormats(ajv);
const schemas = new Map();

for (const relativePath of schemaPaths) {
  const schema = JSON.parse(
    await readFile(path.join(root, relativePath), "utf8"),
  );
  ajv.compile(schema);
  schemas.set(relativePath, schema);
}

const datasetVectors = JSON.parse(
  await readFile(
    path.join(root, "contracts/ai/test-vectors/dataset-contracts.json"),
    "utf8",
  ),
);
const datasetAjv = new Ajv2020({ strict: false, allErrors: true });
addFormats(datasetAjv);
const datasetValidators = new Map();
for (const vector of datasetVectors) {
  const registryEntry = resolveContractReference(
    contractRegistry,
    vector.schema,
    vector.id,
  );
  const relativeSchema = registryEntry.canonicalPath;
  let validate = datasetValidators.get(registryEntry.contractId);
  if (!validate) {
    const schema =
      schemas.get(relativeSchema) ??
      JSON.parse(await readFile(path.join(root, relativeSchema), "utf8"));
    const schemaValidator = registryEntry.contractId.includes("/evaluation/")
      ? ajv
      : datasetAjv;
    validate =
      schemaValidator.getSchema(schema.$id) ?? schemaValidator.compile(schema);
    datasetValidators.set(registryEntry.contractId, validate);
  }
  const schemaValid = validate(vector.value);
  const semanticErrors =
    [datasetManifestV3ContractId, datasetManifestV4ContractId].includes(
      registryEntry.contractId,
    )
      ? datasetManifestSemanticErrors(vector.value)
      : registryEntry.contractId ===
          "https://vfbiz.example/contracts/ai/golden-case/v2"
        ? goldenCaseSemanticErrors(vector.value)
        : registryEntry.contractId ===
            "https://vfbiz.example/contracts/ai/evaluation/grader-calibration/v1"
          ? graderCalibrationSemanticErrors(vector.value)
          : registryEntry.contractId ===
              "https://vfbiz.example/contracts/ai/evaluation/run-result/v1"
            ? evaluationRunResultSemanticErrors(vector.value)
            : registryEntry.contractId ===
                "https://vfbiz.example/contracts/ai/evaluation/evidence-bundle/v1"
              ? evaluationEvidenceBundleSemanticErrors(vector.value)
              : [];
  const observed = schemaValid && semanticErrors.length === 0;
  if (observed !== vector.valid) {
    throw new Error(
      `Dataset contract vector ${vector.id} expected valid=${vector.valid}: ${ajv.errorsText(validate.errors)} ${semanticErrors.join("; ")}`,
    );
  }
}

const conversationEventSchema = schemas.get(conversationEventSchemaPath);
assertGeneratorFriendlyEventSchema(conversationEventSchema);
const publicClient = await readFile(path.join(root, publicClientPath), "utf8");
const conversationCandidate = yaml.load(
  await readFile(path.join(root, conversationCandidatePath), "utf8"),
);
assertCandidateOperationIds(
  conversationCandidate,
  requiredConversationOperationIds,
);
assertReleasedClientExcludesOperationIds(
  publicClient,
  requiredConversationOperationIds,
);

if (process.argv.includes("--self-test")) runNegativeSelfTest();

console.log(
  `Runtime contracts verified: ${contractRegistry.byId.size} registered AI contracts, ${schemaPaths.length} runtime schemas, ${datasetVectors.length} dataset vectors, ${requiredConversationOperationIds.length} isolated candidate operations; active dataset manifest ${datasetManifestV4ContractId}`,
);

async function loadContractRegistry() {
  const registryPath = path.join(root, "contracts/ai/index.json");
  const registry = JSON.parse(await readFile(registryPath, "utf8"));
  if (!Array.isArray(registry.contracts) || registry.contracts.length === 0)
    throw new Error("AI contract registry must contain contracts");
  const byId = new Map();
  const byPath = new Map();
  const byLegacyPath = new Map();
  const byBasename = new Map();
  const contractsBoundary = await realpath(path.join(root, "contracts/ai"));
  for (const entry of registry.contracts) {
    if (
      typeof entry.contractId !== "string" ||
      typeof entry.canonicalPath !== "string" ||
      !Array.isArray(entry.legacyPaths)
    )
      throw new Error("AI contract registry entry is malformed");
    if (byId.has(entry.contractId))
      throw new Error(`Duplicate AI contract ID: ${entry.contractId}`);
    if (byPath.has(entry.canonicalPath))
      throw new Error(
        `Duplicate canonical AI contract path: ${entry.canonicalPath}`,
      );
    if (!entry.canonicalPath.startsWith("contracts/ai/"))
      throw new Error(
        `Canonical AI contract escapes its boundary: ${entry.canonicalPath}`,
      );
    const canonicalAbsolute = path.join(root, entry.canonicalPath);
    const schema = JSON.parse(await readFile(canonicalAbsolute, "utf8"));
    if (schema.$id !== entry.contractId)
      throw new Error(
        `AI contract ID mismatch for ${entry.canonicalPath}: ${schema.$id}`,
      );
    const canonicalRealPath = await realpath(canonicalAbsolute);
    if (
      canonicalRealPath !== contractsBoundary &&
      !canonicalRealPath.startsWith(`${contractsBoundary}${path.sep}`)
    ) {
      throw new Error(
        `Canonical AI contract resolves outside contracts/ai: ${entry.canonicalPath}`,
      );
    }
    registerContractBasename(byBasename, entry.canonicalPath, entry);
    for (const legacyPath of entry.legacyPaths) {
      if (byLegacyPath.has(legacyPath)) {
        throw new Error(`Duplicate legacy AI contract path: ${legacyPath}`);
      }
      const legacyRealPath = await realpath(path.join(root, legacyPath));
      if (legacyRealPath !== canonicalRealPath)
        throw new Error(
          `Legacy AI contract path does not resolve to its canonical schema: ${legacyPath}`,
        );
      registerContractBasename(byBasename, legacyPath, entry);
      byLegacyPath.set(legacyPath, entry);
    }
    byId.set(entry.contractId, entry);
    byPath.set(entry.canonicalPath, entry);
  }
  return { ...registry, byId, byPath, byLegacyPath, byBasename };
}

function registerContractBasename(index, contractPath, entry) {
  const basename = path.basename(contractPath);
  const previous = index.get(basename);
  if (previous && previous.contractId !== entry.contractId) {
    throw new Error(`Ambiguous AI contract basename: ${basename}`);
  }
  index.set(basename, entry);
}

function resolveContractReference(registry, reference, vectorId) {
  const exactEntry =
    registry.byId.get(reference) ??
    registry.byPath.get(reference) ??
    registry.byLegacyPath.get(reference);
  const entry =
    exactEntry ??
    (path.basename(reference) === reference
      ? registry.byBasename.get(reference)
      : undefined);
  if (!entry) {
    throw new Error(
      `Dataset contract vector ${vectorId} references an unregistered schema: ${reference}`,
    );
  }
  return entry;
}

function assertCandidateOperationIds(candidate, requiredOperationIds) {
  const operationIds = collectOpenApiOperationIds(candidate);
  const missing = requiredOperationIds.filter(
    (operationId) => !operationIds.has(operationId),
  );
  if (missing.length > 0) {
    throw new Error(
      `Customer Conversation candidate is missing required operation IDs: ${missing.join(", ")}`,
    );
  }
}

function assertReleasedClientExcludesOperationIds(
  source,
  forbiddenOperationIds,
) {
  const operations = extractOperationsInterface(source);
  const leaked = forbiddenOperationIds.filter((operationId) =>
    new RegExp(`^\\s{4}${escapeRegExp(operationId)}:\\s*\\{\\s*$`, "m").test(
      operations,
    ),
  );
  if (leaked.length > 0) {
    throw new Error(
      `Released public API client contains unreleased Conversation operation IDs: ${leaked.join(", ")}`,
    );
  }
}

function collectOpenApiOperationIds(candidate) {
  if (!isRecord(candidate) || !isRecord(candidate.paths)) {
    throw new Error(
      "Customer Conversation candidate does not declare an OpenAPI paths object",
    );
  }
  const operationIds = new Set();
  const methods = new Set([
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "trace",
  ]);
  for (const pathItem of Object.values(candidate.paths)) {
    if (!isRecord(pathItem)) continue;
    for (const [method, operation] of Object.entries(pathItem)) {
      if (
        methods.has(method.toLowerCase()) &&
        isRecord(operation) &&
        typeof operation.operationId === "string"
      ) {
        operationIds.add(operation.operationId);
      }
    }
  }
  return operationIds;
}

function assertGeneratorFriendlyEventSchema(schema) {
  if (!isRecord(schema) || !isRecord(schema.$defs)) {
    throw new Error("Conversation event schema does not declare $defs");
  }
  if (containsKeyword(schema, "allOf")) {
    throw new Error(
      "Conversation event schema must not compose event envelopes with allOf",
    );
  }
  const variantNames = [
    "MessageAcceptedEvent",
    "TurnProcessingEvent",
    "TurnCompletedEvent",
    "HandoffRequestedEvent",
    "TurnCancelledEvent",
    "RetrievalStartedFrame",
    "ToolStartedFrame",
    "ReconnectRequiredFrame",
  ];
  const eventTypes = new Set();
  for (const variantName of variantNames) {
    const variant = schema.$defs[variantName];
    if (
      !isRecord(variant) ||
      !Array.isArray(variant.required) ||
      !variant.required.includes("type") ||
      !variant.required.includes("data") ||
      !isRecord(variant.properties) ||
      !isRecord(variant.properties.type) ||
      typeof variant.properties.type.const !== "string" ||
      !isRecord(variant.properties.data)
    ) {
      throw new Error(
        `Conversation event variant ${variantName} must require typed type and data fields`,
      );
    }
    if (eventTypes.has(variant.properties.type.const)) {
      throw new Error(
        `Conversation event type is duplicated: ${variant.properties.type.const}`,
      );
    }
    eventTypes.add(variant.properties.type.const);
  }
}

function containsKeyword(value, keyword) {
  if (Array.isArray(value)) {
    return value.some((candidate) => containsKeyword(candidate, keyword));
  }
  if (!isRecord(value)) return false;
  return (
    Object.hasOwn(value, keyword) ||
    Object.values(value).some((candidate) =>
      containsKeyword(candidate, keyword),
    )
  );
}

function datasetManifestSemanticErrors(manifest) {
  if (!isRecord(manifest)) return ["manifest must be an object"];
  const errors = [];
  const isV4 = isRecord(manifest.split_lock);
  const counts = isRecord(manifest.record_counts) ? manifest.record_counts : {};
  const candidate = counts.candidate;
  const accepted = counts.accepted;
  const rejected = counts.rejected;
  if ([candidate, accepted, rejected].every(Number.isInteger)) {
    const decided = accepted + rejected;
    if (
      ["decision-ready", "released"].includes(manifest.status) &&
      candidate !== decided
    ) {
      errors.push(
        "decision-ready or released candidate count must equal accepted plus rejected",
      );
    } else if (
      !["decision-ready", "released"].includes(manifest.status) &&
      decided > candidate
    ) {
      errors.push("accepted plus rejected cannot exceed candidate count");
    }
  }
  const artifactRecords = Array.isArray(manifest.artifacts)
    ? manifest.artifacts.reduce(
        (total, item) =>
          total +
          (isRecord(item) && Number.isInteger(item.records) ? item.records : 0),
        0,
      )
    : 0;
  const artifactHashes = [];
  const artifactDigests = new Set();
  const artifactAddresses = new Set();
  for (const artifact of Array.isArray(manifest.artifacts)
    ? manifest.artifacts.filter(isRecord)
    : []) {
    if (typeof artifact.sha256 !== "string") continue;
    artifactHashes.push(artifact.sha256);
    artifactDigests.add(`sha256:${artifact.sha256}`);
    const expectedAddress = `sha256/${artifact.sha256.slice(0, 2)}/${artifact.sha256}`;
    if (isV4 && artifact.content_address !== expectedAddress) {
      errors.push("artifact content address must match sha256");
    }
    if (
      isV4 &&
      artifactAddresses.has(artifact.content_address) ||
      (isV4 && artifactHashes.slice(0, -1).includes(artifact.sha256))
    ) {
      errors.push("artifact digests and content addresses must be unique");
    }
    artifactAddresses.add(artifact.content_address);
  }
  const expectedContentHash = createHash("sha256")
    .update(artifactHashes.join(""))
    .digest("hex");
  if (
    isV4 &&
    artifactHashes.length > 0 &&
    manifest.content_hash !== expectedContentHash
  ) {
    errors.push("content_hash must bind the ordered artifact digests");
  }
  const split = isRecord(manifest.split_lock)
    ? manifest.split_lock
    : manifest.split;
  const partitions =
    isRecord(split) && isRecord(split.partitions)
      ? split.partitions
      : {};
  const partitionRecords = Object.values(partitions).reduce(
    (total, value) => total + (Number.isInteger(value) ? value : 0),
    0,
  );
  const expectedRecords = ["decision-ready", "released"].includes(
    manifest.status,
  )
    ? accepted
    : candidate;
  if (Number.isInteger(expectedRecords)) {
    if (artifactRecords !== expectedRecords) {
      errors.push("artifact record total does not match manifest state");
    }
    if (partitionRecords !== expectedRecords) {
      errors.push("partition total does not match manifest state");
    }
  }
  const actors = Array.isArray(manifest.approval_evidence)
    ? manifest.approval_evidence
        .filter(isRecord)
        .map((item) => item.actor_ref)
        .filter((value) => typeof value === "string")
    : [];
  if (actors.length !== new Set(actors).size) {
    errors.push("approval decisions must use distinct human actors");
  }
  const decisionIds = Array.isArray(manifest.approval_evidence)
    ? manifest.approval_evidence
        .filter(isRecord)
        .map((item) => item.decision_id)
        .filter((value) => typeof value === "string")
    : [];
  if (isV4 && decisionIds.length !== new Set(decisionIds).size) {
    errors.push("approval decision ids must be unique");
  }
  if (Array.isArray(manifest.quality_evidence)) {
    const verifiedArtifactDigests = new Set();
    for (const evidence of manifest.quality_evidence.filter(isRecord)) {
      if (!artifactDigests.has(evidence.artifact_digest)) {
        errors.push("quality evidence references artifact outside manifest");
      }
      if (
        isV4 &&
        ["decision-ready", "released"].includes(manifest.status)
      ) {
        let current = true;
        if (evidence.state !== "verified") {
          current = false;
          errors.push(
            "decision-ready or released quality evidence must be verified",
          );
        }
        if (evidence.revoked_at !== null && evidence.revoked_at !== undefined) {
          current = false;
          errors.push(
            "decision-ready or released quality evidence is revoked",
          );
        }
        const expiry = Date.parse(evidence.expires_at);
        if (!Number.isFinite(expiry) || expiry <= Date.now()) {
          current = false;
          errors.push(
            "decision-ready or released quality evidence is expired",
          );
        }
        if (current) verifiedArtifactDigests.add(evidence.artifact_digest);
      }
    }
    if (
      isV4 &&
      ["decision-ready", "released"].includes(manifest.status) &&
      [...artifactDigests].some(
        (digest) => !verifiedArtifactDigests.has(digest),
      )
    ) {
      errors.push("every released artifact requires current verified evidence");
    }
  }
  if (
    Array.isArray(manifest.source_ids) &&
    isRecord(manifest.provenance) &&
    Array.isArray(manifest.provenance.sources)
  ) {
    const sourceIds = new Set(manifest.source_ids);
    const provenanceIds = new Set(
      manifest.provenance.sources
        .filter(isRecord)
        .map((item) => item.source_id),
    );
    if (
      sourceIds.size !== provenanceIds.size ||
      [...sourceIds].some((sourceId) => !provenanceIds.has(sourceId))
    ) {
      errors.push("provenance sources must match source_ids exactly");
    }
    if (
      isV4 &&
      ["decision-ready", "released"].includes(manifest.status) &&
      manifest.provenance.sources
        .filter(isRecord)
        .some((source) =>
          ["candidate-input-unresolved", "unresolved", "unknown"].includes(
            source.source_revision,
          ),
        )
    ) {
      errors.push("decision-ready or released provenance must be resolved");
    }
  }
  return errors;
}

function goldenCaseSemanticErrors(goldenCase) {
  if (!isRecord(goldenCase)) return ["golden case must be an object"];
  const evidenceIds =
    isRecord(goldenCase.knowledge_snapshot) &&
    Array.isArray(goldenCase.knowledge_snapshot.evidence_ids)
      ? new Set(goldenCase.knowledge_snapshot.evidence_ids)
      : new Set();
  const expected = isRecord(goldenCase.expected) ? goldenCase.expected : {};
  const claims = Array.isArray(expected.required_claims)
    ? expected.required_claims
    : [];
  const errors = [];
  for (const claim of claims) {
    if (!isRecord(claim) || !Array.isArray(claim.citation_evidence_ids)) {
      continue;
    }
    const unknown = claim.citation_evidence_ids.filter(
      (evidenceId) => !evidenceIds.has(evidenceId),
    );
    if (unknown.length > 0) {
      errors.push(
        `claim ${claim.claim_id ?? "unknown"} cites evidence outside snapshot: ${unknown.sort().join(", ")}`,
      );
    }
  }
  return errors;
}

function graderCalibrationSemanticErrors(calibration) {
  if (!isRecord(calibration)) return ["calibration must be an object"];
  const errors = [];
  const matrix = calibration.confusion_matrix;
  if (isRecord(matrix)) {
    const values = [
      matrix.true_positive,
      matrix.true_negative,
      matrix.false_positive,
      matrix.false_negative,
    ];
    if (values.every(Number.isInteger)) {
      const observedSampleSize = values.reduce(
        (total, value) => total + value,
        0,
      );
      if (observedSampleSize !== calibration.sample_size) {
        errors.push("confusion matrix total must equal sample_size");
      }
      const [truePositive, trueNegative, falsePositive, falseNegative] = values;
      const positiveDenominator = truePositive + falseNegative;
      const negativeDenominator = trueNegative + falsePositive;
      if (positiveDenominator === 0 || negativeDenominator === 0) {
        errors.push("calibration must contain positive and negative examples");
        return errors;
      }
      const positiveRecall = truePositive / positiveDenominator;
      const negativeRecall = trueNegative / negativeDenominator;
      const expectedBalancedAccuracy = (positiveRecall + negativeRecall) / 2;
      const f1Denominator = 2 * truePositive + falsePositive + falseNegative;
      if (f1Denominator === 0) {
        errors.push("calibration must contain positive predictions or labels");
        return errors;
      }
      const expectedF1 = (2 * truePositive) / f1Denominator;
      if (
        !approximatelyEqual(
          calibration.balanced_accuracy,
          expectedBalancedAccuracy,
        )
      ) {
        errors.push("balanced_accuracy must match confusion matrix");
      }
      if (!approximatelyEqual(calibration.f1, expectedF1)) {
        errors.push("f1 must match confusion matrix");
      }
    }
  }
  if (
    Date.parse(calibration.expires_at) <= Date.parse(calibration.calibrated_at)
  ) {
    errors.push("calibration expiry must be after calibrated_at");
  }
  const slices = Array.isArray(calibration.slice_metrics)
    ? calibration.slice_metrics
        .filter(isRecord)
        .map((slice) => slice.slice)
        .filter((slice) => typeof slice === "string")
    : [];
  if (slices.length !== new Set(slices).size) {
    errors.push("calibration slices must be unique");
  }
  return errors;
}

function evaluationRunResultSemanticErrors(result) {
  if (!isRecord(result)) return ["evaluation run result must be an object"];
  const errors = [];
  const counts = result.case_counts;
  if (isRecord(counts)) {
    const terminalCounts = [
      counts.valid,
      counts.invalid,
      counts.failed,
      counts.cancelled,
    ];
    if (
      terminalCounts.every(Number.isInteger) &&
      terminalCounts.reduce((total, value) => total + value, 0) !==
        counts.evaluated
    ) {
      errors.push("terminal case counts must equal evaluated");
    }
    if (
      result.state === "decision_ready" &&
      (counts.evaluated !== counts.expected ||
        counts.invalid !== 0 ||
        counts.failed !== 0 ||
        counts.cancelled !== 0)
    ) {
      errors.push("decision_ready requires a complete case set");
    }
  }
  if (Date.parse(result.completed_at) < Date.parse(result.started_at)) {
    errors.push("completed_at must not precede started_at");
  }
  return errors;
}

function evaluationEvidenceBundleSemanticErrors(bundle) {
  if (!isRecord(bundle)) return ["evidence bundle must be an object"];
  const requiredGraders = Array.isArray(bundle.required_grader_revisions)
    ? bundle.required_grader_revisions
    : [];
  const calibrationGraders = Array.isArray(bundle.grader_calibrations)
    ? bundle.grader_calibrations
        .filter(isRecord)
        .map((entry) => entry.grader_revision)
    : [];
  if (
    bundle.recommendation === "recommend" &&
    (requiredGraders.length !== calibrationGraders.length ||
      requiredGraders.some((grader) => !calibrationGraders.includes(grader)) ||
      calibrationGraders.length !== new Set(calibrationGraders).size)
  ) {
    return ["recommendation requires one calibration per required grader"];
  }
  return [];
}

function approximatelyEqual(observed, expected) {
  return (
    typeof observed === "number" &&
    Number.isFinite(observed) &&
    Math.abs(observed - expected) <= 1e-6
  );
}

function extractOperationsInterface(source) {
  const marker = "export interface operations {";
  const start = source.indexOf(marker);
  if (start < 0) {
    throw new Error(
      "Generated public API client does not declare the operations interface",
    );
  }
  return source.slice(start + marker.length);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function runNegativeSelfTest() {
  const candidate = {
    paths: Object.fromEntries(
      requiredConversationOperationIds.map((operationId, index) => [
        `/synthetic/${index}`,
        { get: { operationId } },
      ]),
    ),
  };
  const releasedClient = "export interface operations {\n}\n";
  assertCandidateOperationIds(candidate, requiredConversationOperationIds);
  assertReleasedClientExcludesOperationIds(
    releasedClient,
    requiredConversationOperationIds,
  );
  assertGeneratorFriendlyEventSchema(conversationEventSchema);
  assertThrows(
    () =>
      assertCandidateOperationIds(
        {
          paths: {
            ...candidate.paths,
            "/synthetic/0": { get: { operationId: "unrelatedOperation" } },
          },
        },
        requiredConversationOperationIds,
      ),
    "missing candidate operation ID",
  );
  assertThrows(
    () =>
      assertReleasedClientExcludesOperationIds(
        "export interface operations {\n    createConversationSession: {\n    };\n}\n",
        requiredConversationOperationIds,
      ),
    "released operation leak",
  );
  assertThrows(
    () =>
      assertGeneratorFriendlyEventSchema({
        ...conversationEventSchema,
        allOf: [],
      }),
    "allOf event envelope",
  );
  assertThrows(
    () =>
      assertGeneratorFriendlyEventSchema({
        ...conversationEventSchema,
        $defs: {
          ...conversationEventSchema.$defs,
          MessageAcceptedEvent: {
            ...conversationEventSchema.$defs.MessageAcceptedEvent,
            required:
              conversationEventSchema.$defs.MessageAcceptedEvent.required.filter(
                (field) => field !== "data",
              ),
          },
        },
      }),
    "event variant without required data",
  );
  assertThrows(
    () =>
      ajv.compile({
        $schema: "https://json-schema.org/draft/2020-12/schema",
        type: "object",
        vfbizUnknownKeyword: true,
      }),
    "strict schema keyword",
  );
  assertThrows(
    () =>
      resolveContractReference(
        contractRegistry,
        "contracts/ai/evaluation/unknown.schema.json",
        "negative-unknown-contract",
      ),
    "unknown canonical contract reference",
  );
  assertThrows(
    () =>
      resolveContractReference(
        contractRegistry,
        "untrusted/path/run-request.schema.json",
        "negative-basename-path-confusion",
      ),
    "path-qualified basename confusion",
  );
  assertThrows(() => {
    const byBasename = new Map();
    registerContractBasename(byBasename, "one/shared.schema.json", {
      contractId: "contract:one",
    });
    registerContractBasename(byBasename, "two/shared.schema.json", {
      contractId: "contract:two",
    });
  }, "ambiguous canonical contract basename");
  const canonicalRelease = datasetVectors.find(
    ({ id }) =>
      id ===
      "released-v4-manifest-binds-classification-lineage-and-quality-evidence",
  )?.value;
  if (!canonicalRelease) {
    throw new Error("Dataset v4 authority self-test fixture is missing");
  }
  const duplicateActorRelease = structuredClone(canonicalRelease);
  duplicateActorRelease.approval_evidence[1].actor_ref =
    duplicateActorRelease.approval_evidence[0].actor_ref;
  if (
    !datasetManifestSemanticErrors(duplicateActorRelease).some((error) =>
      error.includes("distinct human actors"),
    )
  ) {
    throw new Error(
      "Runtime contract checker self-test failed: duplicate dataset approver",
    );
  }
  const unboundQualityRelease = structuredClone(canonicalRelease);
  unboundQualityRelease.quality_evidence[0].artifact_digest =
    `sha256:${"7".repeat(64)}`;
  if (
    !datasetManifestSemanticErrors(unboundQualityRelease).some((error) =>
      error.includes("artifact outside manifest"),
    )
  ) {
    throw new Error(
      "Runtime contract checker self-test failed: unbound quality evidence",
    );
  }
  const semanticMutations = [
    {
      label: "artifact address binding",
      expected: "content address",
      mutate: (value) => {
        value.artifacts[0].content_address = `sha256/${"7".repeat(2)}/${"7".repeat(64)}`;
      },
    },
    {
      label: "manifest content binding",
      expected: "content_hash",
      mutate: (value) => {
        value.content_hash = "9".repeat(64);
      },
    },
    {
      label: "quality evidence expiry",
      expected: "expired",
      mutate: (value) => {
        value.quality_evidence[0].expires_at = "2020-01-01T00:00:00Z";
      },
    },
    {
      label: "quality evidence coverage",
      expected: "every released artifact",
      mutate: (value) => {
        value.artifacts.push({
          ...structuredClone(value.artifacts[0]),
          content_address: `sha256/bb/${"b".repeat(64)}`,
          sha256: "b".repeat(64),
          records: 0,
        });
        value.content_hash = createHash("sha256")
          .update(`${"a".repeat(64)}${"b".repeat(64)}`)
          .digest("hex");
      },
    },
    {
      label: "approval decision identity",
      expected: "decision ids",
      mutate: (value) => {
        value.approval_evidence[1].decision_id =
          value.approval_evidence[0].decision_id;
      },
    },
    {
      label: "resolved provenance",
      expected: "provenance must be resolved",
      mutate: (value) => {
        value.provenance.sources[0].source_revision = "unresolved";
      },
    },
    {
      label: "unique artifact identity",
      expected: "must be unique",
      mutate: (value) => {
        value.artifacts.push(structuredClone(value.artifacts[0]));
        value.artifacts[1].records = 0;
        value.content_hash = createHash("sha256")
          .update("a".repeat(128))
          .digest("hex");
      },
    },
  ];
  for (const { label, expected, mutate } of semanticMutations) {
    const invalidRelease = structuredClone(canonicalRelease);
    mutate(invalidRelease);
    if (
      !datasetManifestSemanticErrors(invalidRelease).some((error) =>
        error.includes(expected),
      )
    ) {
      throw new Error(
        `Runtime contract checker self-test failed: ${label}`,
      );
    }
  }
  console.log("Dataset v4 authority self-test passed.");
}

function assertThrows(operation, label) {
  try {
    operation();
  } catch {
    return;
  }
  throw new Error(`Runtime contract checker self-test failed: ${label}`);
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
