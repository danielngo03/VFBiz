import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';

const sourceRoot = resolve(__dirname, '../../src');
const modulesRoot = join(sourceRoot, 'modules');
const approvedContexts = [
  'access',
  'commerce',
  'customer',
  'engagement',
  'mobility',
  'operations',
  'ownership',
  'product',
  'sales',
] as const;

function typescriptFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory()
      ? typescriptFiles(path)
      : entry.name.endsWith('.ts')
        ? [path]
        : [];
  });
}

describe('bounded context layout', () => {
  it('contains only the approved durable business contexts', () => {
    const actual = readdirSync(modulesRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort();

    expect(actual).toEqual([...approvedContexts]);
  });

  it('does not deep-import another bounded context', () => {
    const violations = typescriptFiles(modulesRoot).flatMap((file) => {
      const owner = relative(modulesRoot, file).split('/')[0];
      const content = readFileSync(file, 'utf8');
      return [...content.matchAll(/from ['"]((?:\.\.\/)+[^'"]+)['"]/g)]
        .map((match) => match[1])
        .flatMap((specifier) => {
          const resolvedImport = resolve(dirname(file), specifier);
          const target = relative(modulesRoot, resolvedImport).split('/')[0];
          if (
            !approvedContexts.includes(target as never) ||
            target === owner ||
            resolvedImport === join(modulesRoot, target)
          ) {
            return [];
          }
          return [`${relative(sourceRoot, file)} -> ${target}`];
        });
    });

    expect(violations).toEqual([]);
  });
});
