# Revisão de Art Direction: AST-CA-001, 002, 003 (v1)

Data: 2026-11-25 · Revisor: Game Director / Art Director

## AST-CA-002 Estudo de materiais: APPROVED (referência oficial de materiais)
- Latão escovado com raios curvos: idêntico em intenção ao gerador `tools/blender/gear.py`. Valida a linguagem de forma das rodas.
- Aço azulado com variação azul-violeta de têmpera: exatamente o acento frio que o jogo precisa. Vira regra: **todo pinhão, parafuso e eixo visível é aço azulado**.
- Esmalte com craquelê fino e anel guilloché, placa gravada com pátina nas cavidades, nogueira com filete de latão, lápis-lazúli com pirita: todos aprovados como alvo de shader.
- Ressalva: os numerais pintados são decoração de referência; no jogo os mostradores terão numerais gerados por nós (texto correto).

## AST-CA-003 Tira de progressão: APPROVED (especificação dos estados do mundo)
- Os quatro estados leem claramente: silêncio → primeiro tique → máquina viva → firmamento. A cúpula abrindo em gomos e as constelações em linhas douradas finas estão certas.
- **Decisão derivada (D09):** o trem começa **horizontal**, sobre uma base de nogueira, com rodas diminuindo da esquerda para a direita e o pêndulo num pórtico (painel 2). Só depois ganha a estrutura vertical de pilares e mostradores (painéis 3 e 4). O layout em zigue-zague vertical do protótipo atual está REJECTED.
- Ressalvas: a arquitetura da sala muda entre painéis (normal em concept); o painel 4 tem dourado demais em tudo, o que apaga a hierarquia de materiais.

## AST-CA-001 Key art: APPROVED COM RESSALVAS (referência de atmosfera e composição, não de acabamento)
- Aprovado: paleta latão × ultramar, cúpula de vidro com nervuras de ferro, mostrador de fases da Lua, braços planetários com lápis, prata e âmbar, primeiro plano escuro com bancada, luz quente baixa e fria alta.
- Ressalvas (não reproduzir no jogo):
  - Saturação e "brilho dourado" generalizados, com cara de render de fantasia genérico. No jogo o latão precisa de áreas escuras e reflexos frios; o dourado vem só dos realces.
  - Aço azulado quase ausente; deveria ser o segundo material mais visível.
  - Hera nas paredes e excesso de objetos de cenário: poluição visual. Sala mais sóbria.
  - Janelas góticas compridas competem com a cúpula. Manter poucas aberturas baixas.

## Comparação com o protótipo atual (`docs/devlog/2026-11-25_proto-v0.png`)
O protótipo está **longe** do alvo. Problemas identificados:
1. Monocromático laranja: luz quente forte demais, sem contraluz fria, latão parecendo cobre.
2. Falta reflexo: metal sem nada para refletir parece plástico laranja.
3. A placa de nogueira atrás domina a imagem.
4. Layout em zigue-zague faz rodas se sobreporem visualmente (REJECTED, ver D09).
5. Sala de placeholder sem cúpula, sem céu.
Próximo passo: look-dev de iluminação e materiais contra AST-CA-001/002 antes de qualquer novo asset.
