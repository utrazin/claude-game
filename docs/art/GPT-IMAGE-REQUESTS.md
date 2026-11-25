# Solicitações ao GPT Image (departamento externo de Concept Art)

Fluxo: o diretor escreve o briefing → Enzo gera → o diretor avalia (APPROVED / CHANGES REQUESTED / REJECTED) → aprovadas viram referência oficial em `docs/art/approved/`.

Regras gerais para todas as solicitações:
- Nada de steampunk vitoriano: sem vapor, cartolas, óculos de aviador, rebites decorativos, tubos de cobre, sépia.
- Nada de low poly, flat shading, cel shading duro ou visual mobile.
- Nada de neon ciano/magenta ou brilho genérico.
- Sem texto legível na imagem (o GPT Image erra letras); numerais romanos no mostrador só como forma.

---

## AST-CA-001 — Key art de atmosfera (exploração de direção)

- **Estado:** BRIEFING
- **Objetivo:** fixar a atmosfera, a paleta e a escala do jogo numa única imagem. Vai orientar a Art Bible, a iluminação na Godot e o material de loja.
- **Contexto no jogo:** a sala única do jogo: o topo de uma torre-observatório de pedra onde o jogador reconstrói o Astrarium, um enorme relógio astronômico que move o céu. Este é o estado "meio do jogo": o mecanismo já está grande e vivo, mas parte da cúpula ainda está apagada.
- **Descrição visual:** interior circular de uma torre de pedra clara e antiga. No centro, um mecanismo de relojoaria monumental, de 4 a 5 metros de altura, feito de rodas de latão com raios curvos, pinhões de aço azulado a fogo, armações de latão parafusadas com parafusos azuis, mostradores de esmalte creme com anéis de latão gravados. Do topo do mecanismo saem braços finos de latão que sustentam esferas planetárias (uma de lápis-lazúli, uma de prata, uma de âmbar). Acima, uma cúpula de vidro e ferro trabalhado abre-se para o céu noturno; algumas estrelas brilham, outras regiões do céu estão escuras e "paradas". Bancada de nogueira com ferramentas de relojoeiro em primeiro plano, em leve desfoque.
- **Direção artística:** realismo estilizado premium, como uma maquete de museu iluminada à noite. Proporções levemente exageradas (engrenagens mais grossas e dentes mais marcados que na vida real) para leitura. Superfícies com microdetalhes: escovado no latão, gravuras finas, desgaste nas bordas.
- **Composição:** o mecanismo ocupa o terço central, levemente abaixo do centro. A cúpula e o céu ocupam o terço superior. Primeiro plano escuro com a bancada. Linhas dos braços planetários conduzem o olhar para cima.
- **Perspectiva:** câmera a cerca de 3 m de altura, olhando levemente para cima, lente equivalente a 35 mm.
- **Paleta:** latão quente (#C8963E), latão envelhecido (#8A6A3A), aço azulado (#2B3F6B), esmalte creme (#EDE6D6), nogueira (#3B2416), azul ultramar da noite (#0F1A33), ouro estelar (#F2D27A). Pedra da torre em cinza quente claro.
- **Iluminação:** duas fontes em contraste. Luz quente de lamparinas a óleo e velas na altura da bancada. Luz fria e azulada da noite entrando pela cúpula. Brilhos especulares nítidos no latão. Sem bloom exagerado.
- **Materiais:** latão polido e escovado, aço azulado a fogo, esmalte vitrificado, nogueira encerada, vidro antigo levemente ondulado, pedra calcária.
- **Restrições:** ver regras gerais. Sem personagens. Sem texto.
- **Formato:** 16:9 paisagem, maior resolução disponível.

**Prompt (copiar e colar):**

```
Cinematic key art, interior of the top chamber of an ancient circular stone observatory tower at night. In the center stands a monumental astronomical clockwork mechanism, about 5 meters tall: large polished brass wheels with elegant curved spokes, heat-blued steel pinions and blue steel screws, engraved brass frame plates, cream vitreous enamel dials with fine brass rings, and slender brass arms rising from its top that hold planetary spheres of lapis lazuli, silver and amber. Above, a wrought iron and old glass dome opens to a deep ultramarine night sky; some regions of the sky have bright stars, other regions are dark and still. In the foreground, a waxed walnut workbench with horologist tools, slightly out of focus. Warm light from oil lamps and candles at bench height contrasts with cool blue moonlight falling through the dome. Crisp specular highlights on brass, brushed metal micro detail, fine engravings, subtle wear on edges. Premium stylized realism, like a museum diorama photographed at night, slightly exaggerated chunky gear proportions for readability. Camera at 3 m height looking slightly up, 35mm lens, mechanism in the central third, dome and sky in the upper third. Palette: warm brass gold, aged brass, heat-blued steel, cream enamel, dark walnut, deep night ultramarine, soft star gold. No steampunk, no steam, no pipes, no rivets, no top hats, no neon, no low poly, no flat shading, no people, no text, no letters. 16:9.
```

---

## AST-CA-002 — Folha de estudo de materiais

- **Estado:** BRIEFING
- **Objetivo:** definir como cada material do jogo deve parecer, para eu calibrar os shaders PBR da Godot e os bakes do Blender.
- **Contexto:** peças isoladas que aparecem em todo o jogo.
- **Descrição visual:** folha de referência em fundo neutro escuro, 6 peças lado a lado em grade 3x2, iluminadas igual: (1) roda de latão de 60 dentes com raios curvos, latão polido com marcas de escovado circular; (2) pinhão e parafusos de aço azulado a fogo, com a variação azul-violeta típica; (3) mostrador de esmalte creme com numerais romanos pintados à mão e anel de latão gravado com padrão guilloché; (4) placa de armação de latão envelhecido com gravura floral fina e pátina nas cavidades; (5) bloco de nogueira encerada com veios visíveis e friso de latão; (6) esfera planetária de lápis-lazúli com veios dourados presa num anel de latão.
- **Direção artística:** fotografia de produto de alta qualidade, realismo estilizado; materiais nítidos, sem plástico.
- **Composição:** grade 3x2, peças centralizadas em cada célula, mesmo tamanho aparente.
- **Perspectiva:** vista 3/4 superior, lente 85 mm, sem distorção.
- **Paleta:** a mesma de AST-CA-001.
- **Iluminação:** estúdio, luz principal quente suave à esquerda, contraluz fria à direita para recortar as bordas, fundo cinza-azulado escuro.
- **Restrições:** sem texto, sem rótulos, sem steampunk, sem neon.
- **Formato:** 3:2 paisagem.

**Prompt:**

```
Material study sheet for a premium game, six objects arranged in a clean 3x2 grid on a dark blue-grey studio background, identical lighting in every cell: 1) a polished brass clock wheel with 60 teeth and elegant curved spokes, circular brushing marks; 2) heat-blued steel pinion and screws with the characteristic blue-violet temper color; 3) a cream vitreous enamel clock dial with hand-painted Roman numerals and a brass ring engraved with guilloche pattern; 4) an aged brass frame plate with fine floral engraving and dark patina in the recesses; 5) a block of waxed walnut wood with visible grain and a thin brass inlay; 6) a lapis lazuli planetary sphere with golden pyrite veins held in a brass ring. High-end product photography, stylized realism, crisp materials, no plastic look. Warm soft key light from the left, cool rim light from the right, 3/4 top view, 85mm lens. No text, no labels, no steampunk, no neon, no low poly. 3:2.
```

---

## AST-CA-003 — Tira de progressão do mundo (4 estados)

- **Estado:** BRIEFING
- **Objetivo:** validar visualmente a promessa central: o jogador vê sua evolução no próprio mundo. Vai virar a especificação dos estados do cenário.
- **Contexto:** a mesma sala da torre, mesma câmera, em quatro momentos do jogo.
- **Descrição visual:** quatro painéis verticais lado a lado, mesma câmera e enquadramento:
  1. **Silêncio:** sala escura, coberta de poeira, uma única roda de latão sobre a bancada, uma vela acesa, cúpula fechada, céu sem estrelas.
  2. **Primeiro tique:** um pequeno trem de 4 ou 5 engrenagens montado sobre uma base de nogueira, um pêndulo, algumas lamparinas acesas, uma fresta da cúpula aberta mostrando poucas estrelas.
  3. **Máquina viva:** mecanismo de 2 metros com vários mostradores de esmalte e o primeiro braço planetário com a Lua de prata, metade da cúpula aberta, uma constelação acesa.
  4. **Firmamento:** mecanismo monumental até o teto, vários planetas em órbita em braços de latão, cúpula toda aberta, céu cheio de estrelas e constelações desenhadas por finas linhas douradas.
- **Direção artística, paleta, materiais:** como em AST-CA-001. A temperatura da cena vai do frio e apagado (1) ao quente e luminoso (4).
- **Composição:** 4 painéis iguais, divisões finas e escuras entre eles, mecanismo sempre no mesmo ponto.
- **Perspectiva:** frontal, 3/4 levemente acima, 35 mm.
- **Restrições:** gerais. Sem texto.
- **Formato:** 21:9 ou 2:1 paisagem.

**Prompt:**

```
Four-panel progression strip of the same scene from the identical camera angle, side by side, separated by thin dark dividers. The scene: the top chamber of an ancient circular stone observatory tower with a wrought iron and glass dome. Panel 1 "silence": dark dusty room, a single brass clock wheel lying on a walnut workbench, one candle lit, dome closed, no stars. Panel 2 "first tick": a small train of five brass gears with heat-blued steel pinions mounted on a walnut base, a pendulum, a few oil lamps lit, a narrow slit of the dome open showing a few stars. Panel 3 "living machine": a 2 meter tall clockwork mechanism with several cream enamel dials and the first slender brass planetary arm holding a silver moon, half of the dome open, one constellation glowing. Panel 4 "firmament": a monumental astronomical clockwork reaching the ceiling, many planets of lapis lazuli, amber and silver orbiting on brass arms, the dome fully open to a deep ultramarine sky full of stars with constellations traced by fine golden lines. The color temperature goes from cold and dim in panel 1 to warm and luminous in panel 4. Premium stylized realism, museum diorama at night, crisp brass highlights, fine engravings. No steampunk, no steam, no pipes, no neon, no low poly, no people, no text. 21:9.
```
