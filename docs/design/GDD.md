# GDD — ASTRARIUM

Versão 0.1 · Estado: IN REVIEW (falta crítica independente do `game-design-critic`) · Dono: Game Design
Balanceamento: `game/data/balance.json` (fonte única) · Simulador: `tools/sim/economy.py`

## 1. Resumo e loops

- **Gênero / perspectiva:** idle/incremental 3D, câmera orbital em torno de um mecanismo, sala única que se transforma.
- **Escopo atual:** vertical slice (VS), cerca de 45–60 min de jogo ativo até o primeiro Grande Ano.
- **Core loop (segundos):** observar o mecanismo girar e os Tiques chegarem → dar corda (clique/segurar) quando quer acelerar → comprar o próximo dente, roda ou peso → ver a peça crescer, engatar e o ritmo do tique mudar.
- **Session loop (minutos):** equilibrar **relação** (rodas maiores) e **força motriz** (peso mais pesado) para o trem não perder eficiência → construir a próxima complicação → acender estrelas na cúpula com Luz Estelar.
- **Meta loop:** completar constelações → concluir um **Grande Ano** (prestígio) → ganhar Éons e um novo material para a máquina → recomeçar mais rápido com novas regras.
- **Teste do minuto 10:** no minuto 1 o jogador clica a manivela e compra dentes de uma roda. No minuto 10 ele administra três estágios, o equilíbrio peso × carga e já viu a Lua surgir; está decidindo entre o quarto estágio e níveis da Lua.

## 2. Mapa de experiência

| ID | Tipo | Propósito | Verbos únicos | Entra / sai | Câmera / layout | Lê / escreve |
|---|---|---|---|---|---|---|
| S1 Torre | cena | o jogo inteiro acontece aqui | dar corda, inspecionar peça, comprar, construir complicação, olhar o céu | inicial | órbita livre limitada ao redor do mecanismo; zoom em peças | todo o estado |
| P1 Painel da Bancada | tela (overlay) | compras do trem e da força motriz | comprar nível, desbloquear estágio, subir peso | sempre visível, recolhível | faixa inferior/lateral diegética (régua de latão sobre nogueira) | Tiques, níveis |
| P2 Ficha da peça | tela (overlay contextual) | entender uma peça: dentes, relação, carga, próximo refinamento | inspecionar, comprar daquela peça | clicar numa roda | cartão de papel antigo preso por alfinete perto da peça | leitura |
| P3 Cúpula / carta celeste | modo de câmera | árvore de upgrades no céu | acender estrela, ler constelação | botão "olhar para cima" / scroll para cima | câmera sobe e olha a cúpula; estrelas clicáveis | Luz Estelar, estrelas |
| P4 Caderno do relojoeiro | tela | onboarding, objetivos, lore curta, estatísticas | ler, acompanhar marcos | botão; abre automaticamente em marcos | livro aberto sobre a bancada | marcos |
| P5 Grande Ano | tela de transição | prestígio: resumo, Éons, escolha do próximo material | confirmar, escolher ofício | quando requisito cumprido | sequência cinematográfica + livro | Éons, era |
| P6 Retorno | tela curta | mostrar o que aconteceu offline | coletar | ao abrir o jogo após ausência | o peso desceu; números sobem no mostrador | tempo offline |
| U Configurações | utilitário | volume, gráficos, idioma, resolução | — | menu | — | config |

Fluxo: S1 é a base. P1 e P2 sobrepõem S1. P3 é S1 com outra câmera. P4/P5/P6 abrem sobre S1 e voltam a S1.

## 3. Verbos

| Verbo | Entrada | Mudança de estado | Feedback | Onde aparece |
|---|---|---|---|---|
| Dar corda | clique ou segurar na manivela | +Tiques imediatos (1 s de produção + 1); ao segurar por 1,5 s, **Sobrecorda** (×1,5 por 8 s) | manivela gira, catraca estala, ponteiro de reserva sobe | manivela 3D na base do mecanismo |
| Comprar dente (nível) | botão na bancada ou na ficha | roda ganha 6 dentes: relação +0,5 | a roda é substituída por uma maior com animação de engate; som de encaixe | P1, P2, mundo |
| Desbloquear estágio | botão | nova roda entra no trem; relação total × nova relação | a roda desce de cima e engata; câmera faz um pequeno enquadramento | P1, mundo |
| Subir peso | botão | força motriz × 1,5 | um novo disco de chumbo é pendurado; corrente desce mais | P1, mundo (poço do peso) |
| Construir complicação | botão | ativa efeito (×2 global, produção de Luz Estelar) | peça monumental sobe/encaixa; corpo celeste reaparece na cúpula | P1, mundo, cúpula |
| Acender estrela | clique na estrela | +50% produção global (aditivo); 7 estrelas = constelação (×2) | linha dourada liga estrelas; acorde de celesta | P3 |
| Inspecionar | clique numa peça | nenhuma | ficha da peça | P2 |
| Grande Ano | botão no caderno | reset de rodas, peso, complicações, Tiques; ganha Éons | sequência: máquina se desmonta em ordem e a luz muda | P5 |

## 4. Recursos

| Recurso | Fonte | Sumidouro | Onde se vê |
|---|---|---|---|
| **Tiques** | escape do trem (tiques/s = base × Π relações × eficiência × multiplicadores); corda | dentes, estágios, peso, complicações, reserva | mostrador principal (odômetro de latão) e ritmo do som |
| **Força motriz** (estado) | nível do peso | consumida pela **carga** (Σ níveis × carga do estágio) | ponteiro de força no mostrador do peso |
| **Eficiência** (estado) | min(1, força/carga)^1,5 | — | ponteiro do mostrador; trem gira visivelmente mais devagar e o tique fica arrastado quando < 1 |
| **Luz Estelar** | complicações celestes: coef × nível × (tiques/s)^0,4 | estrelas | frasco/ampulheta de luz na bancada; partículas subindo à cúpula |
| **Estrelas / constelações** | compradas com Luz Estelar | — (bônus permanentes até o Grande Ano) | cúpula |
| **Reserva de corda** (offline) | nível da reserva (horas) | tempo ausente | comprimento do poço do peso; tela P6 |
| **Éons** | Grande Ano: floor(√(Luz Estelar total / 50)) | ofícios permanentes | caderno, material da máquina |

Checagem de órfãos: todos os recursos têm fonte, sumidouro e lugar no mundo. Estrelas não têm sumidouro dentro de um ciclo por design (são investimento).

## 5. Fórmulas (v0.3, provisórias)

- Relação de um estágio: `dentes / 12`, com `dentes = 12 + 6·(nível−1)`, nível máximo 19 (120 dentes, relação 10).
- Custo de nível: `custo0 · crescimento^nível` (crescimento 1,30–1,34 por estágio).
- **Decisão de design:** relação por estágio é **limitada** (uma roda não cresce para sempre: é física e é visível). O crescimento contínuo vem de novos estágios, complicações, estrelas e Éons. Duas versões anteriores (sem limite) explodiram numericamente no simulador (ver §8).
- Carga: `Σ nível_i · carga_i` com cargas 1, 3, 9, 27, 81. Força: `3 · 1,5^peso`.
- Eficiência: `min(1, força/carga)^1,5`.
- Luz Estelar/s: `Σ coef · nível · (tiques/s)^0,4`.
- Estrelas: custo `15 · 2,3^n`; +50% aditivo cada; constelação de 7 dá ×2.
- Offline: 100% da produção até o limite da reserva (1 h inicial, +1 h por nível).

## 6. Grande Ano (prestígio)

Requisito no VS: 1 constelação completa e Mercúrio construído. Mantém: Éons, estrelas compradas como "memória" (decisão pendente de teste: manter 1 constelação acesa ou todas), caderno. Reseta: Tiques, rodas, peso, complicações. Éons compram **ofícios** (ex.: começar com o segundo estágio, rodas 10% mais baratas, sobrecorda mais longa) e cada Grande Ano troca o material da máquina (latão → aço azulado → ouro → cristal) com pequenas regras novas por material (ex.: aço reduz carga, ouro aumenta Luz Estelar). Cada ciclo precisa trazer uma regra nova, não só um número maior (lição da pesquisa R01).

## 7. Eventos previsíveis

**Conjunções:** a cada ~4 minutos, dois corpos celestes se alinham; o almanaque (mostrador) mostra a contagem. Clicar na conjunção durante a janela de 20 s dá 60 s de produção de Luz Estelar. Não há perda ao ignorar. Entra depois do VS se o core loop já estiver sólido.

## 8. Simulação (evidência)

`python3 tools/sim/economy.py --profile <active|casual|idle> --minutes N` (política gulosa de melhor retorno).

| Versão | Resultado | Decisão |
|---|---|---|
| v0.1 | estrelas multiplicativas → 3e23 tiques/s em 60 min | REJECTED: estrelas passam a ser aditivas |
| v0.2 | sem marcos → terceiro estágio só aos 48 min | REJECTED: lento demais |
| v0.2b | marcos ×2 a cada 10 níveis → overflow numérico (cinco estágios multiplicando) | REJECTED: relação limitada por estágio |
| v0.3 | ativo: centro 0,8 min, 3º 6,8 min, Lua 13,7, 1ª constelação 26, 4º 27, Mercúrio 40,7. Casual: 3º 18,8 min, Lua 36, 1ª constelação 52 | APPROVED como base de protótipo; revalidar com playtest |

Problemas conhecidos: intervalo 1–7 min com só um tipo de compra (risco de monotonia no início, mitigar com a Lua anunciada e com refinamentos visuais); depois dos 60 min sem prestígio ainda não modelado, as compras rareiam (esperado: é onde entra o Grande Ano).

## 9. Onboarding

Sem tutorial em texto longo. Uma vela, uma roda na bancada, a manivela pulsando suavemente. Primeira corda → primeiro tique audível. O caderno do relojoeiro anterior abre com uma frase curta por marco ("O ponteiro das horas lembra o mundo de que o tempo existe.").

## 10. Decisões de design

Ver `docs/production/DECISIONS.md`.
