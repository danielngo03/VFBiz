#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import yaml from 'js-yaml';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const schemaPaths = [
  'contracts/json-schema/citation.schema.json',
  'contracts/json-schema/dataset-release-manifest.schema.json',
  'contracts/json-schema/ai-release-manifest.schema.json',
  'contracts/ai/conversation-turn-protocol.schema.json',
  'contracts/ai/conversation-public-event.schema.json',
  'contracts/ai/ai-execution-assertion.schema.json',
];
const conversationEventSchemaPath =
  'contracts/ai/conversation-public-event.schema.json';
const publicClientPath = 'packages/api-client/src/generated.ts';
const conversationCandidatePath =
  'contracts/openapi/customer-conversation-candidate-v1.yaml';
const requiredConversationOperationIds = [
  'createConversationSession',
  'getConversationSession',
  'closeConversationSession',
  'enqueueConversationMessage',
  'listConversationMessages',
  'streamConversationEvents',
  'cancelConversationTurn',
  'requestConversationHandoff',
];
const ajv = new Ajv2020({ strict: true, allErrors: true });
addFormats(ajv);
const schemas = new Map();

for (const relativePath of schemaPaths) {
  const schema = JSON.parse(await readFile(path.join(root, relativePath), 'utf8'));
  ajv.compile(schema);
  schemas.set(relativePath, schema);
}

const conversationEventSchema = schemas.get(conversationEventSchemaPath);
assertGeneratorFriendlyEventSchema(conversationEventSchema);
const publicClient = await readFile(path.join(root, publicClientPath), 'utf8');
const conversationCandidate = yaml.load(
  await readFile(path.join(root, conversationCandidatePath), 'utf8'),
);
assertCandidateOperationIds(
  conversationCandidate,
  requiredConversationOperationIds,
);
assertReleasedClientExcludesOperationIds(
  publicClient,
  requiredConversationOperationIds,
);

if (process.argv.includes('--self-test')) runNegativeSelfTest();

console.log(
  `Runtime contracts verified: ${schemaPaths.length} schemas, ${requiredConversationOperationIds.length} isolated candidate operations`,
);

function assertCandidateOperationIds(candidate, requiredOperationIds) {
  const operationIds = collectOpenApiOperationIds(candidate);
  const missing = requiredOperationIds.filter(
    (operationId) => !operationIds.has(operationId),
  );
  if (missing.length > 0) {
    throw new Error(
      `Customer Conversation candidate is missing required operation IDs: ${missing.join(', ')}`,
    );
  }
}

function assertReleasedClientExcludesOperationIds(
  source,
  forbiddenOperationIds,
) {
  const operations = extractOperationsInterface(source);
  const leaked = forbiddenOperationIds.filter((operationId) =>
    new RegExp(
      `^\\s{4}${escapeRegExp(operationId)}:\\s*\\{\\s*$`,
      'm',
    ).test(operations),
  );
  if (leaked.length > 0) {
    throw new Error(
      `Released public API client contains unreleased Conversation operation IDs: ${leaked.join(', ')}`,
    );
  }
}

function collectOpenApiOperationIds(candidate) {
  if (!isRecord(candidate) || !isRecord(candidate.paths)) {
    throw new Error(
      'Customer Conversation candidate does not declare an OpenAPI paths object',
    );
  }
  const operationIds = new Set();
  const methods = new Set([
    'delete',
    'get',
    'head',
    'options',
    'patch',
    'post',
    'put',
    'trace',
  ]);
  for (const pathItem of Object.values(candidate.paths)) {
    if (!isRecord(pathItem)) continue;
    for (const [method, operation] of Object.entries(pathItem)) {
      if (
        methods.has(method.toLowerCase()) &&
        isRecord(operation) &&
        typeof operation.operationId === 'string'
      ) {
        operationIds.add(operation.operationId);
      }
    }
  }
  return operationIds;
}

function assertGeneratorFriendlyEventSchema(schema) {
  if (!isRecord(schema) || !isRecord(schema.$defs)) {
    throw new Error('Conversation event schema does not declare $defs');
  }
  if (containsKeyword(schema, 'allOf')) {
    throw new Error(
      'Conversation event schema must not compose event envelopes with allOf',
    );
  }
  const variantNames = [
    'MessageAcceptedEvent',
    'TurnProcessingEvent',
    'TurnCompletedEvent',
    'HandoffRequestedEvent',
    'TurnCancelledEvent',
    'RetrievalStartedFrame',
    'ToolStartedFrame',
    'ReconnectRequiredFrame',
  ];
  const eventTypes = new Set();
  for (const variantName of variantNames) {
    const variant = schema.$defs[variantName];
    if (
      !isRecord(variant) ||
      !Array.isArray(variant.required) ||
      !variant.required.includes('type') ||
      !variant.required.includes('data') ||
      !isRecord(variant.properties) ||
      !isRecord(variant.properties.type) ||
      typeof variant.properties.type.const !== 'string' ||
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

function extractOperationsInterface(source) {
  const marker = 'export interface operations {';
  const start = source.indexOf(marker);
  if (start < 0) {
    throw new Error(
      'Generated public API client does not declare the operations interface',
    );
  }
  return source.slice(start + marker.length);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
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
  const releasedClient = 'export interface operations {\n}\n';
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
            '/synthetic/0': { get: { operationId: 'unrelatedOperation' } },
          },
        },
        requiredConversationOperationIds,
      ),
    'missing candidate operation ID',
  );
  assertThrows(
    () =>
      assertReleasedClientExcludesOperationIds(
        'export interface operations {\n    createConversationSession: {\n    };\n}\n',
        requiredConversationOperationIds,
      ),
    'released operation leak',
  );
  assertThrows(
    () =>
      assertGeneratorFriendlyEventSchema({
        ...conversationEventSchema,
        allOf: [],
      }),
    'allOf event envelope',
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
                (field) => field !== 'data',
              ),
          },
        },
      }),
    'event variant without required data',
  );
  assertThrows(
    () =>
      ajv.compile({
        $schema: 'https://json-schema.org/draft/2020-12/schema',
        type: 'object',
        vfbizUnknownKeyword: true,
      }),
    'strict schema keyword',
  );
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
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
