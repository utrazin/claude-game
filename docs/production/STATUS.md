# STATUS — documento central de continuidade

**Leia isto primeiro em qualquer nova sessão.** Atualizado: 2026-11-25 (sessão 1, fim do bloco 2).

## Fase atual
Fase 3 — Prototyping. Protótipo v0 jogável na Godot (economia v0.1). Economia sendo redesenhada (v0.4, modelo de energia) após a crítica CRIT-01.

## Aprovado (não mudar sem registro em DECISIONS.md)
- Conceito e visão: `docs/concept/V01-visao.md` (ASTRARIUM)
- Pesquisa: `docs/research/R01-mercado-idle.md`
- Referências de arte oficiais: `docs/art/approved/` (AST-CA-001 com ressalvas, 002, 003) e revisão `docs/art/REVIEW-AST-CA-001-003.md`
- Stack: Godot 4.7.2 Forward+, GDScript, Blender 5.3 (bpy), metros, Y-up
- Layout do trem horizontal (D09); modelo de energia (D10)

## Em andamento
- T-002: reimplementar `game/src/core/economy.gd` com o modelo de energia de `balance_v2.json` (o jogo ainda usa `balance.json` v0.1)
- Simulador v2: trocar política gulosa por planejador com horizonte; adicionar Grande Ano
- Look-dev: latão aprovado provisoriamente (proto-v2); faltam texturas (escovado, gravuras), parede de pedra em blocos, crank visível, peso real

## Aguardando revisão / externo
- Nada pendente com o Enzo no momento. Próximo pedido previsto: mockup de UI da bancada (U-001) e textura de pedra calcária.

## Bloqueios
- Nenhum técnico. Performance real só pode ser medida na máquina do Enzo (container renderiza por software).

## Próximas ações
1. T-002 economia v0.4 no jogo + mostradores de amplitude/corda/autonomia (prévia diegética F7).
2. Pêndulo/foliot visível no fim do trem; rotor de vento na cúpula; peso descendo de verdade.
3. Constelação com magnitude e vizinhança (F4) e Polar aberta pelo mostrador (F2).
4. Pedido U-001 (mockup da bancada) ao Enzo.
5. Áudio: tique, engate, catraca (fontes licenciadas CC0 ou síntese própria).
## Como rodar
- Jogo: `godot --path game` (editor: `godot -e --path game`)
- Simulador: `python3 tools/sim/economy.py --profile active --minutes 75`
- Gerar roda: `python3 tools/blender/gear.py --teeth 60 --spokes 5 --out <glb>` (requer `pip install bpy==5.3.0`, Python 3.13)
- Screenshots headless (Linux): `xvfb-run godot --path game ...` (precisa de `mesa-vulkan-drivers` para Forward+)
