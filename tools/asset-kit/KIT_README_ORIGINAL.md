# Game Dev Agent Skills & Procedural Asset Kit

Framework modular de **Skills para Agentes de IA** (compatível com Google Antigravity e agentes baseados no padrão `.agents/skills/`) e um **Kit Local de Produção Procedural de Assets 3D/2D**.

O objetivo deste repositório é fornecer a uma IA de codificação autônoma todas as competências especializadas necessárias para conceber, desenhar, produzir arte, programar e auditar um jogo completo de forma orquestrada e profissional.

---

## 🎮 As 8 Skills Inclusas

As skills residem em `.agents/skills/` e atuam em papéis bem definidos durante o ciclo de vida do jogo:

| Skill | Papel | Entregável Principal |
| :--- | :--- | :--- |
| **`game-orchestrator`** | Maestro do ciclo de vida, intake de parâmetros e despacho de subagentes | Coordenação geral da pipeline |
| **`game-researcher`** | Subagente isolado de pesquisa de mercado, tendências no Steam e vídeos | `references.md` |
| **`game-designer`** | Arquiteto de sistemas, Experience Map, grafo de recursos/verbos e loops | `GDD.md` |
| **`game-design-critic`** | Subagente Red Team que estressa o GDD contra mecânicas órfãs e shallow loops | Relatório de crítica com vetores A/B/C |
| **`game-art-director`** | Diretor de arte, padrões de staging espacial, arquétipos visuais e briefing de assets | `design.md` |
| **`game-asset-kit`** | Especialista em geração procedural 3D (Three.js/Manifold SDF) e 2D (Canvas) | Modelos `.glb` e texturas `.png` |
| **`game-programmer`** | Desenvolvedor do walking skeleton, gerenciador de cenas e gameplay no motor escolhido | Código-fonte do jogo |
| **`game-reviewer-qa`** | Subagente auditor que executa o jogo real e verifica todos os fluxos e estabilidade | `qa_report.md` |

---

## 🛠️ O que é a pasta `tools/asset-kit`?

A pasta `tools/asset-kit` contém o ferramental local de suporte à produção procedural de assets:
* **Geração 3D**: Three.js para malhas diretas e extrusões; Manifold 3D para operações booleanas e campos de distância assinados (SDF `levelSet`).
* **Geração 2D**: Canvas HTML5 nativo para ícones, sprites e texturas.
* **Validação Técnica**: Khronos glTF-Validator e Playwright para inspeção headless e capturas.
* **Visualizador em Tempo Real**: Servidor local HTTP + SSE que atualiza os modelos e texturas no navegador instantaneamente sem recarregar a página e preservando a câmera.
* **CLI e Lançador**: `cli.mjs` com comandos `preview`, `check`, `export`, `verify` e `launcher`.

> **Por que as ferramentas estão na raiz em `tools/`?**  
> Manter o kit em `tools/asset-kit` deixa a pasta `.agents/skills` leve e puramente descritiva (economizando tokens de contexto para os agentes), enquanto centraliza a CLI e dependências (`node_modules`) em um único local reutilizável por qualquer projeto no workspace.

---

## 📦 Pré-requisitos do Sistema

1. **Node.js 22+** instalado:
   * **Windows**: `winget install OpenJS.NodeJS.LTS` no terminal ou baixe em [nodejs.org](https://nodejs.org). *(Reinicie o terminal se o comando não for reconhecido após a instalação).*
   * **Linux**: `nvm install --lts` ou instale via NodeSource (`curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs`).
   * **macOS**: `brew install node` ou baixe em [nodejs.org](https://nodejs.org).
2. **Navegador**: Google Chrome instalado, ou Chromium via Playwright.
3. **Motor de Jogos (opcional)**: Godot 4.x, Unity, Love2D, Phaser, etc., dependendo do stack escolhido pelo usuário.

---

## 🚀 Instalação e Setup

### 1. Clonar o repositório
```bash
git clone <url-do-repositorio>
cd <pasta-do-repositorio>
```

### 2. Instalar dependências das ferramentas de assets
Navegue até a pasta `tools/asset-kit` e instale as dependências:

```bash
cd tools/asset-kit
npm ci
```
*(Caso prefira usar o Chromium do Playwright em vez do Chrome instalado na máquina, execute também: `npx playwright install chromium`)*

### 3. Verificar a instalação
Execute os testes automatizados a partir da raiz do repositório:

```bash
node --test tools/asset-kit/kit.test.mjs
```
Todos os testes de exportação, validação e preview ao vivo devem passar com sucesso (`pass 2, fail 0`).

---

## 🕹️ Como Usar com Antigravity / Agentes de IA

### Fluxo Padrão (Starter Kit)
1. Abra este repositório como seu workspace no Antigravity ou em seu assistente de IA preferido.
2. Inicie uma conversa pedindo para criar um jogo, por exemplo:
   > *"Quero criar um jogo idle incremental de fazenda em Godot 4 com visão isométrica."*
3. O agente ativará o **`game-orchestrator`**, que fará uma única pergunta de **Intake**:
   - Motor/Linguagem (ex: Godot 4 / GDScript, Web / TypeScript).
   - Pasta de assets do projeto.
   - Unidade de medida (ex: 1 unidade = 1 metro).
   - Escopo (`prototype`, `vertical_slice` ou `small_complete`).
   - Preferências de estilo de arte.
4. O agente executará o pipeline em fases:
   - Pesquisa de referências (`game-researcher`).
   - Design detalhado (`game-designer` + `game-design-critic`).
   - Direção de arte e tabela de briefing de assets (`game-art-director`).
   - Produção de modelos 3D e texturas em paralelo com o walking skeleton (`game-asset-kit` + `game-programmer`).
   - Auditoria e testes de execução com relatório de aprovação (`game-reviewer-qa`).

### Visualizando os Assets no Navegador
Na pasta do seu projeto (ou na pasta de exemplo `examples/estudo-kit-assets/`):
- Dê dois cliques em `Abrir Visualizador.bat`, ou
- Execute na raiz do repositório:
  ```powershell
  node tools/asset-kit/cli.mjs preview "examples/estudo-kit-assets" --open
  ```

---

## 📁 Estrutura do Repositório

```text
├── .agents/
│   └── skills/                  # Pacote das 8 skills especializadas para agentes
│       ├── game-orchestrator/   # Orquestrador mestre e contrato de handoff
│       ├── game-researcher/     # Pesquisa de mercado e referências
│       ├── game-designer/       # GDD, Experience Map e presunções de tuning
│       ├── game-design-critic/  # Red-team e revisão de coerência sistêmica
│       ├── game-art-director/   # Direção de arte, staging e arquétipos visuais
│       ├── game-asset-kit/      # Guia de técnicas procedurais (Three.js/Manifold)
│       ├── game-programmer/     # Implementação do jogo e walking skeleton
│       └── game-reviewer-qa/    # Auditoria com execução real do jogo
├── examples/
│   └── estudo-kit-assets/       # Projeto de exemplo e fixture de testes de assets
│       ├── Abrir Visualizador.bat
│       ├── asset-workbench/     # Fontes dos geradores JS e checks de validação
│       └── assets/              # Arquivos finais gerados (.glb e .png)
├── tools/
│   └── asset-kit/               # Ferramental local (CLI, Servidor SSE, Viewer web)
│       ├── cli.mjs
│       ├── server.mjs
│       ├── viewer.js / viewer.css / index.html
│       ├── kit.test.mjs
│       └── package.json
├── .gitignore                   # Regras de exclusão para Git e caches de engines
└── README.md                    # Documentação principal e guia de instalação
```
