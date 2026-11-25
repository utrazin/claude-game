# STATUS — documento central de continuidade

**Leia isto primeiro em qualquer nova sessão.** Atualizado: 2026-11-25 (sessão 1, bloco 3).

## Fase atual
Fase 3 — Prototyping. Protótipo v4 jogável: economia v0.4 (energia: peso, corda, regulador, rotor), pêndulo visível, céu com constelação Clavis clicável, áudio procedural, testes headless (18/18). Playtest 1 do Enzo respondido em D11–D14 (remontoir, presets gráficos, plano do céu, áudio v2). proto-v5: 61 FPS no Médio no PC do Enzo (D12 validado). proto-v6 com D15 e proto-v7 com UI v1 enviadas.

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
- Enzo: reteste da `Astrarium-proto-v5.zip` (FPS com F3, áudio, plano do céu). Playtest 1: 20 FPS em Ryzen integrado, áudio "meia boca", céu "transição de navegador", corda parou de responder após a 4ª compra.

## Bloqueios
- Nenhum técnico. Performance real só pode ser medida na máquina do Enzo (container renderiza por software).

## Próximas ações
1. UI v1 feita (proto-v7: `src/ui/hud.gd`, `gauge.gd`, texturas de `tools/ui/gen_ui.py`, fonte EB Garamond OFL). Falta: menu principal, opções, tutorial curto.
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
