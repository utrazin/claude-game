# ASTRARIUM — Art Bible v1

Estado: **APPROVED (v1)** · 2026-11-25 · Fontes: AST-CA-001/002/003, AST-UI-001 e revisões em `docs/art/`.

## 1. Tese visual
"Um instrumento de precisão aceso por velas, no meio da noite." O mecanismo é a joia; a torre é o estojo; o céu é a recompensa. Tudo que brilha foi conquistado pelo jogador.

## 2. Pilares
1. **O mundo é o mostrador** — progresso se vê no mecanismo e no céu, não em números.
2. **Relojoaria real** — peças com função plausível (rodas, pinhões, pontes, pêndulo, peso, trava). Nada decorativo sem papel mecânico.
3. **Artesanato visível** — chanfros, escovado circular, parafusos azulados, gravura contida.
4. **Noite quente vs. céu frio** — contraste térmico como linguagem de progresso.

## 3. Proibições
Low poly, facetamento visível, steampunk vitoriano (canos, válvulas, cobre rebitado, cartola), rococó/volutas em excesso, neon, UI de app (cards arredondados, blur, pílulas, ícones flat), saturação de cartoon.

## 4. Paleta
| Papel | Cor | Uso |
|---|---|---|
| Latão polido | #DBB366 | rodas, ponteiros dourados, etiquetas compráveis |
| Latão envelhecido | #8C6B3A | pontes, bases, etiquetas caras demais |
| Aço azulado | #2B3F6B | parafusos, eixos, ponteiros; estados especiais da UI |
| Esmalte creme | #EDE6D6 | mostradores, texto da UI |
| Nogueira | #3A2416 | plinto, régua da UI, painéis |
| Pedra | #4A4540 | parede, piso (fria, dessaturada) |
| Chama | #FFB565 | velas, halos de hover |
| Noite | #0B1230 → #1E2A55 | céu, sombras frias |
| Estrela | #F3F0FF / #FFD9A0 | estrelas acesas / brilhantes |

Proporção alvo do quadro: 60% sombra fria, 30% latão/nogueira quente, 10% luz (chama, estrelas, reflexos).

## 5. Materiais (Godot, PBR)
- **Latão de roda:** `shaders/brass_wheel.gdshader` — metálico 0.85, rugosidade 0.28, escovado concêntrico + anisotropia tangencial, manchas de oxidação nas áreas baixas.
- **Latão de estrutura:** StandardMaterial metálico 0.82, rugosidade 0.3–0.45.
- **Aço azulado:** metálico 0.9, rugosidade 0.25, albedo #2B3F6B.
- **Esmalte:** dielétrico, rugosidade 0.15, clearcoat.
- **Nogueira:** dielétrico, rugosidade 0.45 encerada; veios via textura.
- **Pedra:** blocos de calcário (pendente textura tileable), normal suave.

## 6. Luz
- AgX, SSAO + SSIL, glow leve, neblina que não afeta o céu.
- Chave: spot quente que segue o mecanismo. Preenchimento: arandelas com chama emissiva. Contraluz: luar frio pela cúpula.
- O céu (`awake`) clareia e ganha estrelas com o progresso; a sala nunca fica clara de dia.

## 7. Formas
- Rodas: dentes ogivais, raios curvos (3–6), cubo com ressalto, chanfro em todas as arestas. Nunca menos de 24 segmentos visíveis por circunferência na distância de câmera padrão.
- Pontes e colunas: perfis torneados, capitel simples; no máximo um motivo gravado por peça.

## 8. UI (de AST-UI-001)
- **Diegética-física:** latão gravado, nogueira, esmalte, papel.
- **Odômetro:** roletes de latão com sombra interna, numerais de relojoaria; abaixo, Luz Estelar e dois mostradores de esmalte (Amplitude com zona ideal, Reserva de corda).
- **Bancada:** coluna direita ≤20% da largura sobre régua de nogueira; etiquetas de latão ~72 px (1080p) com ícone gravado, título serifado, filete, custo. Estados: comprável (polida, quente), cara demais (fosca, escura), hover (levanta 2 px + halo de chama), especial (filete aço azulado).
- **Ações:** chave de corda (botão principal, centro-baixo); cúpula (Olhar o céu, canto inferior esquerdo).
- **Tipografia:** serifada clássica (títulos), numerais tabulares; texto creme #EDE6D6.
- **Ornamento:** filete duplo + um ornamento central; cantos com parafusos. Sem volutas.
- UI total ≤30% da tela.

## 9. Câmera e composição
Órbita suave centrada no trem; enquadramento de 3/4 levemente de baixo (monumentalidade). Modo céu inclina para a cúpula. Colunas da torre emolduram o mecanismo (AST-CA-003 painel 3).

## 10. Pipeline
Modelos: `tools/blender/*.py` (bpy, procedural, GLB). Materiais e shaders na Godot. Imagens de referência: GPT Image via briefing (`GPT-IMAGE-REQUESTS.md`). NoctForge2D para ícones/ornamentos da UI. NoctForge3D não é usado para arte principal (D03).
