# Revisão — AST-UI-001 (mockup da interface)

- **Arquivo:** `docs/art/approved/AST-UI-001.png` (1672×941)
- **Veredito:** **APPROVED com ressalvas** — aprovado como referência de linguagem da UI, não para reprodução literal.

## O que acerta (adotar)
1. **Odômetro de roletes** de latão em moldura gravada: exatamente a leitura que queremos para o contador principal. Algarismos em cilindros com sombra interna.
2. **Mostradores de esmalte creme com ponteiro de aço azulado**: confirma o vocabulário (esmalte + aço azul) e a escala (dois mostradores menores que o odômetro).
3. **Etiquetas da Bancada com três estados legíveis**: polida (comprável), latão escurecido (caro demais), etiqueta levantada com halo quente (hover). Hierarquia ícone gravado → título → filete → custo funciona.
4. **Régua de nogueira** atrás da coluna direita: amarra a UI ao mundo (diegética-física).
5. **Chave de corda** como botão principal: forma única, imediatamente legível como "dar corda". Vira o ícone/assinatura do jogo.
6. **Botão do Observatório** com cúpula gravada: bom equivalente para "Olhar o céu".

## O que corrigir (não adotar)
1. **Ornamentação excessiva.** Volutas, folhagens e cartuchos em todas as molduras puxam para rococó / vitoriano — conflita com a restrição "sem steampunk vitoriano" e com "ornamentação contida" do briefing. Regra: no máximo **um** motivo gravado por peça (filete duplo + um pequeno ornamento central). Cantos com parafusos, não volutas.
2. **Área de tela.** Coluna direita ~25% + odômetro + mostradores + botões passam dos 30%. Na implementação: coluna 20%, etiquetas mais baixas (~72 px a 1080p), odômetro mais compacto.
3. **Semântica dos mostradores.** "Eficiência %" não existe no jogo; os mostradores são **Amplitude** (arco com zona ideal) e **Reserva de corda**. Falta a linha de **Luz Estelar**.
4. **Densidade de cena.** O mecanismo e o cenário do mockup (telescópio, livros, esfera armilar) são mais cheios que o nosso; não é meta para a UI, mas os props (esfera armilar, telescópio, mapa celeste emoldurado) entram no backlog de cenário.
5. **Fundo das etiquetas** muito saturado/dourado quando todas estão polidas; usar latão mais frio (ver paleta) e reservar o brilho quente para hover e "comprável".

## Consequências
- Entra no Art Bible v1 (`docs/art/ART-BIBLE.md`, §UI).
- Implementação: skin da UI como `Theme` + texturas geradas proceduralmente (StyleBoxTexture com nine-patch), sem pedir mais imagens por ora.
