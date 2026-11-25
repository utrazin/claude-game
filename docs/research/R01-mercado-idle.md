# R01 — Mercado de jogos idle/incrementais (foco em 3D e mundo espacial)

Data da pesquisa: 2026-11-25. Os números de review vêm das páginas da Steam (reviews em inglês, "all-time") na data da coleta. Quando não consegui verificar um dado, ele aparece como **não verificado**. O formato segue o skill `game-researcher`, adaptado ao brief do Diretor.

---

## 1. Resumo executivo (10 insights acionáveis)

1. **O mercado está saturado de idlers genéricos, mas não de idlers com cara de premium.** A Steam teve 100 lançamentos com a tag Idler em 2020, 647 em 2024, 1.033 em 2025 e 1.811 até setembro de 2026. A PC Gamer descreve a maioria como "AI slop" com a mesma UI azul-escura ([PC Gamer](https://pcgamer.com/gaming-industry/steam-week-in-review-54-idle-games-released-on-steam-last-week-and-many-look-eerily-similar)). Uma identidade visual forte e autoral é hoje o principal diferencial de descoberta ([GameDev.net](https://gamedev.net/news/3928-incremental-games-have-a-creativity-problem/)).
2. **Os grandes hits pagos recentes são quase todos 2D ou pixel art**: Rusty's Retirement, Gnorp, Nodebuster, Tower Wizard, Bugtopia. Os casos em 3D que deram certo são poucos e pequenos: Ropuka's Idle Island (95% de 2.414), Placid Plastic Duck (97% de 12.407), The Farmer Was Replaced (tag 3D, mais de US$ 6,8 mi) e Cell to Singularity (habitats 3D, 86% de 11.504). **O nicho "idle 3D premium em que o mundo é o display do progresso" segue sem dono claro.**
3. **Preço baixo e duração curta vendem.** As referências ficam entre US$ 2,99 e 6,99 e duram de 3 a 12 h (Nodebuster: 97% de 10.745 a US$ 2,99). O dev da Gnorp defende preço baixo para jogos "estranhos" ([GameDiscoverCo](https://newsletter.gamediscover.co/p/how-this-solo-dev-incremental-game)). Rusty's ficou em US$ 7, entre os idlers (US$ 0–5) e os farm sims (US$ 10–15) ([GameDiscoverCo](https://newsletter.gamediscover.co/p/how-rustys-retirement-idle-farmed)).
4. **"Desktop companion" é a tendência comercial mais forte.** Rusty's Retirement passou de 880 mil cópias e US$ 4,5 mi; Bongo Cat tem 96% de 31.675 reviews; Spirit City e Cast n Chill passaram de US$ 5,3 mi cada em 2025 ([AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)). Um modo de janela pequena ou faixa de tela vale a pena avaliar.
5. **Ver unidades individuais trabalhando é o gancho emocional.** O dev da Gnorp diz que simular cada gnorp e mostrar a escala "ridícula" é o que mais satisfaz, e que o pico de escala gera momentos compartilháveis ([Game Developer](https://gamedeveloper.com/design/interview-the-gnorp-apologue)).
6. **"Trazer cor ao mundo" funciona como metáfora de progresso.** A Gnorp começa monocromática para que o jogador sinta que está colorindo o mundo ([Game Developer](https://gamedeveloper.com/design/interview-the-gnorp-apologue)). Isso se traduz direto para um ambiente único que se transforma.
7. **A reclamação nº 1 é repetição e "mesma coisa com número maior".** Vêm em seguida prestígios que só repetem a run e upgrades que não têm efeito visível ([Reddit r/incremental_games](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually); [Laura Michet](https://blog.lauramichet.com/played-nodebuster/)). **Todo upgrade precisa de uma consequência visível no mundo.**
8. **A matemática é conhecida e barata de implementar.** Custo exponencial (base 1,07 a 1,15) contra produção linear com multiplicadores em marcos, e prestígio por raiz (√ ou ∛) dos ganhos ([Pecorella I](https://gamedeveloper.com/design/the-math-of-idle-games-part-i); [Pecorella III](https://gamedeveloper.com/design/the-math-of-idle-games-part-iii)). O risco não está no cálculo, e sim no ritmo e no significado.
9. **Monetização F2P agressiva destrói a reputação.** As principais reclamações sobre Cell to Singularity são progresso lento sem pagar, eventos pay-to-win e passes caros ([VaporLens](https://vaporlens.app/app/977400/cell_to_singularity)). Premium a preço único é o caminho seguro para um estúdio indie.
10. **O tema "engrenagens / relojoaria" está livre e mal executado.** Idling Gears tem 69% de 351 e as engrenagens são só tema; Steampunk Idle Spinner não tem score. Nenhum jogo chamado "Astrarium" aparece na busca da Steam. Um idle em que a **mecânica física (razões de engrenagem, órbitas) é a própria economia** não tem concorrente direto identificado.

---

## 2. Tabela de referências

Legenda: % e contagem = reviews em inglês, all-time, na página da Steam. O loop descrito é um resumo meu a partir das descrições e reviews.

| Jogo (ano) | Visual | Preço | Reviews | Loop de 5–30 s | Gancho elogiado | Reclamações |
|---|---|---|---|---|---|---|
| [Nodebuster](https://store.steampowered.com/app/3107330) (2024) | 2D minimalista | US$ 2,99 | 97% de 10.745 | Passar o cursor pelos nós, coletar, comprar na árvore | Custo-benefício, ritmo, partículas e som ([VaporLens](https://vaporlens.app/app/3107330/nodebuster.md)) | Curto (3–6 h), fim repetitivo, upgrades sem efeito visível, rótulo "idle" enganoso |
| [Gnorp Apologue](https://store.steampowered.com/app/1473350) (2023) | 2D pixel | US$ 6,99 | 95% de 7.449; mais de 120 mil vendidas no 1º mês ([GDCo](https://newsletter.gamediscover.co/p/how-this-solo-dev-incremental-game)) | Ver gnorps baterem na rocha, comprar unidades e talentos | Personagens fofos, profundidade de builds ([VaporLens](https://vaporlens.app/app/1473350/the_gnorp_apologue)) | Poucas builds viáveis, escolhas que estragam a run, prestígio duro |
| [Rusty's Retirement](https://store.steampowered.com/app/2666510) (2024) | 2D pixel, faixa de tela | US$ 6,99 | 97% de 6.633; mais de 880 mil cópias ([AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)) | Plantar, posicionar robôs e voltar ao trabalho | Joga enquanto você faz outra coisa ([GDCo](https://newsletter.gamediscover.co/p/how-rustys-retirement-idle-farmed)) | Não verificado |
| [Tower Wizard](https://store.steampowered.com/app/3479000) (2025) | 2D pixel | US$ 2,99 | 96% de 7.382; cerca de 555 mil em 2025 ([AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)) | Invocar espíritos, coletar e subir a torre | Torre que cresce visivelmente | Não verificado |
| [Cookie Clicker](https://store.steampowered.com/app/1454400) (Steam 2021) | 2D | US$ 4,99 | 96% de 55.412 | Clicar, comprar construções | Referência clássica, humor | Não verificado |
| [Melvor Idle](https://store.steampowered.com/app/1267910) (2021) | 2D UI | US$ 9,99 | 92% de 8.691 | Escolher skill, aguardar, gerenciar inventário | Profundidade de RPG, hábito diário ([VaporLens](https://vaporlens.app/app/1267910/melvor_idle)) | Lento, onboarding fraco, **"interface de planilha"** |
| [NGU Idle](https://store.steampowered.com/app/1147690) (2019) | 2D UI | F2P | 95% de 10.900 | Alocar energia e magia | Humor, volume de conteúdo | Não verificado |
| [Idle Slayer](https://store.steampowered.com/app/1353300) (2020) | 2D pixel | F2P | 78% de 4.398 | Pular, coletar moedas, upgrades | Não verificado | Nota baixa para o gênero; motivos não verificados |
| [Unnamed Space Idle](https://store.steampowered.com/app/2471100) (EA 2023) | 2D UI | F2P | 92% de 3.043 | Não verificado | Não verificado | Não verificado |
| [Increlution](https://store.steampowered.com/app/1593350) (2021) | 2D UI | US$ 3,99 | 85% de 1.247 | Encadear ações numa vida, morrer e repetir | Não verificado | Não verificado |
| [Antimatter Dimensions](https://store.steampowered.com/app/1399720) (2022) | 2D UI | F2P | 91% de 3.456 | Comprar dimensões, várias camadas de prestígio | Não verificado | Não verificado |
| [Bongo Cat](https://store.steampowered.com/app/3419430) (2025) | 2D, desktop | F2P | 96% de 31.675; mais de US$ 670 mil ([AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)) | Digitar ou clicar no trabalho e ganhar itens | Meme, companhia passiva | Não verificado |
| [The Farmer Was Replaced](https://store.steampowered.com/app/2060160) (2025) | **3D** (tag) | US$ 9,99 | 95% de 4.620; mais de US$ 6,8 mi ([AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)) | Escrever código que automatiza a fazenda | Programação como automação; D30 acima de 10% | Não verificado |
| [Cell to Singularity](https://store.steampowered.com/app/977400) (2021) | 2D UI + **habitats 3D** | F2P | 86% de 11.504 | Clicar e comprar espécies; ver o habitat 3D evoluir | Valor educativo ([VaporLens](https://vaporlens.app/app/977400/cell_to_singularity)) | Saves na nuvem, progresso lento sem pagar, pay-to-win |
| [Ropuka's Idle Island](https://store.steampowered.com/app/3416070/Ropukas_Idle_Island/) (2025) | **3D** fofo, desktop | US$ 3,99 | 95% de 2.414 | Ver o sapo cortar grama, comprar upgrades, decorar | Adesivo de desktop | Não verificado |
| [Placid Plastic Duck Sim](https://store.steampowered.com/app/1999360) (2022) | **3D** | US$ 1,99 | 97% de 12.407 | Observar patos (quase sem input) | Contemplação pura | Não verificado |
| [BALL x PIT](https://store.steampowered.com/app/2062430) (2025) | 2D | US$ 14,99 | 95% de 16.104; 300 mil em 5 dias ([PC Gamer](https://www.pcgamer.com/games/roguelike/ball-bouncing-city-building-off-the-wall-roguelike-ball-x-pit-is-a-huge-hit-selling-300-000-copies-in-just-its-first-five-days-on-sale/)) | Lançar bolas, fundir, voltar à base | Nº 1 em cópias entre idlers em 2025 ([AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)) | Não verificado |
| [Loop Hero](https://store.steampowered.com/app/1282730) (2021) | 2D pixel | US$ 14,99 | 91% de 16.144 | Posicionar cartas, ver o herói lutar | Não verificado | Não verificado |
| [Kingdom Two Crowns](https://store.steampowered.com/app/701160) (2018) | 2D pixel com camadas | US$ 19,99 | 89% de 10.657 | Gastar moedas para expandir o reino | Comparação visual (mundo que cresce) | Não verificado |
| [Townscaper](https://store.steampowered.com/app/1291340) (2021) | **3D** estilizado | US$ 5,99 | 95% de 10.650 | Clicar e a cidade se monta sozinha | Feedback procedural | Não verificado |
| [Islanders](https://store.steampowered.com/app/1046030) (2019) | **3D** estilizado | US$ 4,99 | 95% de 10.227 | Posicionar prédio, ganhar pontos | Não verificado | Não verificado |
| [Dorfromantik](https://store.steampowered.com/app/1455840) (2022) | **3D** estilizado | US$ 13,99 | 96% de 15.855 | Encaixar peças, o mapa cresce | Visual e trilha ([VaporLens](https://vaporlens.app/app/1455840/dorfromantik)) | Aleatoriedade, repetição, pouca profundidade |
| [Tiny Glade](https://store.steampowered.com/app/2198150) (2024) | **3D** painterly | US$ 14,99 | 97% de 14.155; mais de 1 mi de wishlists ([WN Hub](https://wnhub.io/news/stores-and-publishing/item-45586)) | Puxar muros, o castelo se adapta | Visual "charmoso", calma ([Shacknews](https://shacknews.com/article/141431/tiny-glade-review-score)) | Pouco controle fino ([Shacknews](https://shacknews.com/article/141431/tiny-glade-review-score)) |
| [Timberborn](https://store.steampowered.com/app/1062090) (1.0 em 2026) | **3D** estilizado | US$ 34,99 | 96% de 24.651 | Gerenciar água e castores | Não verificado | Não verificado |
| [shapez 2](https://store.steampowered.com/app/2162800) (1.0 em 2026) | **3D** limpo | US$ 29,99 | 97% de 9.200 | Montar linhas de produção | Não verificado | Não verificado |

Não verificados neste ciclo: **The Tower** (mobile, sem página Steam encontrada), **Banana** (só a receita de cerca de US$ 90 mil, via [AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)), **Universal Paperclips** e **A Dark Room** (web e mobile, sem dados da Steam coletados).

---

## 3. Reclamações recorrentes

- **"A mesma coisa com número maior."** Escala repetitiva e prestígio que só reinicia a mesma run ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually)).
- **Paredes de grind e ritmo irregular.** O começo é lento e depois o jogador fica poderoso demais (Nodebuster, [VaporLens](https://vaporlens.app/app/3107330/nodebuster.md)). Em Melvor, skills "irrazoavelmente" lentas ([VaporLens](https://vaporlens.app/app/1267910/melvor_idle)).
- **Upgrades sem efeito perceptível.** Em Nodebuster, armadura e dano não têm feedback visual, e a autora não sabia por que morria ([Laura Michet](https://blog.lauramichet.com/played-nodebuster/)).
- **Um único caminho ótimo e escolhas que punem.** Na Gnorp, poucas builds viáveis e talentos que estragam a run ([VaporLens](https://vaporlens.app/app/1473350/the_gnorp_apologue)); no Reddit, decisões "falsas" quando só uma ordem de compra funciona.
- **UI de planilha e onboarding fraco** (Melvor, [VaporLens](https://vaporlens.app/app/1267910/melvor_idle)).
- **"Idle" que exige atenção constante.** Jogos que pedem gerência ativa demais deixam de ser idle ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually); Nodebuster no [VaporLens](https://vaporlens.app/app/3107330/nodebuster.md)).
- **Progresso offline com limite curto.** Limites de poucas horas "perdem o sentido de idle" ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually)). Egg, Inc. limita a 2 h ([Pecorella III](https://gamedeveloper.com/design/the-math-of-idle-games-part-iii)).
- **Monetização manipuladora.** Anúncios automáticos são inaceitáveis ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually)); em Cell to Singularity, eventos pay-to-win e passes caros ([VaporLens](https://vaporlens.app/app/977400/cell_to_singularity)). Há literatura acadêmica e regulatória sobre design manipulador em jogos ([vzbv, 2025](https://www.vzbv.de/sites/default/files/2025-04/25-03-11_Additional_information_vzbv_manipulative_design_online-games.pdf); [arXiv 2412.05039](https://arxiv.org/html/2412.05039v1)). Não li o conteúdo em detalhe.
- **Arte genérica ou gerada por IA.** Jogadores percebem e abandonam ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually); [PC Gamer](https://pcgamer.com/gaming-industry/steam-week-in-review-54-idle-games-released-on-steam-last-week-and-many-look-eerily-similar)).
- **Conteúdo curto e pouco replay** (Gnorp e Nodebuster). A crítica coexiste com notas acima de 95%: a curta duração é perdoada quando o preço é baixo.
- **Desempenho em sessões longas.** Lentidão em sessões idle longas e falhas de save na nuvem (Cell to Singularity); queda de FPS e efeitos de tela agressivos em Nodebuster. Num jogo 3D que fica aberto por horas, desempenho em segundo plano é requisito.

---

## 4. Princípios de economia

**Fórmulas base** ([Pecorella, parte I](https://gamedeveloper.com/design/the-math-of-idle-games-part-i)):
- `custo_n = custo_base × taxa^n`. AdVenture Capitalist usa taxa de 1,07.
- `produção = produção_base × n × multiplicadores`. Multiplicadores ×2 aos 25 e 50 itens no exemplo.
- Compra em lote: `b × r^k × (r^n − 1)/(r − 1)`. Máximo comprável: `floor(log_r(c(r−1)/(b·r^k) + 1))`.
- Modelo "gangorra": custo exponencial contra produção linear ou polinomial. Os multiplicadores empurram temporariamente a produção à frente do custo.
- **Variar os marcos de multiplicador entre geradores** evita que o gerador mais novo torne os antigos irrelevantes e muda qual gerador domina ao longo do jogo.

**Cadeias de derivadas** ([Pecorella, parte II](https://www.gamedeveloper.com/game-platforms/the-math-of-idle-games-part-ii)):
- Gerador de nível N produz o de nível N−1, o que gera crescimento `x^n/n!` (tende a `e^x`). Exemplo: custo `5 × 1,1^n` no Derivative Clicker.
- Para manter os níveis baixos relevantes, cada unidade comprada dá um bônus pequeno (0,05%) a todo o nível.

**Prestígio** ([Pecorella, parte III](https://gamedeveloper.com/design/the-math-of-idle-games-part-iii)):
- AdVenture Capitalist: `p = 150·√(ganhos_vida/10^15)`. Dobrar o prestígio exige de 3× a 4× os ganhos.
- Cookie Clicker: `p = ∛(ganhos_vida/10^12)`, cerca de 8× para dobrar.
- Realm Grinder: fórmula triangular inversa, cerca de 4×.
- Egg, Inc.: `Δp = (ganhos_run/10^6)^0,14`, cerca de 128× para dobrar.
- Princípio: resetar no mesmo ponto não deve render mais. A raiz força cada run a ir mais longe.

**Princípios de dev e jogadores:**
- Vincule o multiplicador a **unidades visíveis** (número de gnorps), não a gasto. Vincular a gasto gerou compras forçadas e picos erráticos ([Game Developer](https://gamedeveloper.com/design/interview-the-gnorp-apologue)).
- Bons upgrades **mudam comportamento**, não só percentual ([Game Developer](https://gamedeveloper.com/design/interview-the-gnorp-apologue)).
- Prestígio deve **adicionar mecânica**, não só reiniciar ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually)).
- Libere mecânicas aos poucos e ofereça escolhas reais ([Reddit](https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually)).
- Saltos de escala ("de um a um para milhares") geram boca a boca ([GameDiscoverCo](https://newsletter.gamediscover.co/p/how-this-solo-dev-incremental-game)).
- Retenção típica do gênero: D1 entre 40% e 70%; D30 acima de 10% é excepcional ([AppMagic](https://appmagic.rocks/blog/idle-steam-games-2026)).
- Talks no GDC Vault: "Idle Games: The Mechanics and Monetization of Self-Playing Games" ([GDC Vault](https://gdcvault.com/play/1022065/contactUs)) e "Quest for Progress", GDC Europe 2016 ([slides](https://www.slideshare.net/slideshow/quest-for-progress-gdc-europe-2016/65405507)). Conteúdo não lido em detalhe.

---

## 5. Oportunidades

- **O mundo 3D como display do progresso é sub-explorado.** Os hits pagos de 2023 a 2026 são 2D. Os idles 3D bem avaliados (Ropuka's, Placid Duck, Cell to Singularity) têm escala visual modesta ou usam o 3D como vitrine secundária: em Cell to Singularity, o habitat 3D é separado da UI de compra. Nenhum título encontrado combina **idle premium, ambiente único painterly ou semi-realista, e transformação contínua do mesmo espaço**.
- **Fantasias com prova adjacente:**
  - **Diorama ou miniatura que se adapta:** Tiny Glade (97%) e Townscaper (95%) provam o prazer de ver o mundo "se montar sozinho". Nenhum dos dois é idle.
  - **Ecossistema ou terrário:** Bugtopia (2D, 92% de 869) prova a demanda; não encontrei versão 3D premium.
  - **Ilha ou companhia de desktop:** Ropuka's (3D, 95%) e Rusty's mostram que o modo "janela no canto" vende.
  - **Evolução e cosmos:** Cell to Singularity tem a fantasia, mas foi penalizado pelo modelo F2P.
  - **Máquina ou mecanismo:** ver a seção 6.
- **Ganchos de diferenciação com evidência:** unidades individuais visíveis (Gnorp), mundo que "ganha cor" (Gnorp), automação programável (The Farmer Was Replaced, D30 acima de 10%) e modo desktop (Rusty's, Bongo, Ropuka's).
- **Riscos:** idle e 3D de alta fidelidade exigem desempenho em segundo plano por horas, e jogos curtos recebem críticas de conteúdo. Por isso, um ambiente único com muitos **estados** é mais barato e mais coerente que vários biomas.

---

## 6. Concorrência temática

**(a) Engrenagens, relojoaria, orreries e relógios astronômicos**

| Jogo | 2D/3D | Reviews | A mecânica física importa na economia? |
|---|---|---|---|
| [Idling Gears](https://store.steampowered.com/app/2285820) (2023, US$ 4,99) | 2D cartoon | **Mixed, 69% de 351** | Não. As engrenagens são geradores de moeda com multiplicadores, e a página não menciona encaixe nem razão. É só tema. |
| [Steampunk Idle Spinner](https://store.steampowered.com/app/3749540) (2025, US$ 4,99) | 2D | 5 reviews, sem score | Não é descrito. Há engrenagens, balões e portais em 7 mundos. Tudo indica que é tema. |
| [Crank Engine](https://shikoba.itch.io/crank-engine) (itch e Playdate, US$ 3,99) | 1-bit (2D, por inferência) | Sem notas | Parcial. A manivela física do Playdate gera Essence. As "engrenagens" (Clockwork Array) são multiplicadores comprados, sem razão mecânica. |
| [Clockwork Cycles](https://aizome.itch.io/clockwork-cycles) (itch) | Não verificado | Não verificado | Não verificado |

**Conclusão:** nenhum concorrente encontrado usa razão de engrenagem, trem de engrenagens ou órbita como regra econômica. O tema existe só como verniz e foi mal recebido no maior exemplo (69%). Não encontrei nenhum idle de orrery ou relógio astronômico.

**"Astrarium":**
- A busca da Steam por "astrarium" retornou apenas Slaughter Void, Slaughter Void Demo, Mini Merchant e Time Defense, nenhum com esse nome ([busca Steam](https://store.steampowered.com/search/?term=astrarium)).
- No itch.io existe **"Astrarium"** (2018, de "abclive"), um gerador procedural de planetas experimental, não idle ([RAWG](https://rawg.io/games/astrarium)).
- Existe um perfil itch "astrarium-digital" ([itch](https://itch.io/profile/astrarium-digital)). O conteúdo não foi verificado porque a página falhou ao carregar.
- Nome parecido na Steam: **The Astrolarix** ([Steam](https://store.steampowered.com/app/1073790/The_Astrolarix/)), não verificado.
- Recomendação: checar marca registrada antes de adotar o nome.

**(b) Terrários e ecossistemas em vidro**

| Jogo | 2D/3D | Reviews | Observação |
|---|---|---|---|
| [Bugtopia](https://store.steampowered.com/app/2988300) (2025, US$ 5,99) | 2D | Very Positive, 92% de 869 | Idle aconchegante com mais de 300 insetos, modo wallpaper e Pomodoro |
| [Terrarium](https://store.steampowered.com/app/3262910) (Traveler Studios, 2025, US$ 3,99) | **3D** | 80% de 15 | Sandbox de dioramas em garrafa. A tag Idler existe, mas a página não descreve mecânica idle |
| [Tiny Biomes: Cozy Idle](https://store.steampowered.com/app/4276980/Tiny_Biomes_Cozy_Idle/) (2026, US$ 4,99) | 2D pixel | 85% de 459 | Animais produzem recursos em biomas pequenos |
| [The Neeblarium](https://store.steampowered.com/app/4068780/The_Neeblarium) (EA 2026, US$ 5,99) | 2D pixel | Sem reviews | Vida artificial com linhagens e traços, quase sem input |

**Conclusão:** existe demanda para terrário idle (Bugtopia), mas o único terrário 3D é um builder pequeno e sem tração (15 reviews). **Terrário 3D premium com economia idle continua livre.**

---

## 7. Referências visuais

- **Tiny Glade** (3D painterly, 97% de 14.155). O visual "charmoso" e o tom zen foram elogiados, e a arquitetura procedural se adapta a cada mudança ([Shacknews](https://shacknews.com/article/141431/tiny-glade-review-score); [WN Hub](https://wnhub.io/news/stores-and-publishing/item-45586)). É a melhor prova de que 3D estilizado não-low-poly vende para público casual. Recomendação: estudar a reação procedural do mundo a cada compra.
- **Dorfromantik** (96% de 15.855). Visual e trilha são os elogios mais citados ([VaporLens](https://vaporlens.app/app/1455840/dorfromantik)). Técnica: até 5 canais de vertex color como máscaras, paletas por bioma, a noite tratada como troca de paleta e não como reiluminação, uma luz principal com sombras levantadas e névoa leve, paleta validada em escala de cinza e silhuetas legíveis da câmera fixa ([80.lv](https://80.lv/articles/how-dorfromantik-expands-its-cozy-world-through-minimalist-design)). A técnica de troca de paleta é aplicável a um mundo que se transforma em Godot.
- **Townscaper** (95% de 10.650). Cidade que se monta sozinha num diorama sobre a água.
- **Islanders** (95% de 10.227). Ilha-diorama com paleta suave.
- **Timberborn** (96% de 24.651). Mundo 3D estilizado em que a água e o terreno mudam visivelmente.
- **Gnorp Apologue**. Mundo monocromático que ganha cor com o progresso ([Game Developer](https://gamedeveloper.com/design/interview-the-gnorp-apologue)). Recomendação: aplicar como regra de art direction.
- **Sable, Tunic, tilt-shift e fotografia de miniatura:** não coletei evidência de reviews neste ciclo (**não verificado**). Ficam como referências estéticas sugeridas pelo brief, a validar pelo Art Director.

---

## 8. Fontes

- https://pcgamer.com/gaming-industry/steam-week-in-review-54-idle-games-released-on-steam-last-week-and-many-look-eerily-similar
- https://appmagic.rocks/blog/idle-steam-games-2026
- https://gamedev.net/news/3928-incremental-games-have-a-creativity-problem/
- https://newsletter.gamediscover.co/p/how-rustys-retirement-idle-farmed
- https://newsletter.gamediscover.co/p/how-this-solo-dev-incremental-game
- https://www.gamesradar.com/games/simulation/this-is-definitely-my-biggest-life-achievement-idle-stardew-valley-like-rustys-retirement-hits-top-50-highest-rated-steam-games-among-the-11000-released-this-year
- https://gamedeveloper.com/design/interview-the-gnorp-apologue
- https://blog.lauramichet.com/played-nodebuster/
- https://gamedeveloper.com/design/the-math-of-idle-games-part-i
- https://www.gamedeveloper.com/game-platforms/the-math-of-idle-games-part-ii
- https://gamedeveloper.com/design/the-math-of-idle-games-part-iii
- https://gdcvault.com/play/1022065/contactUs
- https://www.slideshare.net/slideshow/quest-for-progress-gdc-europe-2016/65405507
- https://reddit.zackpollard.pro/r/incremental_games/comments/1ko0i7y/what_makes_an_idleincremental_game_actually
- https://vaporlens.app/app/1473350/the_gnorp_apologue
- https://vaporlens.app/app/3107330/nodebuster.md
- https://vaporlens.app/app/1267910/melvor_idle
- https://vaporlens.app/app/977400/cell_to_singularity
- https://vaporlens.app/app/1455840/dorfromantik
- https://www.vzbv.de/sites/default/files/2025-04/25-03-11_Additional_information_vzbv_manipulative_design_online-games.pdf
- https://arxiv.org/html/2412.05039v1
- https://www.pcgamer.com/games/roguelike/ball-bouncing-city-building-off-the-wall-roguelike-ball-x-pit-is-a-huge-hit-selling-300-000-copies-in-just-its-first-five-days-on-sale/
- https://shacknews.com/article/141431/tiny-glade-review-score
- https://wnhub.io/news/stores-and-publishing/item-45586
- https://80.lv/articles/how-dorfromantik-expands-its-cozy-world-through-minimalist-design
- https://rawg.io/games/astrarium
- https://store.steampowered.com/search/?term=astrarium
- https://shikoba.itch.io/crank-engine
- Páginas Steam (app IDs): 3107330, 1473350, 2666510, 3479000, 1454400, 1267910, 1147690, 1353300, 2471100, 1593350, 1399720, 3419430, 2060160, 977400, 3416070, 1999360, 2062430, 1282730, 701160, 1291340, 1046030, 1455840, 2198150, 1062090, 2162800, 2285820, 3749540, 3262910, 2988300, 4276980, 4068780 (formato `https://store.steampowered.com/app/<id>`)
