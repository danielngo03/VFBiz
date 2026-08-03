#!/usr/bin/env node
import {
  createHash,
  generateKeyPairSync,
  sign as createSignature,
} from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import yaml from "js-yaml";
import {
  SignedAuthorityError,
  canonicalAuthorityJson,
  verifyAndProjectSignedAuthority,
  verifyNormalizedAuthorityProjection,
  verifySignedAuthority,
} from "./lib/gcp-signed-authority.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contractRegistry = await loadContractRegistry();
const datasetManifestV3ContractId =
  "https://vfbiz.example/contracts/ai/dataset-release-manifest/v3";
const datasetManifestV4ContractId =
  "https://vfbiz.example/contracts/ai/dataset-release-manifest/v4";
const assistantClassifierBindingContractId =
  "https://vfbiz.example/contracts/ai/assistant-release-classifier-binding/v1";
const sourceRegisterContractId =
  "https://vfbiz.example/contracts/ai/source-register/v5";
const contractPath = (contractId) => {
  const entry = contractRegistry.byId.get(contractId);
  if (!entry) throw new Error(`AI contract is not registered: ${contractId}`);
  return entry.canonicalPath;
};
const schemaPaths = [
  "contracts/governance/agent-runtime.schema.json",
  "contracts/governance/gcp-controlled-apply-authority.schema.json",
  "contracts/governance/gcp-controlled-apply-verified-envelope.schema.json",
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
ajv.addFormat("vfbiz-canonical-utc-timestamp", {
  type: "string",
  validate: (value) => {
    if (
      !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{3})?Z$/.test(
        value,
      )
    )
      return false;
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed)) return false;
    const normalized = value.includes(".")
      ? new Date(parsed).toISOString()
      : new Date(parsed).toISOString().replace(".000Z", "Z");
    return normalized === value;
  },
});
const governanceSchema = JSON.parse(
  await readFile(
    path.join(root, "contracts/governance/governance.schema.json"),
    "utf8",
  ),
);
ajv.addSchema(governanceSchema);
const schemas = new Map();

assertEvaluationCanonicalDigestParity();

for (const relativePath of schemaPaths) {
  const schema = JSON.parse(
    await readFile(path.join(root, relativePath), "utf8"),
  );
  ajv.compile(schema);
  schemas.set(relativePath, schema);
}

await assertGovernanceContractVectors(
  "contracts/governance/gcp-controlled-apply-authority.schema.json",
  "contracts/governance/gcp-controlled-apply-authority.vectors.json",
);
await assertPlainContractVectors(
  "contracts/governance/gcp-controlled-apply-verified-envelope.schema.json",
  "contracts/governance/gcp-controlled-apply-verified-envelope.vectors.json",
);

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
  const semanticErrors = [
    datasetManifestV3ContractId,
    datasetManifestV4ContractId,
  ].includes(registryEntry.contractId)
    ? datasetManifestSemanticErrors(vector.value)
    : registryEntry.contractId ===
        "https://vfbiz.example/contracts/ai/source-intake-receipt/v1"
      ? sourceIntakeReceiptSemanticErrors(vector.value)
      : registryEntry.contractId === sourceRegisterContractId
        ? sourceRegisterSemanticErrors(vector.value)
        : registryEntry.contractId === assistantClassifierBindingContractId
          ? assistantClassifierBindingSemanticErrors(vector.value)
          : registryEntry.contractId ===
              "https://vfbiz.example/contracts/ai/golden-case/v2"
            ? goldenCaseSemanticErrors(vector.value)
            : [
                  "https://vfbiz.example/contracts/ai/evaluation/grader-calibration/v1",
                  "https://vfbiz.example/contracts/ai/evaluation/grader-calibration/v2",
                ].includes(registryEntry.contractId)
              ? graderCalibrationSemanticErrors(
                  vector.value,
                  registryEntry.contractId.endsWith("/v2"),
                )
              : [
                    "https://vfbiz.example/contracts/ai/evaluation/benchmark-definition/v2",
                    "https://vfbiz.example/contracts/ai/evaluation/run-request/v2",
                    "https://vfbiz.example/contracts/ai/evaluation/case-result/v1",
                    "https://vfbiz.example/contracts/ai/evaluation/run-result/v1",
                  ].includes(registryEntry.contractId)
                ? evaluationMoneySemanticErrors(
                    registryEntry.contractId,
                    vector.value,
                  )
                : registryEntry.contractId ===
                    "https://vfbiz.example/contracts/ai/evaluation/run-result/v1"
                  ? evaluationRunResultSemanticErrors(vector.value)
                  : registryEntry.contractId ===
                      "https://vfbiz.example/contracts/ai/evaluation/evidence-bundle/v1"
                    ? evaluationEvidenceBundleSemanticErrors(vector.value)
                    : [];
  const observed = schemaValid && semanticErrors.length === 0;
  const expected =
    typeof vector.semantic_valid === "boolean"
      ? vector.semantic_valid
      : vector.valid;
  if (observed !== expected) {
    throw new Error(
      `Dataset contract vector ${vector.id} expected valid=${expected}: ${ajv.errorsText(validate.errors)} ${semanticErrors.join("; ")}`,
    );
  }
}

function sourceRegisterSemanticErrors(value) {
  const originKind = value?.origin?.kind;
  if (
    ["managed-upload", "local-bootstrap"].includes(originKind) &&
    value.source_revision !== value.content_revision
  ) {
    return ["managed source revision must equal its content revision"];
  }
  return [];
}

function sourceIntakeReceiptSemanticErrors(value) {
  if (value.content_revision !== `sha256:${value.observed_sha256}`) {
    return ["content revision must equal the observed SHA-256"];
  }
  return [];
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

function assertEvaluationCanonicalDigestParity() {
  const vector = {
    n: -0,
    small: 1e-7,
    large: 1e21,
    v: "Việt",
    x: 1,
  };
  const canonical = canonicalEvaluationJson(vector);
  const expectedCanonical =
    '{"large":1e+21,"n":0,"small":1e-7,"v":"Việt","x":1}';
  const digest = `sha256:${createHash("sha256").update(canonical).digest("hex")}`;
  const expectedDigest =
    "sha256:2cee1c2db35a2523a4212e3dbebe0694b85e04547ae13dfcd71b2b0857a464d5";
  if (canonical !== expectedCanonical || digest !== expectedDigest) {
    throw new Error(
      "Evaluation canonical JSON/digest differs from the Python evidence authority",
    );
  }
}

function canonicalEvaluationJson(value) {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value))
      throw new Error("Evaluation canonical JSON rejects non-finite numbers");
    return JSON.stringify(Object.is(value, -0) ? 0 : value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value))
    return `[${value.map(canonicalEvaluationJson).join(",")}]`;
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalEvaluationJson(value[key])}`,
      )
      .join(",")}}`;
  }
  throw new Error(`Evaluation canonical JSON rejects ${typeof value} values`);
}

async function assertGovernanceContractVectors(schemaPath, vectorsPath) {
  const schema = schemas.get(schemaPath);
  const validate = ajv.getSchema(schema.$id) ?? ajv.compile(schema);
  const vectors = JSON.parse(
    await readFile(path.join(root, vectorsPath), "utf8"),
  );
  if (!Array.isArray(vectors) || vectors.length < 2)
    throw new Error(`${vectorsPath}: expected positive and negative vectors`);
  for (const vector of vectors) {
    const observed = validate(vector.value);
    if (observed !== vector.valid) {
      throw new Error(
        `${vectorsPath}:${vector.id} expected valid=${vector.valid}: ${ajv.errorsText(validate.errors)}`,
      );
    }
  }
  const normalizedSchema = schemas.get(
    "contracts/governance/gcp-controlled-apply-verified-envelope.schema.json",
  );
  const validateNormalized =
    ajv.getSchema(normalizedSchema.$id) ?? ajv.compile(normalizedSchema);
  assertSignedAuthorityVerifier(vectors, validate, validateNormalized);
}

async function assertPlainContractVectors(schemaPath, vectorsPath) {
  const schema = schemas.get(schemaPath);
  const validate = ajv.getSchema(schema.$id) ?? ajv.compile(schema);
  const vectors = JSON.parse(
    await readFile(path.join(root, vectorsPath), "utf8"),
  );
  if (!Array.isArray(vectors) || vectors.length < 2)
    throw new Error(`${vectorsPath}: expected positive and negative vectors`);
  for (const vector of vectors) {
    const observed = validate(vector.value);
    if (observed !== vector.valid)
      throw new Error(
        `${vectorsPath}:${vector.id} expected valid=${vector.valid}: ${ajv.errorsText(validate.errors)}`,
      );
    if (
      vector.valid &&
      schemaPath ===
        "contracts/governance/gcp-controlled-apply-verified-envelope.schema.json"
    ) {
      const semanticDigest = createHash("sha256")
        .update(canonicalAuthorityJson(vector.value.projection))
        .digest("hex");
      if (vector.value.projection_sha256 !== semanticDigest)
        throw new Error(`${vectorsPath}:${vector.id} projection digest drift`);
      for (const field of [
        "aggregate_authority_complete",
        "approval_event_verified",
        "cancellation_authority_verified",
        "dispatch_eligible",
        "workforce_capability_verified",
        "workforce_subject_verified",
      ]) {
        const widened = structuredClone(vector.value);
        widened.projection[field] = true;
        if (validate(widened))
          throw new Error(`${vectorsPath}:${vector.id} allowed ${field}=true`);
      }
      for (const field of [
        "issued_at",
        "expires_at",
        "claimed_claim_expires_at",
        "claimed_approval_event_occurred_at",
      ]) {
        if (!(field in vector.value.projection)) continue;
        for (const invalid of [
          "2026-08-02T13:00:00+07:00",
          "2026-08-02T06:00:00.1Z",
          "2026-02-30T06:00:00Z",
          "2026-13-01T06:00:00Z",
          "2026-01-01T25:00:00Z",
          "2026-12-31T23:59:60Z",
        ]) {
          const candidate = structuredClone(vector.value);
          candidate.projection[field] = invalid;
          if (validate(candidate))
            throw new Error(
              `${vectorsPath}:${vector.id} accepted non-canonical ${field}`,
            );
        }
      }
    }
  }
}

function assertSignedAuthorityVerifier(
  vectors,
  validateSchema,
  validateNormalized,
) {
  const positive = vectors.find((vector) => vector.valid === true)?.value;
  if (!positive) throw new Error("signed authority positive vector is missing");
  const { privateKey, publicKey } = generateKeyPairSync("ec", {
    namedCurve: "prime256v1",
  });
  const signEnvelope = (candidate) => {
    const payloadJson = canonicalAuthorityJson(candidate.payload);
    candidate.payload_sha256 = createHash("sha256")
      .update(payloadJson)
      .digest("hex");
    const signingProjection = canonicalAuthorityJson({
      algorithm: candidate.signature.algorithm,
      issuer_service_account: candidate.signature.issuer_service_account,
      kms_key_version: candidate.signature.kms_key_version,
      payload: candidate.payload,
      payload_sha256: candidate.payload_sha256,
      schema_version: candidate.schema_version,
    });
    candidate.signature.value_base64 = createSignature(
      "sha256",
      Buffer.from(signingProjection),
      privateKey,
    ).toString("base64");
    return candidate;
  };
  const envelope = signEnvelope(structuredClone(positive));
  const publicKeySha256 = createHash("sha256")
    .update(publicKey.export({ type: "spki", format: "der" }))
    .digest("hex");
  const trustedKmsKeyVersions = new Map([
    [
      envelope.signature.kms_key_version,
      {
        algorithm: "EC_SIGN_P256_SHA256",
        issuerServiceAccount: envelope.signature.issuer_service_account,
        publicKeyPem: publicKey.export({ type: "spki", format: "pem" }),
        publicKeySha256,
        state: "ENABLED",
      },
    ],
  ]);
  const context = {
    nowMs: Date.parse("2026-08-02T06:10:00Z"),
    expectedBrokerServiceAccount: envelope.payload.broker_service_account,
    expectedExecutorServiceAccount: envelope.payload.executor_service_account,
    trustedKmsKeyVersions,
    verifierRevisionSha256: "f".repeat(64),
    expectedVerifierRevisionSha256: "f".repeat(64),
  };
  const signedEnvelope = canonicalAuthorityJson(envelope);
  context.sourceEnvelopeUri =
    "gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/" +
    `${createHash("sha256").update(signedEnvelope).digest("hex")}.json#1`;
  const verified = verifySignedAuthority(signedEnvelope, context);
  if (
    !verified.signatureValid ||
    !verified.semanticValid ||
    verified.disposition !== "review-pending" ||
    verified.dispatchEligible
  )
    throw new Error("synthetic signed authority must remain inert");
  const normalized = verifyAndProjectSignedAuthority(signedEnvelope, context);
  verifyNormalizedAuthorityProjection(normalized, {
    ...context,
    sourceEnvelopeBytes: signedEnvelope,
  });
  if (!validateNormalized(normalized))
    throw new Error(
      `normalized signed authority is invalid: ${ajv.errorsText(validateNormalized.errors)}`,
    );
  const normalizedDigest = createHash("sha256")
    .update(canonicalAuthorityJson(normalized.projection))
    .digest("hex");
  if (
    normalized.projection_sha256 !== normalizedDigest ||
    normalized.projection.source_signature_verified !== true ||
    normalized.projection.source_semantics_verified !== true ||
    normalized.projection.workforce_subject_verified !== false ||
    normalized.projection.workforce_capability_verified !== false ||
    normalized.projection.approval_event_verified !== false ||
    normalized.projection.cancellation_authority_verified !== false ||
    normalized.projection.aggregate_authority_complete !== false ||
    normalized.projection.dispatch_eligible !== false
  )
    throw new Error("normalized signed authority widened its authority class");
  for (const field of [
    "base_revision",
    "decision_id",
    "plan_uri",
    "executor_image",
  ]) {
    for (const invalid of [
      [positive.payload[field]],
      { value: positive.payload[field] },
    ]) {
      const candidate = signEnvelope(structuredClone(positive));
      candidate.payload[field] = invalid;
      signEnvelope(candidate);
      if (validateSchema(candidate))
        throw new Error(`signed authority schema accepted non-string ${field}`);
      try {
        verifySignedAuthority(canonicalAuthorityJson(candidate), context);
      } catch (error) {
        if (error instanceof SignedAuthorityError) continue;
        throw error;
      }
      throw new Error(`signed authority runtime coerced non-string ${field}`);
    }
  }
  const payloadJson = canonicalAuthorityJson(envelope.payload);
  envelope.signature.value_base64 = createSignature(
    "sha256",
    Buffer.from(`${payloadJson}tampered`),
    privateKey,
  ).toString("base64");
  try {
    verifySignedAuthority(canonicalAuthorityJson(envelope), context);
  } catch (error) {
    if (
      error instanceof SignedAuthorityError &&
      error.code === "AUTHORITY_SIGNATURE_INVALID"
    )
      return;
    throw error;
  }
  throw new Error("signed authority verifier accepted an invalid signature");
}

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

function assistantClassifierBindingSemanticErrors(binding) {
  if (!isRecord(binding)) return ["classifier binding must be an object"];
  const errors = [];
  const evaluation = isRecord(binding.evaluation_evidence)
    ? binding.evaluation_evidence
    : {};
  if (
    evaluation.target_classification_stack_sha256 !==
    binding.classification_stack_sha256
  ) {
    errors.push(
      "evaluation evidence must target the classification stack digest",
    );
  }
  const approval = isRecord(binding.approval_evidence)
    ? binding.approval_evidence
    : {};
  if (approval.target_binding_core_sha256 !== binding.binding_core_sha256) {
    errors.push("approval evidence must target the binding core digest");
  }
  const effectiveAt = Date.parse(binding.effective_at);
  const expiresAt = Date.parse(binding.expires_at);
  const evidenceValidUntil = Date.parse(evaluation.valid_until);
  if (
    !Number.isFinite(effectiveAt) ||
    !Number.isFinite(expiresAt) ||
    expiresAt <= effectiveAt
  ) {
    errors.push("classifier binding effective window is invalid");
  }
  if (
    !Number.isFinite(evidenceValidUntil) ||
    !Number.isFinite(expiresAt) ||
    evidenceValidUntil < expiresAt
  ) {
    errors.push(
      "classifier evaluation evidence must cover the binding effective window",
    );
  }
  return errors;
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
      (isV4 && artifactAddresses.has(artifact.content_address)) ||
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
    isRecord(split) && isRecord(split.partitions) ? split.partitions : {};
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
      if (isV4 && ["decision-ready", "released"].includes(manifest.status)) {
        let current = true;
        if (evidence.state !== "verified") {
          current = false;
          errors.push(
            "decision-ready or released quality evidence must be verified",
          );
        }
        if (evidence.revoked_at !== null && evidence.revoked_at !== undefined) {
          current = false;
          errors.push("decision-ready or released quality evidence is revoked");
        }
        const expiry = Date.parse(evidence.expires_at);
        if (!Number.isFinite(expiry) || expiry <= Date.now()) {
          current = false;
          errors.push("decision-ready or released quality evidence is expired");
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

function graderCalibrationSemanticErrors(
  calibration,
  requireEvidenceDigest = false,
) {
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
      const f1Denominator = 2 * truePositive + falsePositive + falseNegative;
      if (f1Denominator === 0) {
        errors.push("calibration must contain positive predictions or labels");
        return errors;
      }
      if (
        !balancedAccuracyMatches(
          calibration.balanced_accuracy,
          truePositive,
          trueNegative,
          falsePositive,
          falseNegative,
        )
      ) {
        errors.push("balanced_accuracy must match confusion matrix");
      }
      if (
        !f1Matches(calibration.f1, truePositive, falsePositive, falseNegative)
      ) {
        errors.push("f1 must match confusion matrix");
      }
    }
  }
  if (
    Date.parse(calibration.expires_at) <= Date.parse(calibration.calibrated_at)
  ) {
    errors.push("calibration expiry must be after calibrated_at");
  }
  if (requireEvidenceDigest) {
    const semanticDocument = structuredClone(calibration);
    delete semanticDocument.evidence_digest;
    const observedDigest = `sha256:${createHash("sha256")
      .update(canonicalEvaluationJson(semanticDocument))
      .digest("hex")}`;
    if (calibration.evidence_digest !== observedDigest) {
      errors.push("calibration evidence_digest must match semantic document");
    }
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
  for (const slice of Array.isArray(calibration.slice_metrics)
    ? calibration.slice_metrics
    : []) {
    if (!isRecord(slice) || !isRecord(slice.confusion_matrix)) continue;
    const sliceMatrix = slice.confusion_matrix;
    const values = [
      sliceMatrix.true_positive,
      sliceMatrix.true_negative,
      sliceMatrix.false_positive,
      sliceMatrix.false_negative,
    ];
    if (!values.every(Number.isInteger)) continue;
    const [truePositive, trueNegative, falsePositive, falseNegative] = values;
    if (
      values.reduce((total, value) => total + value, 0) !== slice.sample_size
    ) {
      errors.push(`calibration slice ${slice.slice} matrix total mismatch`);
      continue;
    }
    if (slice.sample_size > calibration.sample_size) {
      errors.push(
        `calibration slice ${slice.slice} exceeds overall sample_size`,
      );
    }
    const positiveDenominator = truePositive + falseNegative;
    const negativeDenominator = trueNegative + falsePositive;
    const f1Denominator = 2 * truePositive + falsePositive + falseNegative;
    if (
      positiveDenominator <= 0 ||
      negativeDenominator <= 0 ||
      f1Denominator <= 0
    ) {
      errors.push(`calibration slice ${slice.slice} is not calibratable`);
      continue;
    }
    if (
      !balancedAccuracyMatches(
        slice.balanced_accuracy,
        truePositive,
        trueNegative,
        falsePositive,
        falseNegative,
      )
    ) {
      errors.push(
        `calibration slice ${slice.slice} balanced_accuracy mismatch`,
      );
    }
    if (!f1Matches(slice.f1, truePositive, falsePositive, falseNegative)) {
      errors.push(`calibration slice ${slice.slice} f1 mismatch`);
    }
    if (
      slice.slice === "all" &&
      (slice.sample_size !== calibration.sample_size ||
        !confusionMatricesEqual(
          slice.confusion_matrix,
          calibration.confusion_matrix,
        ) ||
        slice.balanced_accuracy !== calibration.balanced_accuracy ||
        slice.f1 !== calibration.f1)
    ) {
      errors.push("calibration all slice must equal overall calibration");
    }
  }
  return errors;
}

function evaluationMoneySemanticErrors(contractId, value) {
  let cost;
  if (contractId.endsWith("/benchmark-definition/v2"))
    cost = value?.budgets?.max_cost_usd;
  else if (contractId.endsWith("/run-request/v2"))
    cost = value?.budgets?.maxCostUsd;
  else if (contractId.endsWith("/case-result/v1"))
    cost = value?.usage?.cost_usd;
  else cost = value?.budget_usage?.cost_usd;
  const errors =
    typeof cost === "number" &&
    Number.isFinite(cost) &&
    cost >= 0 &&
    cost <= 1_000_000 &&
    hasAtMostDecimalPlaces(cost, 6)
      ? []
      : ["evaluation cost must use bounded micro-USD precision"];
  return contractId.endsWith("/run-result/v1")
    ? [...errors, ...evaluationRunResultSemanticErrors(value)]
    : errors;
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

function balancedAccuracyMatches(observed, tp, tn, fp, fn) {
  const positiveTotal = BigInt(tp) + BigInt(fn);
  const negativeTotal = BigInt(tn) + BigInt(fp);
  const numerator = BigInt(tp) * negativeTotal + BigInt(tn) * positiveTotal;
  const denominator = 2n * positiveTotal * negativeTotal;
  return metricMatchesRatio(observed, numerator, denominator);
}

function f1Matches(observed, tp, fp, fn) {
  return metricMatchesRatio(
    observed,
    2n * BigInt(tp),
    2n * BigInt(tp) + BigInt(fp) + BigInt(fn),
  );
}

function metricMatchesRatio(observed, expectedNumerator, expectedDenominator) {
  const observedRatio = decimalNumberRatio(observed);
  if (!observedRatio || expectedDenominator <= 0n) return false;
  const [observedNumerator, observedDenominator] = observedRatio;
  const difference =
    observedNumerator * expectedDenominator -
    expectedNumerator * observedDenominator;
  const absoluteDifference = difference < 0n ? -difference : difference;
  return (
    absoluteDifference * 1_000_000_000_000n <=
    observedDenominator * expectedDenominator
  );
}

function decimalNumberRatio(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  const match = value
    .toString()
    .toLowerCase()
    .match(/^(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?$/);
  if (!match) return null;
  const fraction = match[2] ?? "";
  const exponent = Number.parseInt(match[3] ?? "0", 10);
  let numerator = BigInt(`${match[1]}${fraction}`);
  const scale = fraction.length - exponent;
  if (scale <= 0) {
    numerator *= 10n ** BigInt(-scale);
    return [numerator, 1n];
  }
  return [numerator, 10n ** BigInt(scale)];
}

function confusionMatricesEqual(left, right) {
  if (!isRecord(left) || !isRecord(right)) return false;
  return [
    "true_positive",
    "true_negative",
    "false_positive",
    "false_negative",
  ].every((key) => left[key] === right[key]);
}

function hasAtMostDecimalPlaces(value, maximumPlaces) {
  if (typeof value !== "number" || !Number.isFinite(value)) return false;
  const match = value
    .toString()
    .toLowerCase()
    .match(/^\d+(?:\.(\d+))?(?:e([+-]?\d+))?$/);
  if (!match) return false;
  const fractionalDigits = match[1]?.length ?? 0;
  const exponent = Number.parseInt(match[2] ?? "0", 10);
  return fractionalDigits - exponent <= maximumPlaces;
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
  unboundQualityRelease.quality_evidence[0].artifact_digest = `sha256:${"7".repeat(64)}`;
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
      throw new Error(`Runtime contract checker self-test failed: ${label}`);
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
