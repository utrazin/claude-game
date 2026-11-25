# Sessão de visualização 2.0

O viewer, o sandbox e a captura usam o runtime de sessão 2.0, com polling coordenado, identidade estável, controle de requisições antigas e prontidão explícita. Não há fallback para o protocolo anterior.

## Uso e atualização

- O viewer mantém seleção e estado de inspeção ao atualizar assets. Erros deixam a versão anterior disponível.
- O shell usa superfícies cinza escuras, navegação por projeto, modo Foco e painéis adaptáveis.
- `/api/health` identifica protocolo, versão do runtime, instância, workspace e escopo. Um servidor de outro workspace não é adotado.
- `/api/catalog` fornece snapshot com `schemaVersion`, revisão opaca, projetos e assets. O parâmetro `project` seleciona o catálogo do projeto. O escopo autorizado pelo servidor continua prevalecendo.
- Sandboxes estão em `projects/<projeto>/sandboxes/<nome>/`. O conteúdo é código livre integrado ao SDK gerenciado.
- Mudança de asset atualiza o conteúdo sem reload da página. Mudança do código da composição reconstrói apenas a página do sandbox, com hooks para salvar/restaurar estado próprio.
- Captura usa `capture=1`, aguarda estado pronto ou falha explícita e desativa o polling do sandbox. `--at` é espera adicional após prontidão.

## Runtime compartilhado

Fonte canônica: `NoctAssetForge2D/viewer/forge-session.js` e `forge-theme.css`. O 3D embarca cópias idênticas, sem depender do checkout irmão durante execução. `runtime-version.json` fixa versão e SHA-256. Os testes de ambos verificam esses hashes.

Após modificar a fonte, executar no 2D: `npm run sync:viewer-runtime -- <caminho-do-repositório-3D>`. Publicar as duas alterações juntas. O servidor continua especializado por renderer: Node/Vite no 2D e Python no 3D.

## Validação

Os testes cobrem seleção, atualização incremental, isolamento entre abas, remoção, cancelamento de requisições, coalescência, distribuição do runtime, câmera/playback, revisões de GLB e atualização de instâncias do sandbox. Os assets de teste são temporários; a suíte não regenera projetos do usuário.

## 3D

`viewer.bat` abre o catálogo global; `py -3.12 -m Tools.forge view <projeto> --open` mantém o modo escopado. O modo global prefere a porta 8765; se estiver ocupada por outro processo, usa a primeira livre entre as 20 seguintes (a URL impressa e a abertura no navegador usam a porta escolhida). `--port` explícito é estrito. Um viewer do mesmo workspace já ativo em qualquer dessas portas é reutilizado; outro workspace/modo/protocolo nunca é adotado. As capturas usam servidores próprios e escopados.

Segurança: o servidor escuta apenas em localhost e rejeita (403) requisições cujo cabeçalho `Host` não seja `127.0.0.1`, `localhost` ou `::1` na porta do servidor (proteção contra DNS rebinding). O código de um sandbox é confiável e roda na mesma origem do viewer. Dados corrompidos no disco (JSON, base64) respondem 500, não 403; erros inesperados também respondem 500 em JSON.

A revisão do backend (`serverRevision`) cobre `viewer_server.py`, `model_viewer.py`, `_resolve.py` e `project_manifest.py`.

Criar: `py -3.12 -m Tools.forge sandbox <projeto> <nome>`. Capturar: `py -3.12 -m Tools.forge capture <projeto> --sandbox <nome>`.

Sandbox no navegador: `/sandbox/<projeto>/<nome>/`. A identificação dos dois componentes é obrigatória. URLs só com projeto, só com nome e aliases que escolhiam o primeiro sandbox foram removidos.

## Animação e inspeção

O inspector à direita tem abas **Animações**, **Hierarquia** e **Visual**. A biblioteca à esquerda lista apenas os assets do projeto escolhido. Ao abrir a biblioteca global sem um asset no URL, o viewer mostra a seleção em vez de carregar um modelo arbitrário.

A aba Animações oferece busca, nomes e durações, seleção de clip e um botão de reprodução por linha. O transporte fica fixo abaixo do viewport: Play/Pause, início, timeline e velocidade. O menu `•••` contém repetição, pose base, tempo numérico e passo de 0,05 s. Trocar de clip mantém a reprodução quando ela já estava ativa. Durante scrub, a reprodução pausa e retoma apenas quando estava ativa. Pausa preserva a pose; Uma vez preserva a pose final. GLB sem metadados de repetição usa repetição como comportamento Original documentado.

Atualizar o mesmo asset mantém câmera completa, clip, tempo, velocidade e play/pause. A navegação explícita tem prioridade sobre o polling, inclusive quando uma atualização do índice já está em andamento. O catálogo de um asset não percorre outros projetos; manifestos validados e metadados de textura são reaproveitados até sua revisão mudar. Payloads JSON maiores usam gzip quando o cliente aceita.

A hierarquia abre subárvores sob demanda e mostra os dados do elemento selecionado em uma área própria, sem renomear o asset. A aba Visual reúne aparência, câmera e referência. Em telas pequenas, os botões Biblioteca/Inspector abrem os painéis. O launcher verifica também a revisão do backend e recusa reutilizar silenciosamente um processo antigo depois de atualização do código.

O SDK `ForgeSandbox` mantém um grupo estável por instância. Atualizações substituem só seu conteúdo e conservam transforms e handle retornado por `add()`. Usar `options.captureState` e `options.restoreState` para estado adicional em reconstruções da composição. Referências diretas a meshes internos devem ser resolvidas novamente quando o conteúdo mudar.

Teste: `py -3.12 -m unittest tests.test_viewer_session tests.test_session_runtime tests.test_project_viewer tests.test_viewer_global tests.test_model_viewer tests.test_sandbox tests.test_capture_preview`.
