/**
 * Automated Public API Reference Generator
 *
 * Inspects every public entrypoint (`@core`, `@core/pixel`, `@core/brush`) with the
 * TypeScript Compiler API, extracts exported symbols, JSDoc, signatures and types,
 * and writes the single API reference into `core/docs/api/`:
 * - `core.md`                  `@core`
 * - `pixel.md`                 `@core/pixel`
 * - `brush-geometry.md`, `brush-paths.md`, `brush-styles.md`, `brush-textures.md`  `@core/brush`
 *
 * Every exported symbol must land in exactly one file. The generator fails otherwise.
 */

import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import ts from 'typescript';

const OUTPUT_DIR = resolve('core/docs/api');

type Domain = 'geometry' | 'paths' | 'styles' | 'textures';

interface DomainConfig {
  id: Domain;
  filename: string;
  title: string;
  description: string;
}

// `@core/brush` is split by competence, because a full brush reference is too large to load at once.
const DOMAINS: Record<Domain, DomainConfig> = {
  geometry: {
    id: 'geometry',
    filename: 'brush-geometry.md',
    title: '@core/brush - Geometry, Primitives & 2D Modeling',
    description: 'Declarative vector shapes, parametric primitives, CSG booleans, deformation hooks, bilateral symmetry, lathe/revolve, lofting, extrusion and semantic layout placement.',
  },
  paths: {
    id: 'paths',
    filename: 'brush-paths.md',
    title: '@core/brush - Paths, Lines & Curves',
    description: 'Continuous path generation, PathBuilder fluent chaining, parametric measuring, variable-width ribbons, arc-length queries and path concatenation.',
  },
  styles: {
    id: 'styles',
    filename: 'brush-styles.md',
    title: '@core/brush - Styles, Brushes & Themes',
    description: 'Visual attributes, fill/stroke styles, cel-shading lights, extensible brush definitions (defineBrush), built-in renderers and color helpers.',
  },
  textures: {
    id: 'textures',
    filename: 'brush-textures.md',
    title: '@core/brush - Procedural Textures & Stamps',
    description: 'Hole-aware procedural fills (Hatch, Stipple, Grit), cacheable raster/vector stamp tips (StampAsset) and procedural stamp scattering (StampScatter).',
  },
};

interface OutputGroup {
  filename: string;
  title: string;
  description: string;
  select: (doc: SymbolDoc) => boolean;
}

interface Target {
  /** Import specifier as users write it. */
  spec: string;
  /** Entrypoint file, the module whose exports are the public surface. */
  entry: string;
  groups: OutputGroup[];
}

const ALL = (): boolean => true;

const TARGETS: Target[] = [
  {
    spec: '@core',
    entry: resolve('core/index.ts'),
    groups: [{
      filename: 'core.md',
      title: '@core - Shared Utilities',
      description: 'Asset contract (`defineAsset`, `createCanvas`), deterministic random, noise, color helpers, theme definition, sheet packing and the Bayer dithering matrix. Pixel rendering lives in `@core/pixel`.',
      select: ALL,
    }],
  },
  {
    spec: '@core/pixel',
    entry: resolve('core/pixel.ts'),
    groups: [{
      filename: 'pixel.md',
      title: '@core/pixel - Pixel Art Engine',
      description: 'Discrete integer-grid drawing through `PixelCanvas`: lines, rectangles, circles, polygon fills, outlines, character-matrix sprites and Bayer dithering.',
      select: ALL,
    }],
  },
  {
    spec: '@core/brush',
    entry: resolve('core/brush/index.ts'),
    groups: (Object.keys(DOMAINS) as Domain[]).map(domainKey => ({
      filename: DOMAINS[domainKey].filename,
      title: DOMAINS[domainKey].title,
      description: DOMAINS[domainKey].description,
      select: doc => doc.domain === domainKey,
    })),
  },
];

interface MethodDoc {
  name: string;
  signature: string;
  doc: string;
  isStatic: boolean;
}

interface MemberDoc {
  name: string;
  type: string;
  doc: string;
}

interface SymbolDoc {
  name: string;
  kind: 'class' | 'function' | 'interface' | 'type' | 'const';
  signature?: string;
  /** Generic parameters as written in source, e.g. `<P extends object = {}>`. */
  typeParams?: string;
  doc: string;
  constructors?: string[];
  methods?: MethodDoc[];
  properties?: MemberDoc[];
  domain: Domain;
}

function getCleanDoc(symbol: ts.Symbol, checker: ts.TypeChecker): string {
  const parts = symbol.getDocumentationComment(checker);
  return ts.displayPartsToString(parts).trim();
}

function cleanSignature(sig: string): string {
  return sig
    .replace(/import\([^)]+\)\./g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Generic parameters of an interface or type alias, as written in source. */
function typeParamsText(decl: ts.Declaration): string {
  const params = ts.isInterfaceDeclaration(decl) || ts.isTypeAliasDeclaration(decl) ? decl.typeParameters : undefined;
  return params && params.length > 0 ? `<${params.map(p => p.getText()).join(', ')}>` : '';
}

function determineDomain(name: string, sourcePath: string): Domain {
  const normalized = sourcePath.replace(/\\/g, '/');

  if (normalized.includes('/shapes/path') || normalized.includes('/stroke/')) {
    return 'paths';
  }
  if (normalized.includes('/textures/') || normalized.includes('/stamps/')) {
    return 'textures';
  }
  if (normalized.includes('/brushes/') || normalized.includes('/styles/') || normalized.includes('color.')) {
    return 'styles';
  }
  if (normalized.includes('/shapes/') || normalized.includes('/ops/')) {
    return 'geometry';
  }

  // Fallback for types declared in types.ts or params.ts:
  const pathsKeywords = ['Line', 'Arc', 'Curve', 'Spline', 'Bezier', 'Wave', 'Wobble', 'Ribbon', 'ToShape', 'LineToShape'];
  if (pathsKeywords.some(kw => name.includes(kw))) {
    return 'paths';
  }

  const texturesKeywords = ['Hatch', 'Stipple', 'Grit', 'Stamp', 'Texture'];
  if (texturesKeywords.some(kw => name.includes(kw))) {
    return 'textures';
  }

  const stylesKeywords = ['Stroke', 'Shadow', 'ShapeStyle', 'CelShade', 'Brush', 'Param', 'RGBA', 'Gradient', 'Paint'];
  if (stylesKeywords.some(kw => name.includes(kw))) {
    return 'styles';
  }

  return 'geometry';
}

function formatMarkdown(
  title: string,
  description: string,
  docs: SymbolDoc[],
  headerNotice = ''
): string {
  let md = `# ${title}\n\n`;
  if (headerNotice) {
    md += `> ${headerNotice}\n\n`;
  }
  if (description) {
    md += `${description}\n\n`;
  }

  const classes = docs.filter(d => d.kind === 'class');
  const functions = docs.filter(d => d.kind === 'function' || d.kind === 'const');
  const typesAndInterfaces = docs.filter(d => d.kind === 'interface' || d.kind === 'type');

  md += `## Table of Contents\n\n`;
  if (classes.length > 0) {
    md += `- [Classes & Constructors](#classes--constructors)\n`;
    for (const c of classes) md += `  - [\`${c.name}\`](#${c.name.toLowerCase()})\n`;
  }
  if (functions.length > 0) {
    md += `- [Functions & Operations](#functions--operations)\n`;
    for (const f of functions) md += `  - [\`${f.name}\`](#${f.name.toLowerCase()})\n`;
  }
  if (typesAndInterfaces.length > 0) {
    md += `- [Types & Interfaces](#types--interfaces)\n`;
    for (const t of typesAndInterfaces) md += `  - [\`${t.name}\`](#${t.name.toLowerCase()})\n`;
  }
  md += `\n---\n\n`;

  if (classes.length > 0) {
    md += `## Classes & Constructors\n\n`;
    for (const c of classes) {
      md += `### \`${c.name}\`\n\n`;
      if (c.doc) md += `${c.doc}\n\n`;

      if (c.constructors && c.constructors.length > 0) {
        md += `**Constructor${c.constructors.length > 1 ? 's' : ''}:**\n\`\`\`ts\n${c.constructors.map(sig => `new ${c.name}${sig}`).join('\n')}\n\`\`\`\n\n`;
      }

      if (c.properties && c.properties.length > 0) {
        md += `**Properties:**\n\n`;
        for (const p of c.properties) {
          md += `- \`${p.name}: ${p.type}\`${p.doc ? ` — ${p.doc}` : ''}\n`;
        }
        md += `\n`;
      }

      const staticMethods = c.methods?.filter(m => m.isStatic) || [];
      if (staticMethods.length > 0) {
        md += `**Static Factories:**\n\n`;
        for (const m of staticMethods) {
          md += `- \`${c.name}.${m.signature}\`\n`;
          if (m.doc) md += `  ${m.doc.replace(/\n/g, ' ')}\n`;
        }
        md += `\n`;
      }

      const instanceMethods = c.methods?.filter(m => !m.isStatic) || [];
      if (instanceMethods.length > 0) {
        md += `**Instance Methods:**\n\n`;
        for (const m of instanceMethods) {
          md += `- \`.${m.signature}\`\n`;
          if (m.doc) md += `  ${m.doc.replace(/\n/g, ' ')}\n`;
        }
        md += `\n`;
      }

      md += `---\n\n`;
    }
  }

  if (functions.length > 0) {
    md += `## Functions & Operations\n\n`;
    for (const f of functions) {
      md += `### \`${f.name}\`\n\n`;
      if (f.doc) md += `${f.doc}\n\n`;
      if (f.signature) md += `\`\`\`ts\n${f.signature}\n\`\`\`\n\n`;
      md += `---\n\n`;
    }
  }

  if (typesAndInterfaces.length > 0) {
    md += `## Types & Interfaces\n\n`;
    for (const t of typesAndInterfaces) {
      md += `### \`${t.name}\`\n\n`;
      if (t.doc) md += `${t.doc}\n\n`;
      if (t.signature) {
        md += `\`\`\`ts\n${t.signature}\n\`\`\`\n\n`;
      } else if (t.properties && t.properties.length > 0) {
        md += `\`\`\`ts\ninterface ${t.name}${t.typeParams ?? ''} {\n`;
        for (const p of t.properties) {
          md += p.type ? `  ${p.name}: ${p.type};\n` : `  ${p.name};\n`;
        }
        md += `}\n\`\`\`\n\n`;
      }
    }
  }

  return md;
}

function collectDocs(entryFile: string): SymbolDoc[] {
  const configPath = ts.findConfigFile('./', ts.sys.fileExists, 'tsconfig.json');
  let compilerOptions: ts.CompilerOptions = {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.NodeNext,
    moduleResolution: ts.ModuleResolutionKind.NodeNext,
  };

  if (configPath) {
    const configFile = ts.readConfigFile(configPath, ts.sys.readFile);
    const parsedConfig = ts.parseJsonConfigFileContent(configFile.config, ts.sys, dirname(configPath));
    compilerOptions = parsedConfig.options;
  }

  const program = ts.createProgram([entryFile], compilerOptions);
  const checker = program.getTypeChecker();
  const sourceFile = program.getSourceFile(entryFile);

  if (!sourceFile) {
    throw new Error(`Could not load entry file: ${entryFile}`);
  }

  const moduleSymbol = checker.getSymbolAtLocation(sourceFile);
  if (!moduleSymbol) {
    throw new Error(`Could not resolve module symbol for: ${entryFile}`);
  }

  const exports = checker.getExportsOfModule(moduleSymbol);
  const docs: SymbolDoc[] = [];

  for (const exp of exports) {
    const resolved = exp.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(exp) : exp;
    const name = exp.getName();
    const doc = getCleanDoc(resolved, checker) || getCleanDoc(exp, checker);
    const declarations = resolved.getDeclarations() || exp.getDeclarations() || [];
    const primaryDecl = declarations[0];

    if (!primaryDecl) continue;

    const sourcePath = primaryDecl.getSourceFile().fileName;
    const domain = determineDomain(name, sourcePath);

    if (ts.isClassDeclaration(primaryDecl)) {
      const methods: MethodDoc[] = [];
      const properties: MemberDoc[] = [];
      const constructors: string[] = [];

      for (const member of primaryDecl.members) {
        const modifiers = ts.canHaveModifiers(member) ? ts.getModifiers(member) : undefined;
        const isPrivate = modifiers?.some(m => m.kind === ts.SyntaxKind.PrivateKeyword || m.kind === ts.SyntaxKind.ProtectedKeyword);
        const nameText = member.name && ts.isIdentifier(member.name) ? member.name.text : '';

        if (isPrivate || nameText.startsWith('_') || nameText.startsWith('live')) continue;

        const memberSymbol = member.name ? checker.getSymbolAtLocation(member.name) : undefined;
        const memberDoc = memberSymbol ? getCleanDoc(memberSymbol, checker) : '';

        // A declaration with a body is the implementation of its overloads. It is internal, so only
        // the body-less overload signatures are documented. Members without overloads keep their body.
        const hasOverloads = (ts.isConstructorDeclaration(member) || ts.isMethodDeclaration(member))
          && member.body !== undefined
          && primaryDecl.members.some(other =>
            (ts.isConstructorDeclaration(other) || ts.isMethodDeclaration(other))
            && other.body === undefined
            && (
              (ts.isConstructorDeclaration(member) && ts.isConstructorDeclaration(other))
              || (ts.isMethodDeclaration(member) && ts.isMethodDeclaration(other) && other.name.getText() === member.name.getText())
            )
          );

        if (ts.isConstructorDeclaration(member) && !hasOverloads) {
          const sig = checker.getSignatureFromDeclaration(member);
          if (sig) {
            constructors.push(cleanSignature(checker.signatureToString(sig)));
          }
        } else if (ts.isMethodDeclaration(member) && !hasOverloads) {
          const isStatic = Boolean(modifiers?.some(m => m.kind === ts.SyntaxKind.StaticKeyword));
          const sig = checker.getSignatureFromDeclaration(member);
          const sigStr = sig ? checker.signatureToString(sig) : '()';
          methods.push({
            name: nameText,
            signature: cleanSignature(`${nameText}${sigStr}`),
            doc: memberDoc,
            isStatic,
          });
        } else if (ts.isPropertyDeclaration(member) || ts.isGetAccessorDeclaration(member)) {
          const propType = checker.getTypeAtLocation(member);
          properties.push({
            name: nameText,
            type: cleanSignature(checker.typeToString(propType)),
            doc: memberDoc,
          });
        }
      }

      docs.push({
        name,
        kind: 'class',
        doc,
        constructors,
        methods,
        properties,
        domain,
      });
    } else if (ts.isFunctionDeclaration(primaryDecl) || (ts.isVariableDeclaration(primaryDecl) && primaryDecl.initializer && ts.isArrowFunction(primaryDecl.initializer))) {
      const type = checker.getTypeOfSymbolAtLocation(resolved, primaryDecl);
      // One line per overload: the implementation signature is not visible on the type, only the overloads.
      const signatures = type.getCallSignatures().map(sig => cleanSignature(`function ${name}${checker.signatureToString(sig)}`));

      docs.push({
        name,
        kind: 'function',
        signature: signatures.join('\n'),
        doc,
        domain,
      });
    } else if (ts.isInterfaceDeclaration(primaryDecl)) {
      // Read members from the declared type, not the declaration's own nodes: this includes
      // inherited members (interface extends) and members of mapped aliases such as Partial<T>.
      const properties: MemberDoc[] = [];
      const declaredType = checker.getDeclaredTypeOfSymbol(resolved);
      for (const prop of checker.getPropertiesOfType(declaredType)) {
        const propDecl = prop.valueDeclaration ?? prop.declarations?.[0];
        const propDoc = getCleanDoc(prop, checker);
        if (propDecl && ts.isMethodSignature(propDecl)) {
          // Methods are listed as `name(params): ret` with no separate type column.
          const sig = checker.getSignatureFromDeclaration(propDecl);
          const sigStr = sig ? checker.signatureToString(sig) : '()';
          properties.push({
            name: cleanSignature(`${prop.getName()}${sigStr}`),
            type: '',
            doc: propDoc,
          });
        } else {
          properties.push({
            name: prop.getName(),
            type: cleanSignature(checker.typeToString(checker.getTypeOfSymbol(prop))),
            doc: propDoc,
          });
        }
      }
      docs.push({
        name,
        kind: 'interface',
        typeParams: typeParamsText(primaryDecl),
        doc,
        properties,
        domain,
      });
    } else if (ts.isTypeAliasDeclaration(primaryDecl)) {
      const type = checker.getTypeAtLocation(primaryDecl);
      // InTypeAlias expands the alias body instead of printing the alias's own name (`X = X`).
      const body = checker.typeToString(type, undefined, ts.TypeFormatFlags.InTypeAlias | ts.TypeFormatFlags.NoTruncation);
      docs.push({
        name,
        kind: 'type',
        signature: cleanSignature(`type ${name}${typeParamsText(primaryDecl)} = ${body}`),
        doc,
        domain,
      });
    } else {
      const type = checker.getTypeOfSymbolAtLocation(resolved, primaryDecl);
      docs.push({
        name,
        kind: 'const',
        signature: cleanSignature(`const ${name}: ${checker.typeToString(type, undefined, ts.TypeFormatFlags.NoTruncation)}`),
        doc,
        domain,
      });
    }
  }

  return docs;
}

function generateApiDocs(): void {
  mkdirSync(OUTPUT_DIR, { recursive: true });
  const notice = 'Auto-generated public API reference. Do not edit directly; re-run `npm run docs:api`.';

  for (const target of TARGETS) {
    console.log(`📖 Collecting ${target.spec} from ${target.entry}`);
    const docs = collectDocs(target.entry);

    const uncovered = docs.filter(doc => !target.groups.some(group => group.select(doc)));
    if (uncovered.length > 0) {
      throw new Error(`${target.spec}: no output file for ${uncovered.map(d => d.name).join(', ')}`);
    }

    for (const group of target.groups) {
      const selected = docs.filter(group.select);
      const outPath = resolve(OUTPUT_DIR, group.filename);
      writeFileSync(outPath, formatMarkdown(group.title, group.description, selected, notice), 'utf8');
      console.log(`✔ ${outPath} (${selected.length} symbols)`);
    }
  }
}

generateApiDocs();
