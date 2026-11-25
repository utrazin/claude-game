# Registro de decisões

Decisões aqui não mudam sem uma nova entrada que explique o motivo.

| # | Data | Decisão | Motivo | Evidência |
|---|---|---|---|---|
| D01 | 2026-11-25 | Engine Godot 4.7.2 stable, renderer Forward+ | versão estável mais recente disponível; Forward+ dá SSAO, SSR, sombras e materiais PBR que o latão precisa | `godot --version`; teste Forward+ via lavapipe |
| D02 | 2026-11-25 | Conceito: ASTRARIUM (relógio astronômico) | maior nota na exploração C01; nicho aberto segundo R01 (nenhum idle 3D com ambiente premium como mostrador; idles de engrenagem são 2D e temáticos apenas) | `docs/concept/C01`, `docs/research/R01` |
| D03 | 2026-11-25 | Arte 3D principal via Blender (bpy 5.3) procedural, não via NoctForge3D | NoctForge3D gera BBModel (cubos estilo Blockbench), incompatível com a restrição de não ser low poly; bpy permite booleanas exatas, bevel, weighted normals e GLB | spike `docs/devlog/2026-11-25_spike-engrenagem-v1.png` |
| D04 | 2026-11-25 | NoctForge 2D e asset-kit ficam para ícones, texturas procedurais e assets de UI | ambos passam nos testes e são bons em 2D/Canvas | logs de teste da sessão 1 |
| D05 | 2026-11-25 | Relação de cada estágio é limitada (máx. 120 dentes) | versões ilimitadas explodiram no simulador; o limite também é físico e visível | GDD §8 |
| D06 | 2026-11-25 | Estrelas dão bônus aditivo, constelação multiplica | estrelas multiplicativas criaram loop de realimentação | GDD §8 |
| D07 | 2026-11-25 | UI em inglês como base com tradução PT-BR via `tr()` desde o início | público Steam global; o diretor de produto fala português | — |
| D08 | 2026-11-25 | Sem estética steampunk vitoriana | evitar clichê; referência é horologia astronômica histórica | V01 |
| D09 | 2026-11-25 | Trem começa horizontal sobre base de nogueira (rodas diminuindo da esquerda para a direita) e ganha estrutura vertical depois | AST-CA-003 painel 2; o zigue-zague do protótipo sobrepõe rodas | REVIEW-AST-CA-001-003 |
| D10 | 2026-11-25 | Resposta à CRIT-01. F1/F3/F6/F8: ADOPT A, modelo único **regulador + trem + energia do peso** (relação dá autonomia e reduz torque; peso é energia armazenada; corda enche o peso até a trava de corda). F2: FUSE A+B (escape/regulador é peça inicial; mostrador abre a fresta da cúpula e a Polar cedo). F4: FUSE A+B (constelações com magnitude, vizinhança e bônus de regra; regiões do céu abertas pelas órbitas). F5: FUSE A+B (cada Grande Ano é uma invenção da relojoaria com o material como pele; o céu permanece aceso entre ciclos, só a máquina é refeita). F7: ADOPT A (prévia diegética antes da compra) e trocar o simulador guloso por planejador com horizonte | crítica com evidência de simulação: estratégia dominante, clique domina +300%, céu linear, Lua tarde | docs/design/CRIT-01-gdd-v0.1.md |
