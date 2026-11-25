import assert from 'node:assert/strict';
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import ts from 'typescript';

console.log('🧪 Checking skill and guide snippets...\n');

// Guides describe choices, not templates. A fenced `ts` block may hold a basic one-line form only.
const MAX_LINES = 3;
const ALLOW_MARKER = '<!-- docs:allow-long -->';
const ROOT = resolve('.');
const SNIPPET_DIR = resolve('tests/.docs-snippets');

const docFiles = [
  resolve('.agents/skills/noct-asset-forge/SKILL.md'),
  ...readdirSync(resolve('core/brush/docs'))
    .filter(name => name.endsWith('.md'))
    .map(name => resolve('core/brush/docs', name)),
];

interface Snippet {
  file: string;
  line: number;
  code: string;
  allowLong: boolean;
}

function extractSnippets(file: string): Snippet[] {
  const lines = readFileSync(file, 'utf8').split(/\r?\n/);
  const snippets: Snippet[] = [];
  let inside = false;
  let start = 0;
  let buffer: string[] = [];
  let allowLong = false;
  let previous = '';

  lines.forEach((text, index) => {
    const trimmed = text.trim();
    if (!inside) {
      if (trimmed === '```ts') {
        inside = true;
        start = index + 1;
        buffer = [];
        allowLong = previous === ALLOW_MARKER;
      }
      if (trimmed !== '') previous = trimmed;
    } else if (trimmed === '```') {
      inside = false;
      snippets.push({ file, line: start, code: buffer.join('\n'), allowLong });
      previous = '';
    } else {
      buffer.push(text);
    }
  });

  return snippets;
}

// Imports are hoisted, `export` is dropped, and the body goes into a function so
// top-level statements compile. `ctx` is the only ambient name a snippet may use.
function toModule(code: string): string {
  const imports: string[] = [];
  const rest = code.replace(/^import[\s\S]*?from\s+['"][^'"]+['"];?/gm, match => {
    imports.push(match);
    return '';
  });
  const body = rest.replace(/^export\s+/gm, '');
  return [
    ...imports,
    'declare const ctx: CanvasRenderingContext2D;',
    'export function snippet(): void {',
    body,
    '}',
    '',
  ].join('\n');
}

const snippets = docFiles.flatMap(extractSnippets);
const problems: string[] = [];

for (const snippet of snippets) {
  const lineCount = snippet.code.split('\n').filter(line => line.trim() !== '').length;
  if (lineCount > MAX_LINES && !snippet.allowLong) {
    problems.push(`${snippet.file}:${snippet.line} has ${lineCount} lines; fenced ts blocks in guides are limited to ${MAX_LINES}.`);
  }
}

// Typecheck every snippet against the repo's own tsconfig, so `@core` paths resolve.
rmSync(SNIPPET_DIR, { recursive: true, force: true });
mkdirSync(SNIPPET_DIR, { recursive: true });
try {
  const files = snippets.map((snippet, index) => {
    const path = join(SNIPPET_DIR, `snippet-${index}.ts`);
    writeFileSync(path, toModule(snippet.code), 'utf8');
    return path;
  });

  const config = ts.readConfigFile(resolve('tsconfig.json'), ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, ROOT);
  const program = ts.createProgram(files, { ...parsed.options, noEmit: true });
  const diagnostics = ts.getPreEmitDiagnostics(program).filter(d => d.file && files.some(f => resolve(d.file!.fileName) === resolve(f)));

  for (const diagnostic of diagnostics) {
    const index = files.findIndex(f => resolve(diagnostic.file!.fileName) === resolve(f));
    const origin = snippets[index];
    const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, ' ');
    problems.push(`${origin.file}:${origin.line} does not compile: ${message}`);
  }
} finally {
  rmSync(SNIPPET_DIR, { recursive: true, force: true });
}

assert.equal(problems.length, 0, `Snippet problems:\n${problems.join('\n')}`);

console.log(`✔ ${snippets.length} snippets checked across ${docFiles.length} files.\n`);
