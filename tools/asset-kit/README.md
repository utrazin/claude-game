# Kit local de assets

Ferramentas de produção em HTML/JavaScript, sem dependência do kit no jogo final. Three.js gera/visualiza/exporta malhas; Manifold cobre sólidos e SDF; Canvas nativo gera PNG; Khronos valida GLB; Playwright automatiza o navegador. Versões estão fixadas no lockfile.

A orientação para agentes está na [skill game-asset-kit](../../.agents/skills/game-asset-kit/SKILL.md), com decisão de estilo/técnica e separação entre arquivos exportáveis e efeitos de runtime. O [contrato](../../.agents/skills/game-orchestrator/references/asset_handoff.md) prefere GLB/PNG e não exige um manifesto no jogo.

## Operação

**Padrão no Windows:** dê dois cliques em `Abrir Visualizador.bat` na pasta do projeto. Para criar o lançador em outro projeto, use `node tools/asset-kit/cli.mjs launcher "<projeto>"` da raiz. A primeira janela mantém o servidor; aberturas seguintes reutilizam o mesmo servidor. Assets reexportados e novas entradas de `assets.json` atualizam o visualizador sem recarregar a página e sem perder a câmera do modelo atual. O botão de download salva uma cópia; a exportação para os caminhos do projeto continua sendo feita pela CLI.

Node 22+ e Chrome instalado, ou Chromium do Playwright. Para restaurar dependências, execute `npm ci` nesta pasta. Se necessário, `npx playwright install chromium`. A instalação atual já foi testada com Chrome.

Da raiz do repositório:

```powershell
node tools/asset-kit/cli.mjs preview "examples/estudo-kit-assets"
node tools/asset-kit/cli.mjs check "examples/estudo-kit-assets"
node tools/asset-kit/cli.mjs export "examples/estudo-kit-assets" sdf_rock
node tools/asset-kit/cli.mjs verify "examples/estudo-kit-assets"
```

`preview` imprime o endereço local. `export`/`check` geram e verificam; `verify` verifica arquivos existentes. O ID opcional limita a operação. Fontes, lista de exportação e evidências ficam no projeto; arquivos finais ficam em `assets`. Não é necessário copiar o kit ou suas dependências para cada projeto. O servidor aceita conexões apenas de localhost e não possui endpoint de escrita; a CLI salva os downloads.

Consulte [operations.md](../../.agents/skills/game-asset-kit/references/operations.md) para interface dos geradores, exemplos, limites de SDF, material e animação. O adaptador Manifold transfere posições/índices e recalcula normais; UVs, cores e vários materiais exigem mapeamento próprio. A inspeção automática deixa `visualReview: pending` deliberadamente: o agente deve abrir as capturas e testar animações/importação no destino.

Para verificar a ferramenta: `node --test tools/asset-kit/kit.test.mjs`, da raiz. O teste usa cópias temporárias do estudo de caso e verifica falhas reais de entrega.
