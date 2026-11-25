# C01 — Exploração de conceitos

Estado: IN REVIEW (decisão final depende do relatório R01)
Autor: Game Director · 2026-11-25

Restrições fixas: idle/incremental, 3D, Godot 4.7, sem estética low poly. Critério extra do diretor: **o mundo 3D precisa ser o mostrador do progresso**, não um fundo para uma planilha.

## Capacidade real de produção (o que o estúdio consegue fazer bem)

Verificado nesta sessão, não presumido:

- **Blender 5.3 como módulo Python (bpy)** roda headless no container. Permite modelagem procedural com booleanas exatas, bevel, weighted normals, UV e exportação GLB. Spike: roda de relógio de 60 dentes com raios curvos, bevel e cubo central (`tools/blender/gear.py`, imagem em `docs/devlog/2026-11-25_spike-engrenagem-v1.png`).
- **Godot 4.7.2 Forward+** renderiza headless via Vulkan por software (lavapipe). Screenshots automatizadas funcionam. Performance real só pode ser medida na máquina do Enzo.
- **Kits procedurais** (asset-kit Three.js/Manifold, NoctForge 2D) passam nos próprios testes. NoctForge 3D é baseado em BBModel (cubos estilo Blockbench), o que conflita com a restrição de não ser low poly; uso limitado a casos específicos.
- **GPT Image via Enzo** para concept art, key art, mockups de UI e texturas base.

Consequência: superfícies **hard-surface** (metal, madeira, vidro, pedra trabalhada) e **animação mecânica** são o ponto forte. Personagens orgânicos animados e vegetação densa são o ponto fraco.

## Candidatos

| # | Conceito | Fantasia | Como o mundo mostra o progresso |
|---|---|---|---|
| A | **Astrarium** (relógio astronômico) | Último relojoeiro de uma torre-observatório reconstrói, engrenagem a engrenagem, a máquina que move o céu | O mecanismo cresce fisicamente, sobe pelos andares da torre; cada complicação reacende um corpo celeste na cúpula |
| B | Terrário selado | Cultivar um ecossistema inteiro dentro de um frasco de vidro | O frasco se enche de musgo, fungos, névoa, insetos |
| C | Erosão / tempo profundo | Ser o clima que esculpe uma paisagem ao longo de eras | O terreno deforma: rios, cânions, vida |
| D | Farol na tempestade | Manter um farol que guia navios e cresce em uma vila costeira | Vila cresce, navios chegam |
| E | Recife abissal | Fazer crescer um recife bioluminescente | Corais e criaturas ocupam o fundo |

## Avaliação (1–5)

| Critério | A Astrarium | B Terrário | C Erosão | D Farol | E Recife |
|---|---|---|---|---|---|
| Originalidade | 4 | 3 | 5 | 2 | 3 |
| Potencial de diversão (decisões reais) | 5 | 3 | 2 | 3 | 3 |
| Identidade visual reconhecível | 5 | 4 | 4 | 3 | 3 |
| Mundo como mostrador do progresso | 5 | 5 | 5 | 3 | 4 |
| Profundidade / expansão | 4 | 3 | 3 | 3 | 3 |
| Viabilidade técnica com nosso pipeline | 5 | 2 | 3 | 3 | 2 |
| Custo de produção de arte (5 = barato) | 4 | 2 | 3 | 2 | 2 |
| Risco de clichê (5 = baixo) | 3 | 4 | 5 | 2 | 2 |
| **Total** | **35** | 26 | 30 | 21 | 22 |

### Por que A vence

1. **A mecânica nasce do tema.** Num trem de engrenagens, a relação de dentes multiplica velocidade e divide força. Isso vira uma economia incremental real e legível: produção = rotação que se propaga pelo trem. Escolher entre velocidade e torque é uma decisão significativa, não um botão de "+10%".
2. **O idle tem justificativa na ficção.** Um relógio funciona sozinho; é automação literal. O progresso offline pode ser limitado pela **corda principal (mainspring)**: quanto mais corda você instala, mais tempo a máquina trabalha sem você. É um limite com motivo, não uma trava arbitrária.
3. **Animação fluida de graça.** Rotação mecânica é perfeita por definição, e quanto mais o jogador evolui, mais o mundo se mexe.
4. **Forte em hard-surface**, exatamente onde o pipeline Blender procedural rende qualidade alta (bevels, latão, esmalte, vidro, madeira).
5. **Imagem reconhecível numa captura de tela**: latão quente contra azul noturno, uma máquina enorme e viva sob uma cúpula de estrelas.

### Riscos de A e mitigação

- **Clichê steampunk** (cartola, vapor, rebites, sépia). Mitigação: referência histórica e astronômica, não vitoriana industrial. Astrário de Giovanni Dondi (séc. XIV), relógio astronômico de Praga, relógio da catedral de Estrasburgo, mecanismo de Anticítera, orreries do séc. XVIII. Nada de vapor, nada de rebites decorativos.
- **Monotonia de material** (tudo latão). Mitigação: Art Bible com hierarquia de materiais (latão, aço azulado, esmalte, madeira, vidro, pedra da torre, céu).
- **Leitura da UI** num mundo cheio de peças girando. Mitigação: câmera com enquadramentos definidos e UI diegética quando possível.

### Por que não C (segunda colocada)

Tema mais original, mas o verbo do jogador é vago ("ser o clima"): difícil produzir decisões significativas a cada minuto. Fica registrada como ideia para outro projeto.

## Decisão provisória

Conceito A, título de trabalho **ASTRARIUM**. Confirmar após R01 que não existe concorrente direto em 3D com a mesma proposta, e checar o nome.
