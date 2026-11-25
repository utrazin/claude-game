# Inventário público vs interno da API — proposta final

Manual. Critério (de `docs/modules/api-ergonomics/spec.md`, Concluído): a
superfície pública de `lib/` existe para **agentes que escrevem
`generate_model.py` / `generate_texture.py` por etapa** (geometria, UV/textura,
rigging, animação, com dependências bem definidas); **o backend matemático pode
ser tão complexo quanto necessário**. Fase 2 da spec: corrigir
`ModelBuilder.add_loft` para "não somar o pivô do pai nas seções, **eliminando
a necessidade de chamar `loft()` diretamente nos scripts**". Ou seja: público
= o que o agente toca no código da receita (inclusive por encadeamento, sem
`import` direto) + tipos que circulam nesse código + CLI por etapa. Núcleos e
maquinaria de estágio = internos, mesmo com testes próprios.

Método: uso real em receitas (`projects/*/scripts`, só leitura), `Tools/`,
`tests/`, `lib/`, skills/docs + leitura da intenção (docstrings, wrappers,
histórico: `git log -S` mostra exportações por acresção orgânica —
"consolidate", "checkpoint" — sem decisão desenhada de API). Detalhes técnicos
em [generated API reference](api/index.md); mapa em
[lib/ARCHITECTURE](../lib/ARCHITECTURE.md).

**Status: EXECUTADO.** Os 13 saíram dos `__all__` (raiz não os re-exporta
mais); continuam importáveis nos submódulos (`lib.procedural`,
`lib.spatial`, `lib.geometry_types`, `Tools.TexturePainter.export`,
`Tools.TexturePainter.core.color`). `docs/api/` regenerado reflete o novo
`__all__`; `tests/test_api_reference.py` trava a ausência
(`test_internalized_symbols_are_absent`).

**Follow-up executado (eliminação de legado):** os 7 projetos flat foram
modernizados (receitas via `recipe_paths`, layout `assets/<id>/` +
`scripts/<id>/`, `project.json`, sem `legacy:true`); o fallback
não-registrado saiu de `_resolve`/`recipe_context`; `project migrate`,
ramos `legacy` e imports flat do `model_import` foram removidos; viewers
read-only aceitam arquivo `.bbmodel` explícito via `resolve_read_model`;
`uv_options.json`, `.bak`, `history/` e debris (`test_mantle.bbmodel`,
`preview.html`) removidos dos projetos.

## Decisão: `lib` vai para INTERNO (8)

Todos os `add_*` (`add_loft`, `add_sweep`, `add_segment`, `add_revolve`,
`lib/model_builder.py:681-785`) são **supersets ergonômicos**: roteiam pelos
núcleos via `_append_loft`/`_append_mesh` adicionando `placement=`, `pivot=`,
nome do mesh e prefixo de erro `Mesh 'x':`. Chamar o núcleo direto na receita
é estritamente pior (sem placement/pivot, sem contexto de erro) — por isso a
spec manda eliminar essa necessidade. Nenhuma receita chama os núcleos (só
menções em comentários); `Tools/` nunca os importa; skills ensinam só `add_*`.

| Símbolo | Porquê interno (desenho, não só desuso) |
|---|---|
| `loft` | Núcleo do `add_loft`; retorno é geometria crua sem integração ao builder |
| `sweep` | Núcleo do `add_sweep`; idem |
| `segment` | Núcleo do `add_segment`; idem |
| `revolve` | Núcleo do `add_revolve` (`...revolve(...).build()`, `model_builder.py:780`) |
| `segment_sections` | Roteamento intermediário; a docstring admite motivo interno ("para o ModelBuilder rotear… em vez de manter segunda implementação"); o par `path_sections`, do mesmo tipo, **já é interno** |
| `sweep_sections` | Idem |
| `MeshFace` | Nunca nomeado em receita: `MeshDraft` recebe nomes/pontos, `MeshGeometry.create` recebe dados crus (`Tools/recipe_emit.py:170`), e o próprio `place()` constrói `MeshFace` internamente (`model_builder.py:793-796`). Tipo lido, não ferramenta do agente |
| `box_surface_contacts` | Helper puro; o acesso do agente é `get_surface_contact`; nenhuma skill ensina, nenhuma receita chama |

"Interno" = fora do `__all__` raiz, **ainda importável** em `lib.procedural` /
`lib.spatial` / `lib.geometry_types` (como `path_sections` já é) — maquinaria
estável, sem promessa ergonômica.

## Decisão: `lib` fica PÚBLICO (25)

- **Receitas importam (11):** `ModelBuilder`, `Profile`, `SegmentSection`,
  `PathSection`, `Section`, `Frame`, `Path3D`, `Placement`, `MeshDraft`,
  `CapSpec`, `AnimationEditor` (ex.: `projects/chibi_base/.../generate_model.py:31`;
  templates emitidos em `Tools/model_import.py:41,63`).
- **Tipos de entrada — estendem o que o agente pode expressar (5):**
  `RelativePath`/`Curve` (alternativas de `path=` com `resolve()`,
  `model_builder.py:754-757`), `ChainSegment` (alternativa tipada a dicts,
  ensinada em `box-modeling.md`, `model_builder.py:905`), `JointBlend` (tipo
  exigido do parâmetro público `bind(joints=)`, `model_builder.py:1824-1826`),
  `ModelOrientation` (parâmetro `ModelBuilder(orientation=)`).
- **Tipos encontrados/retornados no código do agente (7):** `SpatialFrame`,
  `SurfaceContact`, `PrimitiveHandle` (`builder.last`), `ArmatureHandle`,
  `BindingReport`, `AnimationControl`, `MeshGeometry` (aceito por `add_mesh`,
  lido por `recipe_emit`).
- **Utilitários do idioma documentado (2):** `linear_falloff`,
  `smooth_falloff` (fatores de `weights=`, `shapes.md`).

## Decisão: `TexturePainter` vai para INTERNO (5)

`TextureExporter` só existe dentro de `TexturePainter.save()`
(`painter.py:1112-1124`); `parse_color`, `color_add_noise`, `color_lerp`,
`color_adjust_brightness` validam/operam cores que **fluem** pelas receitas,
mas nenhuma receita os importa — nenhuma skill ensina a importá-los (o contrato
de cores vive no texto da skill + mensagens de erro, que não mudam). Entraram
no `__all__` no commit de checkpoint `955175f`, sem desenho de API.

## Decisão: `TexturePainter` fica PÚBLICO (11) — correção à métrica crua

Import direto subconta: o idioma da receita é **navegação/encadeamento**
(`element.band().fill()`, `field.paint()`, `paint_surface(sample)`), e esses
11 são todos tocados ali: `TexturePainter`, `ElementPainter`, `FacePainter`,
`FaceCanvas` (base de `DecalCanvas`/`CanvasRegion`, tipo de `face.canvas` e
`blit`), `DecalCanvas` (construção documentada), `CanvasRegion`,
`ElementSelection`, `SurfaceRegion`, `SurfaceSample` (atributos lidos no
callback, documentados na skill), `ContactField`, `FieldHit`.

## Decisão: contexto, UV e CLI ficam PÚBLICOS

`recipe_paths` (receitas importam), `RecipePaths` (type-only),
`recipe_environment` (tooling CLI-side, rotular como tal), `UVBuilder` (API de
receita avançada `share_uv`, 46 usos em testes, caminho `auto_uv`) e os 17
comandos `Tools.forge` (todos com usuários nas skills/docs).

## Cheiros (observar, fora de escopo sem pedido)

1. ~~`projects/goblin/.../generate_model.py:20` importa `Placement` via
   `lib.geometry_types`~~ — corrigido para `from lib import` na modernização
   das receitas.
2. `Tools/` importa `lib` por deep paths — correto como uso interno, não é
   evidência de API pública.
3. `Tools/__init__.py` re-exporta 9/16 (inclui os 5 internos, omite
   `DecalCanvas`, público de fato) — limpar junto na execução.

## Proposta final de execução (EXECUTADA)

1. `lib/__init__.py`: removidos do `__all__` e da re-exportação raiz os 8
   (`lib` agora tem 25; `Tools/TexturePainter`, 11);
   `Tools/TexturePainter/__init__.py` + `Tools/__init__.py`: removidos os 5.
2. Docstrings "deliberately public" (`segment_sections`,
   `sweep_sections`) → "roteamento interno".
3. Migrados 5 imports de teste para deep paths (precedente já usado no repo):
   `test_concave_cap_message.py` (`loft`→`lib.procedural`),
   `test_low_poly_api.py` (`loft`, `segment_sections`, `sweep_sections`),
   `test_polygon_api.py` + `test_procedural_modeling.py`
   (`MeshFace`→`lib.geometry_types`; `loft`, `sweep`, `revolve`→`lib.procedural`),
   `test_surface_contacts.py` (`box_surface_contacts`→`lib.spatial`).
4. Regenerado `docs/api/`, índice atualizado e
   `tests/test_api_reference.py` com trava de regressão.
5. Verificação: `--check`, suíte completa, `git diff --check`.

Resumo: **25 PÚBLICO + 8 INTERNO em `lib`** (33), **11 PÚBLICO + 5 INTERNO em
`TexturePainter`** (16), **4 + 17 PÚBLICOS** (contexto/UV/CLI). Nenhuma receita
ou skill importa os 13 internalizáveis — migração zero fora de 4 arquivos de teste.
