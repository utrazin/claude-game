# STATUS — documento central de continuidade

**Leia isto primeiro em qualquer nova sessão.** Atualizado: 2026-11-25 (sessão 1, bloco 3).

## Fase atual
Fase 3 — Prototyping. Protótipo v4 jogável: economia v0.4 (energia: peso, corda, regulador, rotor), pêndulo visível, céu com constelação Clavis clicável, áudio procedural, testes headless (18/18). Build Windows exportada para teste de desempenho/áudio na máquina do Enzo.

## Aprovado (não mudar sem registro em DECISIONS.md)
- Conceito e visão: `docs/concept/V01-visao.md` (ASTRARIUM)
- Pesquisa: `docs/research/R01-mercado-idle.md`
- Referências de arte oficiais: `docs/art/approved/` (AST-CA-001 com ressalvas, 002, 003, AST-UI-001 com ressalvas) e revisões em `docs/art/REVIEW-*.md`
- **Art Bible v1:** `docs/art/ART-BIBLE.md`
- Stack: Godot 4.7.2 Forward+, GDScript, Blender 5.3 (bpy), metros, Y-up
- Layout do trem horizontal (D09); modelo de energia (D10)

## Em andamento
- Simulador v2: trocar política gulosa por planejador com horizonte; adicionar Grande Ano
- Look-dev: latão aprovado provisoriamente (proto-v2); faltam texturas (escovado, gravuras), parede de pedra em blocos, crank visível, peso real

## Aguardando revisão / externo
- Enzo: rodar `Astrarium-proto-v4.exe` (em /mnt/project-files/astrarium/) e informar FPS, GPU e impressão do áudio.

## Bloqueios
- Nenhum técnico. Performance real só pode ser medida na máquina do Enzo (container renderiza por software).

## Próximas ações
1. Skin da UI conforme Art Bible §8 (odômetro de roletes, mostradores, etiquetas, chave de corda) — substitui o placeholder.
2. Rotor de vento na cúpula; peso e corrente reais; manivela visível; textura de pedra em blocos.
3. Constelação com magnitude e vizinhança (F4) e Polar aberta pelo mostrador (F2).
4. Simulador v2 com planejador e Grande Ano; Lua em ≤15 min.
5. Menu de opções (volume, gráficos, idioma).
- Build: `cd game && godot --headless --export-release "Windows Desktop" ../build/windows/Astrarium.exe` (templates 4.7.2 em ~/.local/share/godot/export_templates).
## Como rodar
- Jogo: `godot --path game` (editor: `godot -e --path game`)
- Simulador: `python3 tools/sim/economy.py --profile active --minutes 75`
- Gerar roda: `python3 tools/blender/gear.py --teeth 60 --spokes 5 --out <glb>` (requer `pip install bpy==5.3.0`, Python 3.13)
- Screenshots headless (Linux): `xvfb-run godot --path game ...` (precisa de `mesa-vulkan-drivers` para Forward+)
