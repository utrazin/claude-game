# ASTRARIUM — instruções do repositório

Jogo idle/incremental 3D em Godot 4.7. Antes de qualquer trabalho, leia `docs/production/STATUS.md` (estado, aprovados, próximas ações) e `docs/production/DECISIONS.md`.

- Jogo: `game/` (projeto Godot). Balanceamento só em `game/data/balance.json`.
- Docs: `docs/` (concept, design, art, tech, production, research, devlog). Idioma dos docs: português.
- Skills: `.agents/skills/` (pipeline de game dev) e skills das ferramentas em `tools/noct-forge-2d/.agents/skills` e `tools/noct-forge-3d/.agents/skills`; todas linkadas em `.claude/skills/`.
- Os comandos das skills NoctForge assumem o diretório da ferramenta como cwd (`tools/noct-forge-2d` ou `tools/noct-forge-3d`). Em Linux use `python3` no lugar de `py -3.12`.
- NoctForge3D gera modelos de cubos (BBModel): não usar para arte principal (restrição: nada de low poly). Ver D03.
- Restrições inegociáveis: 3D, Godot, idle/incremental, sem estética low poly, sem steampunk vitoriano.
