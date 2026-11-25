# Estudo do kit — exemplos técnicos

Estilo escolhido para estes exemplos: geometria simples com cores sólidas. Não define a direção de arte de futuros jogos. Unidade 3D: metro; Y para cima, frente +Z; pivô na base. Todos são entregas `file`; não há comportamento que precise de runtime neste estudo.

| ID | Técnica e razão | Entrega |
| --- | --- | --- |
| fence | Peças de malha direta: forma rígida e modular, arestas retas | assets/models/fence.glb; 2 × 1 × 0,12 m |
| sdf_rock | Campo escalar convertido em malha: volume orgânico sem topologia manual | assets/models/sdf_rock.glb; volume aproximado de 1,3 m de largura |
| carrot_icon | Canvas: ilustração simples e estática | assets/images/carrot_icon.png; 128 × 128, fundo transparente |

Regeneração, da raiz: `node tools/asset-kit/cli.mjs check "Projetos/Estudo Kit Assets"`.

Os GLBs e o PNG foram reabertos e inspecionados visualmente. As verificações técnicas estão em checks. Estes exemplos não constituem um jogo nem testam importação em Godot; essa validação pertence à integração de cada projeto. Não existe critério de animação neste estudo estático.
