# Plano de correção da exportação de animações

## Decisão

O BBModel continua sendo a fonte serializada. A exportação para GLB deve converter a
semântica de animação do Blockbench para os canais que o glTF consegue representar.
GLB é o formato 3D de entrega. As animações são amostradas diretamente durante essa
conversão a partir do BBModel.

“Sem limitações” não pode significar serializar qualquer recurso do Blockbench em
qualquer formato: glTF define canais de animação próprios. O objetivo é não impor
restrições artificiais quando o Blockbench consegue avaliar um movimento e o glTF
consegue representá-lo como uma curva amostrada. Recursos sem representação glTF,
como efeitos/eventos, devem ser identificados claramente, nunca descartados em
silêncio.

## Etapas

1. **Registrar as diferenças confirmadas.** Comparar o conversor do projeto com o
   exportador GLTF oficial e corrigir as afirmações documentais anteriores.
2. **Completar a conversão determinística dos canais TRS.** Manter posição, rotação e
   escala; amostrar Bezier junto com Catmull-Rom; preservar keyframes descontínuos
   com múltiplos pontos de dados; aceitar frequência de amostragem definida no job.
3. **Avaliar expressões por instante.** Resolver expressões determinísticas comuns do
   Blockbench para números finitos durante o bake. Usar tempo da animação e valor
   anterior do canal quando presentes. Expressões que dependam de variáveis/contexto
   externo precisam produzir erro com o canal, eixo e expressão, em vez de perda
   silenciosa.
4. **Detectar recursos não conversíveis.** Verificar animadores sem nó, canais de
   extensão e efeitos. Canais TRS não reconhecidos como dados válidos causam erro
   explícito. Recursos sem equivalente glTF ficam identificados no diagnóstico.
5. **Documentar as fronteiras reais.** Distinguir dados animados que o conversor pode
   amostrar, dependências de avaliação que precisam de contexto e semânticas que o
   próprio formato de destino não representa.
6. **Aceitação.** Conferir a estrutura dos samplers GLB em casos lineares, STEP,
   Catmull-Rom, Bezier, expressão temporal, descontinuidade e bone; conferir também
   que dados não conversíveis falham de forma explícita. Reimportar GLB para confirmar
   os clips e canais exportados.

## Aplicado

Foram aplicadas as etapas 2–5 ao conversor existente. A avaliação Molang abrange
expressões numéricas determinísticas com operadores matemáticos, funções matemáticas,
`query.anim_time`, `query.life_time` e `this`. Variáveis globais, chamadas que dependam
da cena/editor e efeitos não são constantes exportáveis sem contexto; agora são
relatados em vez de ignorados. A API de receita também expõe Bezier e seus handles.
A fidelidade se mede sobre os valores amostrados, pois glTF não guarda a expressão
executável do Blockbench. A etapa de aceitação ainda requer execução da suíte e
reimportação de GLB.
