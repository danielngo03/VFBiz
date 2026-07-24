import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import ts from 'typescript';

const ownershipRoot = resolve(__dirname);
const sourceRoot = resolve(ownershipRoot, '../..');
const allowedEntries = ['AGENTS.md', 'ownership-quarantine.spec.ts'] as const;
const legacyIdentifiers = new Set([
  'OwnerVehicleAssociation',
  'ServiceAppointmentProjection',
  'ownerVehicleAssociation',
  'serviceAppointmentProjection',
  'externalVehicleRef',
]);
const legacyDatabaseObjects = [
  'owner_vehicle_association',
  'service_appointment_projection',
] as const;

interface QuarantineViolation {
  readonly column: number;
  readonly line: number;
  readonly reason: string;
}

function normalizedPath(path: string): string {
  return path.replaceAll('\\', '/');
}

function runtimeTypescriptFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    const relativePath = normalizedPath(relative(sourceRoot, path));

    if (
      entry.isDirectory() &&
      (relativePath === 'generated' || relativePath === 'modules/ownership')
    ) {
      return [];
    }
    if (entry.isDirectory()) return runtimeTypescriptFiles(path);
    return entry.name.endsWith('.ts') && !entry.name.endsWith('.spec.ts')
      ? [path]
      : [];
  });
}

function staticallyKnownString(
  expression: ts.Expression,
  constants: ReadonlyMap<string, string>,
): string | null {
  if (ts.isStringLiteralLike(expression)) return expression.text;
  if (ts.isIdentifier(expression))
    return constants.get(expression.text) ?? null;
  if (ts.isParenthesizedExpression(expression)) {
    return staticallyKnownString(expression.expression, constants);
  }
  if (
    ts.isAsExpression(expression) ||
    ts.isTypeAssertionExpression(expression) ||
    ts.isSatisfiesExpression(expression)
  ) {
    return staticallyKnownString(expression.expression, constants);
  }
  if (
    ts.isBinaryExpression(expression) &&
    expression.operatorToken.kind === ts.SyntaxKind.PlusToken
  ) {
    const left = staticallyKnownString(expression.left, constants);
    const right = staticallyKnownString(expression.right, constants);
    return left === null || right === null ? null : left + right;
  }
  if (ts.isTemplateExpression(expression)) {
    const head = expression.head.text;
    let result = head;
    for (const span of expression.templateSpans) {
      const value = staticallyKnownString(span.expression, constants);
      if (value === null) return null;
      result += value + span.literal.text;
    }
    return result;
  }
  return null;
}

function constantStrings(
  sourceFile: ts.SourceFile,
): ReadonlyMap<string, string> {
  const declarations: ts.VariableDeclaration[] = [];
  const visit = (node: ts.Node): void => {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.initializer !== undefined &&
      ts.isVariableDeclarationList(node.parent) &&
      (node.parent.flags & ts.NodeFlags.Const) !== 0
    ) {
      declarations.push(node);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);

  const values = new Map<string, string>();
  for (let pass = 0; pass < declarations.length; pass += 1) {
    let changed = false;
    for (const declaration of declarations) {
      if (values.has(declaration.name.getText(sourceFile))) continue;
      const value = staticallyKnownString(declaration.initializer!, values);
      if (value !== null) {
        values.set(declaration.name.getText(sourceFile), value);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return values;
}

function templateStaticText(node: ts.TemplateLiteral): string {
  if (ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  return [
    node.head.text,
    ...node.templateSpans.map((span) => span.literal.text),
  ].join(' ');
}

function analyzeLegacyOwnershipUsage(
  sourceText: string,
  fileName: string,
): readonly QuarantineViolation[] {
  const sourceFile = ts.createSourceFile(
    fileName,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const constants = constantStrings(sourceFile);
  const violations: QuarantineViolation[] = [];
  const fingerprints = new Set<string>();

  const add = (node: ts.Node, reason: string): void => {
    const position = sourceFile.getLineAndCharacterOfPosition(node.getStart());
    const fingerprint = `${position.line}:${position.character}:${reason}`;
    if (fingerprints.has(fingerprint)) return;
    fingerprints.add(fingerprint);
    violations.push({
      column: position.character + 1,
      line: position.line + 1,
      reason,
    });
  };
  const checkStaticValue = (node: ts.Node, value: string): void => {
    if (legacyIdentifiers.has(value)) {
      add(node, `references quarantined ownership name ${value}`);
    }
    const normalized = value.toLowerCase();
    for (const databaseObject of legacyDatabaseObjects) {
      if (normalized.includes(databaseObject)) {
        add(node, `references quarantined database object ${databaseObject}`);
      }
    }
  };

  const visit = (node: ts.Node): void => {
    if (ts.isIdentifier(node) && legacyIdentifiers.has(node.text)) {
      add(node, `references quarantined ownership identifier ${node.text}`);
    }
    if (ts.isStringLiteralLike(node)) checkStaticValue(node, node.text);
    if (ts.isTemplateLiteral(node)) {
      checkStaticValue(node, templateStaticText(node));
    }
    if (
      ts.isElementAccessExpression(node) &&
      node.argumentExpression !== undefined
    ) {
      const value = staticallyKnownString(node.argumentExpression, constants);
      if (value !== null) checkStaticValue(node.argumentExpression, value);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return violations;
}

describe('legacy ownership quarantine', () => {
  it('contains policy and guardrail only, with no runtime entrypoint', () => {
    const entries = readdirSync(ownershipRoot).sort();

    expect(entries).toEqual([...allowedEntries].sort());
    expect(entries).not.toContain('index.ts');
    expect(entries).not.toContain('ownership.module.ts');
  });

  it('is not composed into the NestJS application', () => {
    const compositionRoot = readFileSync(
      join(sourceRoot, 'app.module.ts'),
      'utf8',
    );

    expect(compositionRoot).not.toMatch(
      /(?:from|require\()\s*['"][^'"]*modules\/ownership/,
    );
    expect(compositionRoot).not.toContain('OwnershipModule');
  });

  it('has no runtime consumer of the legacy ownership Prisma models', () => {
    const violations = runtimeTypescriptFiles(sourceRoot).flatMap((file) => {
      const content = readFileSync(file, 'utf8');
      return analyzeLegacyOwnershipUsage(content, file).map(
        (violation) =>
          `${normalizedPath(relative(sourceRoot, file))}:${violation.line}:${violation.column} ${violation.reason}`,
      );
    });

    expect(violations).toEqual([]);
  });

  it.each([
    [
      'direct Prisma delegate',
      'async function read(prisma: any) { return prisma.ownerVehicleAssociation.findMany(); }',
    ],
    [
      'computed Prisma delegate',
      "const delegate = 'owner' + 'VehicleAssociation';\nprisma[delegate].findMany();",
    ],
    [
      'raw SQL table',
      'prisma.$queryRaw`SELECT * FROM owner_vehicle_association`;',
    ],
    [
      'computed legacy external reference',
      "const field = `external${'Vehicle'}Ref`;\nrecord[field];",
    ],
    [
      'legacy generated type import',
      "import type { OwnerVehicleAssociation } from '../../generated/prisma/client';",
    ],
  ])('detects the negative fixture: %s', (_name, sourceText) => {
    expect(
      analyzeLegacyOwnershipUsage(sourceText, 'negative-fixture.ts'),
    ).not.toHaveLength(0);
  });

  it('does not flag legacy words that occur only in comments', () => {
    const sourceText = `
      // OwnerVehicleAssociation and owner_vehicle_association are quarantined.
      export const allowedCustomerProjection = { customerProfileId: 'synthetic' };
    `;

    expect(
      analyzeLegacyOwnershipUsage(sourceText, 'positive-fixture.ts'),
    ).toEqual([]);
  });
});
