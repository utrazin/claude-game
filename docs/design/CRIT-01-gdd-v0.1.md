# Relatório de validação e stress-test: ASTRARIUM (GDD v0.1)

Crítico: `game-design-critic` (Red Team, subagente isolado) · Data: 2026-11-25 · Rodada: 1
Objeto: `docs/design/GDD.md` v0.1, com contexto de `V01-visao.md`, `R01-mercado-idle.md` e `game/data/balance.json`.

Legenda de evidência usada em cada achado:
- **[SIM]**: comprovado por simulação (método e números no Apêndice A).
- **[TEXTO]**: comprovado pela leitura do GDD ou do `balance.json` (contradição, órfão ou lacuna verificável).
- **[JULGAMENTO]**: avaliação do crítico, sem prova numérica. Nunca serve de veto.
- **[FONTE]** / **[RECALL NÃO VERIFICADO]**: precedente de mercado com ou sem fonte.

> **Aviso de versão.** O `balance.json` mudou durante a revisão (17:25 UTC: `base_teeth` 12→24, `max_level` 19→17, `base_beat_rate` 0,5→0,25), mas o GDD §5 e §8 continuam descrevendo a v0.3 (12 dentes, nível 19). Rodei tudo nas duas versões: **v0.3** (a que o GDD descreve) e **v0.3b** (o arquivo atual). As conclusões valem para as duas. O GDD e o `balance.json` precisam voltar a concordar antes da rodada 2.

---

## 1. Evidence Classification

* **Status:** **PROVEN DEFECT (Veto)**, em 4 achados (F1, F2, F3, F4). Os demais são riscos observados.
* **Executive Assessment:** A fantasia, o tema e a regra "relação limitada por estágio" estão certos, e o nicho é real (R01). O núcleo sistêmico, porém, ainda não entrega o que o GDD promete. O eixo velocidade × força se resolve com uma regra trivial ("nunca deixe a força abaixo da carga"), que na simulação empata com o otimizador ou o supera. O jogador não-clicador vê o céu, que é o diferencial do jogo, só depois de 48 a 53 minutos. A cúpula é um sumidouro linear de moeda. O Grande Ano ainda não traz regras novas. Dá para corrigir tudo isso aprofundando a relojoaria, sem cortar escopo.

---

## 2. Orphans and Coherence Gaps

* **Recursos, verbos e cenas órfãos ou incompletos:**
  - **Reserva de corda** [TEXTO]: está em §4 (recurso) e no `balance.json` (`offline.cost0 = 500`, `growth = 3`), mas não aparece na tabela de verbos (§3) nem em nenhuma tela do mapa (§2). O simulador também não tem essa compra. A peça que define a experiência idle/offline nunca foi testada.
  - **Sobrecorda** [TEXTO]: o verbo existe (§3), mas não está no simulador e não está claro como convive com o clique (segurar a manivela exclui clicar?).
  - **Éons** [TEXTO]: o GDD §6 diz que Éons são **gastos** em ofícios. O `balance.json` tem `aeon_mult_each: 0.1`, um multiplicador **passivo** por Éon. Falta dizer se gastar reduz o multiplicador (a tensão do sacrifício de anjos de AdVenture Capitalist) ou se são duas moedas. O prestígio inteiro (reset, ofícios, era) não está no simulador.
  - **Roda de escape (5º estágio)** [SIM]: desbloqueio a 4e8 Tiques. Nenhum perfil a alcança em 75 min (o ativo chega ao Grande Ano aos ~40 min). No VS ela é conteúdo morto. Além disso, na relojoaria real o escape é **a peça que faz o tique**; ser a última compra contradiz o pilar 2 (ver F8).
  - **Refinamentos a cada 6 níveis** (`milestone.mult = 1.0`): são só visuais. Cumprem o pilar 1, mas não tocam nenhuma decisão. Aceitável se forem assumidos como recompensa visual.
* **Cenas ou telas duplicadas:** nenhuma de fato. P1 (bancada) e P2 (ficha) compartilham "comprar", mas P2 tem a leitura contextual como verbo próprio. P3 (cúpula) só tem um verbo ("acender estrela"), sem escolha (ver F4).
* **Minute-10 Test:** **FAIL** [SIM + TEXTO]. O GDD §1 afirma que no minuto 10 o jogador "já viu a Lua surgir" e "está decidindo entre o quarto estágio e níveis da Lua". O próprio §8 e o simulador desmentem: no perfil ativo (v0.3) a Lua chega aos 13,7 min e o 4º estágio aos 27,2 min. No casual, aos 10 min ainda há 2 estágios (o 3º chega aos 18,8). No idle, 2 estágios até 25,6 min. Os verbos do minuto 10 são os do minuto 1: comprar nível de roda, comprar peso, clicar.

---

## 3. Findings

### F1. Velocidade × força tem uma estratégia trivialmente dominante: "mantenha força ≥ carga"
* **Classificação:** PROVEN DEFECT (Veto): dominância trivial. **[SIM]**
* **Evidência:**
  - Comparei a política gulosa do simulador com uma política de regra fixa: antes de qualquer compra que faça a carga passar da força, compre peso; nunca deixe a eficiência ficar abaixo de 1. Na v0.3, a regra **empata com o otimizador ou o supera** em todos os perfis: ativo, Grande Ano aos 39,9 min contra 40,7; casual, 3º estágio aos 15,7 contra 18,8; idle, 3º estágio aos 20,6 contra 25,6. Na v0.3b a regra vence por muito (Grande Ano ativo aos 59,6 min; o guloso chega aos 74,4).
  - O peso custa **0,01% a 0,26% de todos os Tiques gastos** na partida (ativo v0.3: 0,0001 do gasto). O custo dele cresce ×1,7 por nível, mas a carga máxima do VS (4 estágios no nível 19) é 760, e o peso 15 já dá força 1.314 por um total acumulado de cerca de 115 mil Tiques. Só o desbloqueio do 4º estágio custa 2,5 milhões. Depois do minuto ~4 (ativo), o peso vira um botão barato que se aperta sempre que o ponteiro fica vermelho.
  - A forma da função também elimina o ótimo interior: `eficiência = min(1, F/C)^1,5`. Força acima da carga vale zero, e força abaixo pune mais que linearmente. O único ponto racional é F ≈ C. As complicações não têm carga nenhuma.
  - A política "nunca comprar peso" trava: 3º estágio só aos 72 min no ativo. O peso, portanto, é **obrigatório e barato**. Isso é um pedágio, não uma decisão.
* **Por que importa:** é o pilar 2 e o diferencial nº 1 do V01 ("economia baseada em trem de engrenagens real, relação × força"). Se o eixo de força se reduz a um reflexo, o jogo volta a ser "gerador abstrato com tema de engrenagem", exatamente o que o R01 aponta como fracasso dos concorrentes (Idling Gears, 69% de 351, [Steam](https://store.steampowered.com/app/2285820)).

### F2. Janela monótona e o céu chegando tarde demais para quem não clica
* **Classificação:** PROVEN DEFECT (Veto): o mesmo no minuto 10, e o GDD contradiz a própria simulação. **[SIM + TEXTO]**
* **Evidência (v0.3):**

  | Perfil | Último elemento novo | Próximo elemento novo | Janela sem novidade | Lua (céu aparece) |
  |---|---|---|---|---|
  | Ativo (3 cliques/s) | roda de centro 0,8 min | 3ª roda 6,8 min | **6,0 min** | 13,7 min |
  | Casual (0,6/s) | roda de centro 2,2 min | 3ª roda 18,8 min | **16,6 min** | 36,0 min |
  | Idle (sem clique) | roda de centro 1,0 min | 3ª roda 25,6 min | **24,6 min** | 53,3 min |

  - No ativo, entre 1 e 7 min, só aparecem 3 tipos de compra (nível da grande roda ×16, nível da roda de centro ×18, peso ×7), todas numéricas. A grande roda chega ao nível máximo aos 3,2 min, e daí até 6,8 min sobram só a roda de centro e o peso.
  - Na v0.3b o greedy chega a passar de 7 a 15 min sem compra nenhuma (artefato da política míope, ver F7, mas o sintoma para um jogador desatento é o mesmo).
* **Por que importa:** o R01 coloca "a mesma coisa com número maior" como reclamação nº 1 do gênero. O V01 promete, como critério de sucesso, que "aos 10 minutos o jogador toma decisões diferentes das do minuto 1". O público-alvo declarado (segunda tela, cozy) é o perfil casual/idle, justamente o que espera de 16 a 25 min sem novidade e quase 1 h para ver a cúpula.

### F3. O clique domina a economia e contradiz "nunca frenético" e "respeito pelo tempo"
* **Classificação:** PROVEN DEFECT (Veto): estratégia dominante + contradição com pilar. **[SIM + TEXTO]**
* **Evidência:**
  - Cada clique dá `1 + 1 s de produção`. A 3 cliques/s, a renda total é `B + 3(1+B) ≈ 4B`: **+300% permanente**, que escala com a produção e nunca perde relevância. A Sobrecorda (×1,5) ainda soma em cima, e o simulador nem a modela.
  - Grande Ano pronto (v0.3, política de regra): ativo **39,9 min**, casual **87,8 min**, idle **129,2 min**. Na v0.3b: 59,6 / 132,4 / 196,5 min. A meta do VS ("45–60 min") só vale para quem clica 3 vezes por segundo, o que dá cerca de **7.200 cliques** até o primeiro prestígio.
  - V01: "nunca frenético", público de "segunda tela" (Rusty's Retirement, Bongo Cat). R01 §3: "'Idle' que exige atenção constante deixa de ser idle" ([Reddit r/incremental_games](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually)).
* **Por que importa:** o melhor jogo, segundo a matemática, é o oposto do tom pretendido. Clicar 7 mil vezes num relógio contemplativo também é risco de LER.

### F4. "O céu é a árvore de upgrades" ainda não é uma árvore: é um sumidouro linear
* **Classificação:** PROVEN DEFECT (Veto): ilusão de escolha / progressão só numérica. **[TEXTO + SIM]**
* **Evidência:**
  - Todas as estrelas são idênticas (`add_each 0.5`), o custo é uma sequência única (`15·2,3^n`) e o bônus da constelação só chega na 7ª. Não há topologia, ramos nem estrela "diferente". O verbo "acender estrela" não tem escolha: qualquer estrela vale o mesmo.
  - Retorno marginal depois da 1ª constelação: a 7ª leva o multiplicador de ×4 para ×9. A 8ª custa 5,1 mil e dá +11% (×9→×10). A 13ª custa 329 mil e dá +7%. A 2ª constelação exige 1,34 milhão de Luz Estelar acumulada. Com a produção do fim da partida ativa (149/s), isso dá ~2,5 h, ou seja, **nunca acontece num ciclo do VS**.
  - Cadeia de conversão totalmente linear: Tiques → níveis de Lua/Mercúrio (**56% de todo o gasto de Tiques do perfil ativo**, v0.3) → Luz Estelar → estrela → o mesmo multiplicador global que a roda já dá. É um único eixo com três moedas.
* **Por que importa:** é o diferencial nº 2 do V01. R01 §4: "Bons upgrades mudam comportamento, não só percentual" ([Game Developer, Gnorp](https://gamedeveloper.com/design/interview-the-gnorp-apologue)). Hoje a cúpula é bonita, mas mecanicamente é um contador.

### F5. Grande Ano e eras de material: ainda são "número maior", e a ficção apaga o mundo
* **Classificação:** OBSERVED RISK, com um defeito parcial comprovado. **[TEXTO + SIM]** (o prestígio não foi simulado porque o simulador não tem reset)
* **Evidência:**
  - Os exemplos de regras por material são "aço reduz carga" e "ouro aumenta Luz Estelar". O primeiro age num eixo que já é irrelevante (o peso é 0,01% do gasto, F1): **efeito praticamente nulo, comprovado** [SIM]. O segundo é um multiplicador. O GDD §6 exige "uma regra nova, não só um número maior", e os próprios exemplos não passam nesse teste.
  - Os ofícios listados ("começar com o 2º estágio", "rodas 10% mais baratas", "sobrecorda mais longa") são todos aceleradores do mesmo run.
  - Éons no ponto de prontidão (ativo v0.3): `floor(√(33.414/50)) = 25`. Sem uma tabela de ofícios não há como avaliar o valor deles.
  - **Ficção** [JULGAMENTO]: o reset apaga Lua e planetas que "voltaram ao céu". O pilar 1 ("o mundo é o mostrador") vira o contrário: o mundo esquece. A decisão sobre manter as estrelas está pendente.
* **Por que importa:** R01 §4: "o prestígio deve adicionar mecânica, não só reiniciar". É a reclamação nº 1 do gênero aplicada à meta.

### F6. A relação de dentes "acelera o tique": a relojoaria ensinada é parcialmente falsa
* **Classificação:** OBSERVED RISK. **[JULGAMENTO]** (fato de relojoaria; precedente técnico de conhecimento geral, sem link)
* **Evidência:** num relógio real a frequência do tique é definida pelo **regulador** (pêndulo ou foliot) através do **escape**. O trem de engrenagens converte a queda lenta do peso em muitas batidas: mais relação significa **mais autonomia** (o peso desce mais devagar) e **menos torque no escape** (força ÷ relação). No modelo atual, "mais dentes = tique mais rápido" é um trem sem escape, que dispararia. Além disso, a roda de escape vem por último (F2/§2), quando na realidade é a primeira peça necessária. O V01 promete que "o jogador aprende algo verdadeiro sobre mecanismos".
* **Por que importa:** é uma oportunidade perdida mais do que um erro. O modelo real já contém o trade-off que falta ao F1.

### F7. Compras que pioram a máquina, sem pré-visualização; o simulador é míope
* **Classificação:** OBSERVED RISK (feedback / fricção cognitiva). **[SIM]**
* **Evidência:**
  - v0.3: desbloquear a roda de centro aos 0,8 min derruba a produção de 2,0 para 0,71 tiques/s (−65%). A primeira peça nova deixa a máquina **mais lenta**.
  - Ao longo de 90 min, o otimizador avalia 75 (ativo), 207 (casual) e 114 (idle) compras de nível que **reduzem** a produção. Na v0.3b são 2.244, 6.007 e 10.025: com `base_teeth 24` o ganho marginal de um dente é menor e quase toda compra de roda sem peso é prejuízo.
  - O guloso do `economy.py` avalia uma compra por vez e não enxerga o pacote "peso + roda". Na v0.3b isso gera um falso "vale morto" de 7 a 15 min no perfil ativo. **As conclusões do §8 sobre ritmo dependem dessa política.**
* **Por que importa:** o jogador humano tende a se comportar como o guloso (compra o botão maior). Sem uma prévia diegética ("esta roda vai arrastar o trem"), o eixo de força ensina pela punição. É a mesma reclamação de Nodebuster: "não sabia por que" ([Laura Michet](https://blog.lauramichet.com/played-nodebuster/)).

### F8. A experiência idle/offline não está definida nem testada
* **Classificação:** OBSERVED RISK. **[TEXTO + SIM]**
* **Evidência:** a reserva começa em 1 h, com custo `500·3^n` e sem verbo nem tela de compra (§2). O idle leva **129 min ativos na tela** para o primeiro Grande Ano (v0.3). O R01 §3 registra que limites offline curtos "perdem o sentido de idle" ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually)), com o exemplo de Egg, Inc. limitado a 2 h ([Pecorella III](https://gamedeveloper.com/design/the-math-of-idle-games-part-iii)). O jogador idle, que é o público declarado, é o menos servido pelo desenho atual.
* **Por que importa:** o critério de sucesso do V01 "ao voltar depois de horas, o jogador vê a diferença no mundo" não tem economia por trás.

---

## 4. Decoupled Solution Vectors (por achado, não obrigatórios)

### F1. Velocidade × força dominada por regra trivial

#### Option A: Energia e autonomia (aprofunda, relojoaria real)
* **Approach:** o peso deixa de ser "força" e passa a ser **energia armazenada** (massa × altura da queda, visível no poço). Cada tique consome energia, e um trem mais rápido esvazia o peso mais depressa. A relação total decide quantos tiques por volta da grande roda; a massa decide o torque disponível e a reserva. Daí saem três perfis legítimos: *rápido e curto* (muito tique/s, pouca autonomia, exige dar corda), *lento e longo* (menos tique/s, horas de autonomia offline) e o equilíbrio. A "Reserva de corda" deixa de ser uma compra separada e passa a emergir do desenho do trem.
* **Loop / Structure Impact:** o eixo de força passa a valer o jogo inteiro e a separar os estilos ativo e idle sem punir nenhum (F3 e F8 também se resolvem). Exige reescrever as fórmulas do §5 e o simulador com o estado "energia restante".

#### Option B: Complicações consomem torque + ótimo interior de amplitude (aprofunda)
* **Approach:** em relógios astronômicos reais, o disco lunar, o calendário e a campainha tiram energia do trem. Cada complicação passa a ter **carga própria**, e cada nível dela aumenta essa carga. A curva de eficiência ganha um **pico**: força demais aumenta a amplitude do pêndulo e o erro circular (o relógio "corre" e perde precisão; no jogo, perde Luz Estelar, que depende de precisão). O jogador procura uma faixa de força, não um mínimo, e escolhe entre "mais planetas" e "mais velocidade". Fusée e remontoire entram depois como upgrades **qualitativos** que achatam a curva.
* **Loop / Structure Impact:** cria tensão entre ramo do trem e ramo do céu e liga recursos que hoje são independentes. A UI precisa mostrar a faixa ótima no mostrador do peso.

#### Option C: Manter o modelo e reprecificar o peso (hipótese controlada)
* **Approach:** o custo do peso passa a acompanhar a carga (por exemplo, custo ∝ carga atual × custo médio do último estágio) e o expoente de eficiência cai para 1,0, o que torna a sub-força às vezes aceitável.
* **Fail Metric:** se, no simulador, a política "eficiência ≥ 1 sempre" ficar a menos de 5% do otimizador em tempo até o Grande Ano, **ou** se o peso ficar abaixo de 5% do gasto total, a decisão continua trivial.

### F2. Janela monótona e céu tardio

#### Option A: O escape e o pêndulo como 2ª peça (aprofunda, relojoaria real)
* **Approach:** a partida começa com grande roda + escape primitivo (foliot). Entre 2 e 5 min o jogador ganha o **pêndulo** (Huygens, 1656), com um verbo novo: ajustar o comprimento. Pêndulo curto dá tique rápido e exige mais impulso; pêndulo longo dá tique lento, preciso e barato em força. A roda de escape sai do fim da fila e vira a peça inicial.
* **Loop / Structure Impact:** um verbo qualitativo dentro da janela de 1–7 min, coerente com o pilar 2, que conversa com o F1-A/B.

#### Option B: Puxar o céu para frente (aprofunda o espaço P3)
* **Approach:** o mostrador de horas (100 Tiques, 18 s) passa a **abrir uma fresta da cúpula** e acender uma estrela-guia (Polaris) com um efeito qualitativo. A Lua cai para um custo alcançável em ≤ 6 min no ativo e ≤ 15 min no idle. Conjunções (§7) entram no VS como verbo da janela de 5–15 min.
* **Loop / Structure Impact:** P3 entra em uso cedo, e o diferencial nº 2 aparece no trailer dos primeiros minutos.

#### Option C: Manter o ritmo e enriquecer só o visual (hipótese)
* **Approach:** refinamentos a cada 6 níveis e anúncio da Lua.
* **Fail Metric:** no playtest, a mediana do intervalo entre "eventos novos" (peça, verbo ou tela) maior que 4 min entre os minutos 1 e 15, **ou** abandono na 1ª sessão entre os minutos 3 e 10 acima de 25%.

### F3. Clique dominante

#### Option A: Dar corda é encher o peso, com trava de corda (aprofunda, relojoaria real)
* **Approach:** relógios reais têm **stopwork** (trava de Genebra) para impedir excesso de corda. O clique sobe o peso (energia, F1-A) até o topo do poço e, quando a corda está cheia, a manivela trava com um estalo. Clicar passa a significar "manter um trem rápido abastecido", e o idle compensa com autonomia. Pode entrar também a "força de manutenção" de Harrison como upgrade (o trem não para enquanto se dá corda).
* **Loop / Structure Impact:** o clique fica limitado pela física e não pela UI. O ativo continua vantajoso, mas por um fator limitado (meta: ≤ 1,5× até o Grande Ano).

#### Option B: Clique só no começo, Sobrecorda como verbo ativo com cadência
* **Approach:** o clique vira `+ ticks_per_wind` fixo, sem a fração da produção, e perde relevância depois de ~3 min. A Sobrecorda passa a ser o verbo ativo: segurar até sentir a tensão e soltar na hora certa (feedback de catraca). Ela recarrega pelo próprio trem.
* **Loop / Structure Impact:** remove 90% dos cliques e mantém um gesto ativo ritmado e calmo.

#### Option C: Teto no bônus de clique (hipótese)
* **Approach:** limitar a renda de clique a +50% da produção passiva.
* **Fail Metric:** se o tempo do idle até o Grande Ano for maior que 2× o do ativo, ou se a mediana de cliques por minuto no minuto 20 passar de 60.

### F4. Cúpula linear

#### Option A: Constelações reais como grafo de escolhas (aprofunda)
* **Approach:** cada estrela tem **magnitude** (as mais brilhantes custam mais e dão mais) e só pode ser acesa se for vizinha de outra já acesa, seguindo as linhas reais da constelação. Cada constelação tem 2 ou 3 caminhos e **um bônus de regra**, não ×2. Exemplos: Ursa Maior → a reserva conta o tempo offline em dobro; Plêiades → janela de conjunção maior; Lira → a carga das complicações cai pela metade.
* **Loop / Structure Impact:** P3 ganha um verbo de escolha (qual caminho, qual constelação primeiro). As estrelas viram builds, e a ordem importa.

#### Option B: O céu é alcançado pelas órbitas (aprofunda e liga sistemas)
* **Approach:** cada complicação dá **acesso** a uma região do céu: a Lua percorre a eclíptica e abre as constelações do zodíaco, Mercúrio abre as próximas ao Sol. Uma estrela só acende quando o corpo celeste que a alcança passa por ela (evento previsível do almanaque).
* **Loop / Structure Impact:** liga o ramo do trem, o ramo das complicações e o céu numa só geografia, e reforça "o mundo é o mostrador".

#### Option C: Manter linear, com bônus de constelação qualitativo (hipótese)
* **Fail Metric:** menos de 5% do tempo de sessão com a câmera em P3 depois da 3ª estrela, **ou** mais de 70% dos jogadores acendendo estrelas sempre na mesma ordem (se houver ordem).

### F5. Grande Ano sem regra nova

#### Option A: Cada era é uma invenção da relojoaria, e o material é a pele (aprofunda)
* **Approach:**
  - Era 1, latão: verge e foliot. Tolerante a pouca força, impreciso (expoente de eficiência baixo).
  - Era 2, aço azulado: pêndulo e escape de âncora. Verbo novo: comprimento do pêndulo.
  - Era 3, ouro: escape *deadbeat* e fusée/remontoire. Força constante, permite muitas complicações.
  - Era 4, cristal: compensação térmica (pêndulo de grelha latão + aço). A torre tem ciclo dia/noite que altera o ritmo, e o jogador combina metais.

  Cada era reescreve **a forma** da curva de eficiência, de modo que o eixo velocidade × força muda de natureza a cada ciclo.
* **Loop / Structure Impact:** cada ciclo adiciona um verbo e uma regra, e o material continua sendo o diferencial visual.

#### Option B: Precessão, em que o céu fica e a máquina é refeita (corrige a ficção)
* **Approach:** o Grande Ano é a **precessão dos equinócios**. As estrelas e os corpos celestes **ficam acesos** (são a meta permanente, a "árvore" de longo prazo). Só a máquina é desmontada e refeita no novo material, e no ciclo seguinte os corpos celestes aparecem como "fantasmas" até o trem voltar a alcançá-los. Os Éons ficam definidos como moeda gasta, sem multiplicador passivo, ou o contrário, mas com uma regra só.
* **Loop / Structure Impact:** "o mundo é o mostrador" vale também na meta, e a cúpula acumula ao longo de todos os ciclos.

#### Option C: Só ofícios numéricos (hipótese)
* **Fail Metric:** se o 2º ciclo repetir a mesma ordem de compras do 1º em ≥ 80% das decisões e só terminar mais rápido, o prestígio é "a mesma coisa com número maior". Precisa de um simulador com reset.

### F6. Relojoaria parcialmente falsa

#### Option A: Adotar o modelo regulador + trem + energia (aprofunda)
* **Approach:** é o mesmo modelo de F1-A, F2-A e F3-A. O regulador define a batida, a relação define a autonomia e o torque necessário, e o peso define a energia.
* **Loop / Structure Impact:** um modelo físico único sustenta três achados.

#### Option B: Assumir a licença poética pela ficção
* **Approach:** "o Astrarium não mede o tempo, ele **move** o céu" (o V01 já diz isso). O trem é um motor, não um relógio, e o caderno do relojoeiro anterior explica a diferença numa frase.
* **Loop / Structure Impact:** custo zero, mas perde a promessa "aprendo algo verdadeiro".

#### Option C: Teste de compreensão (hipótese)
* **Fail Metric:** no playtest, menos de 50% dos jogadores conseguem explicar, depois de 20 min, por que comprar peso faz o trem andar mais.

### F7. Compras punitivas e simulador míope

#### Option A: Prévia diegética
* **Approach:** ao passar o mouse sobre uma roda, um ponteiro-fantasma no mostrador do peso mostra a eficiência depois da compra, e a ficha (P2) diz "vai arrastar o trem: precisa de +1 disco".
* **Loop / Structure Impact:** só UI. O eixo de força passa a ser lido antes de punir.

#### Option B: O travamento como fenômeno físico legível (aprofunda)
* **Approach:** quando a carga passa da força, o pêndulo perde amplitude visivelmente e, abaixo de um limiar, **para** com um som seco. O jogador aprende o conceito real de "relógio parado por falta de força". Nunca há perda de recurso, só pausa.
* **Loop / Structure Impact:** transforma a punição em descoberta e combina com F1-B.

#### Option C: Simulador com política de pacote (ferramenta)
* **Approach:** acrescentar ao `economy.py` uma política que avalia "compra + peso necessário" como um pacote (implementação de referência no Apêndice A).
* **Fail Metric:** se o simulador continuar mostrando vales de mais de 3 min sem compra que a política de pacote não mostra, as conclusões de ritmo do §8 não são confiáveis.

### F8. Idle e offline indefinidos

#### Option A: Autonomia emergente (aprofunda; ver F1-A)
* **Approach:** a reserva vem do desenho do trem e da altura da torre. Com o tempo, a torre ganha andares (o poço do peso fica mais fundo), o que é uma mudança visível no mundo.
* **Loop / Structure Impact:** o retorno (P6) mostra literalmente o peso no fundo do poço.

#### Option B: Reserva como verbo explícito na bancada
* **Approach:** adicionar o verbo "alongar a corrente" em P1, com custo, e uma meta de 8 h ou mais de autonomia antes do 1º Grande Ano.
* **Loop / Structure Impact:** fecha o órfão com custo mínimo.

#### Option C: Hipótese
* **Fail Metric:** mais de 30% das sessões de retorno chegando com a reserva esgotada, ou queda de retenção D1 em quem joga majoritariamente offline.

---

## 5. Dialectical Inquiries

* Se a resposta ótima ao ponteiro de força é sempre "clique em peso até ficar verde", por que o peso é um botão e não uma consequência do desenho do trem?
* Qual frase verdadeira sobre relógios o jogador consegue dizer depois de 1 h de jogo? Hoje seria "mais dentes = mais rápido", o que é falso para um relógio com escape.
* O que o jogador idle (o público-alvo declarado) **vê de novo** entre os minutos 1 e 25? E entre 25 e 53?
* Por que a 9ª estrela existe se ninguém completa a 2ª constelação no VS? O que o jogador escolhe na cúpula?
* O Grande Ano apaga a Lua que o jogador devolveu ao céu. Isso é o clímax ou a negação da fantasia central?
* Éons: são gastos, multiplicam, ou as duas coisas? Se as duas, gastar deve doer?
* Que verbo existe no ciclo 2 que não existia no ciclo 1? Se a resposta for "nenhum", o prestígio é só um reset.
* A roda de escape (o coração de um relógio) é a última compra e está fora do VS. É intencional?

---

## Apêndice A: método de simulação

- O simulador oficial foi rodado como pedido: `python3 -I tools/sim/economy.py --profile {active,casual,idle} --minutes 75`. Os resultados batem exatamente com o §8 do GDD (v0.3: centro 0,8; 3º 6,8; Lua 13,7; constelação 26,0; 4º 27,2; Mercúrio 40,7).
- Análises adicionais em scripts próprios no scratchpad do crítico (nenhum arquivo do projeto foi alterado). Eles importam a classe `Game` de uma **cópia congelada** do `economy.py` e duas cópias do balanceamento:
  - `bal_v03.json`: `base_teeth 12`, `max_level 19`, `base_beat_rate 0.5` (o que o GDD descreve).
  - `bal_v03b.json`: o arquivo atual (`base_teeth 24`, `max_level 17`, `base_beat_rate 0.25`).
- Políticas:
  - **guloso**: idêntica à do `economy.py`, com clone rápido em vez de `deepcopy`. Mesmos resultados.
  - **regra "eficiência ≥ 1"**: antes de qualquer compra, adiciona os níveis de peso necessários para manter força ≥ carga e avalia o pacote pelo mesmo critério de valor/custo. Só compra se puder pagar o pacote inteiro.
  - **sem peso**: o guloso proibido de comprar peso.
- Limitações: não modela Sobrecorda, reserva offline, conjunções nem prestígio (o reset não existe no simulador). Cliques são uma taxa constante.

| Medida | v0.3 ativo | v0.3 casual | v0.3 idle | v0.3b ativo | v0.3b casual | v0.3b idle |
|---|---|---|---|---|---|---|
| Grande Ano pronto, guloso (min) | 40,7 | > 90 | > 90 | 74,4 | > 150 | > 240 |
| Grande Ano pronto, regra "ef ≥ 1" (min) | **39,9** | **87,8** | **129,2** | **59,6** | **132,4** | **196,5** |
| 3ª roda, guloso / regra (min) | 6,8 / 6,0 | 18,8 / 15,7 | 25,6 / 20,6 | 19,4 / 8,2 | 52,4 / 21,7 | 84,6 / 30,4 |
| Lua, guloso / regra (min) | 13,7 / 12,8 | 36,0 / 32,6 | 53,3 / 47,8 | 33,4 / 18,6 | 87,8 / 47,6 | — / 72,0 |
| Peso como fração do gasto de Tiques (guloso) | 0,01% | 0,07% | 0,26% | 0,03% | 1,4% | 1,6% |
| Compras de nível avaliadas que reduzem a produção (90 min) | 75 | 207 | 114 | 2.244 | 6.007 | 10.025 |
| Política "sem peso": 3ª roda | 72,2 min | — | — | — | — | — |

Notas: "Grande Ano pronto" = 7 estrelas + Mercúrio construído, que é o requisito do §6. Éons nesse ponto (ativo v0.3): 25.
