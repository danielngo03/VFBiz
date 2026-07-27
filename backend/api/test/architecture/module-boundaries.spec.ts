import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';

const sourceRoot = resolve(__dirname, '../../src');
const modulesRoot = join(sourceRoot, 'modules');
const approvedContexts = [
  'access',
  'customer',
  'engagement',
  'mobility',
  'product',
] as const;
const dormantContextMarkers = ['commerce', 'operations', 'sales'] as const;
const frameworkOrOrmImports = [
  '@nestjs/',
  '@prisma/',
  '/generated/prisma',
  'fastify',
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
  it('contains only approved runtime contexts or explicit dormant markers', () => {
    const directories = readdirSync(modulesRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort();

    const runtime = directories.filter(
      (context) => typescriptFiles(join(modulesRoot, context)).length > 0,
    );
    const dormant = directories.filter((context) => !runtime.includes(context));

    expect(runtime).toEqual([...approvedContexts]);
    expect(dormant).toEqual([...dormantContextMarkers]);
    for (const context of dormant) {
      expect(existsSync(join(modulesRoot, context, 'DORMANT.md'))).toBe(true);
    }
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

  it('keeps domain code independent from framework and ORM types', () => {
    const violations = approvedContexts.flatMap((context) => {
      const domain = join(modulesRoot, context, 'domain');
      if (!existsSync(domain)) return [];
      return typescriptFiles(domain).flatMap((file) => {
        const content = readFileSync(file, 'utf8');
        return [...content.matchAll(/from ['"]([^'"]+)['"]/g)]
          .map((match) => match[1])
          .filter((specifier) =>
            frameworkOrOrmImports.some((forbidden) =>
              specifier.includes(forbidden),
            ),
          )
          .map(
            (specifier) => `${relative(sourceRoot, file)} imports ${specifier}`,
          );
      });
    });

    expect(violations).toEqual([]);
  });

  it('does not import infrastructure or presentation into application code', () => {
    const violations = approvedContexts.flatMap((context) => {
      const application = join(modulesRoot, context, 'application');
      if (!existsSync(application)) return [];
      return typescriptFiles(application).flatMap((file) => {
        const content = readFileSync(file, 'utf8');
        return [...content.matchAll(/from ['"]([^'"]+)['"]/g)]
          .map((match) => match[1])
          .filter(
            (specifier) =>
              specifier.includes('/infrastructure/') ||
              specifier.includes('/presentation/'),
          )
          .map(
            (specifier) => `${relative(sourceRoot, file)} imports ${specifier}`,
          );
      });
    });

    expect(violations).toEqual([]);
  });
});
