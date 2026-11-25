# STATUS — documento central de continuidade

**Leia isto primeiro em qualquer nova sessão.** Atualizado: 2026-11-25 (sessão 1).

## Fase atual
Fase 2 — Pre-production (Fase 1 Discovery concluída). Protótipo técnico do core loop começando em paralelo.

## Aprovado (não mudar sem registro em DECISIONS.md)
- Conceito e visão: `docs/concept/V01-visao.md` (ASTRARIUM)
- Pesquisa de mercado: `docs/research/R01-mercado-idle.md` (APPROVED com ressalvas: itens marcados "não verificado")
- Stack: Godot 4.7.2 Forward+, GDScript, Blender 5.3 (bpy) para modelos, unidades em metros, Y-up
- Economia v0.3 como base de protótipo: `game/data/balance.json`

## Em andamento
- GDD v0.1 (IN REVIEW, falta rodada do game-design-critic)
- Art Bible v0 (BRIEFING; depende dos concepts AST-CA-001..003)
- Protótipo Godot do core loop (IN PROGRESS)

## Aguardando revisão / externo
- GPT Image: AST-CA-001, 002, 003 enviados ao Enzo (`docs/art/GPT-IMAGE-REQUESTS.md`)

## Bloqueios
- Nenhum técnico. Performance real só pode ser medida na máquina do Enzo (container renderiza por software).

## Próximas ações
1. Protótipo jogável: trem de engrenagens procedural, peso, corda, compra, save/load, offline.
2. Crítica independente do GDD.
3. Avaliar concepts recebidos → Art Bible v1.
4. Biblioteca de rodas (Blender) com bevel + materiais PBR calibrados.

## Como rodar
- Jogo: `godot --path game` (editor: `godot -e --path game`)
- Simulador: `python3 tools/sim/economy.py --profile active --minutes 75`
- Gerar roda: `python3 tools/blender/gear.py --teeth 60 --spokes 5 --out <glb>` (requer `pip install bpy==5.3.0`, Python 3.13)
- Screenshots headless (Linux): `xvfb-run godot --path game ...` (precisa de `mesa-vulkan-drivers` para Forward+)
