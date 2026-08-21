# Extrator SP Sports — aplicação base (TCC)

Exemplo mínimo de **web scraping de site dinâmico** (feito no Bubble.io).
Parte dos dados não vem no HTML pronto, então a aplicação combina duas
técnicas: uma chamada direta à **API JSON** do site (leve, sem navegador) e
um **navegador real controlado por Playwright** para o que só aparece depois
da interação.

## O que ele faz

**Técnica 1 — API JSON (sem navegador).**
Chama `https://webarena.app/api/1.1/init/data` com `requests` e lista os
esportes disponíveis direto do JSON, sem abrir o Chromium.

**Técnica 2 — navegador headless (Playwright).**
1. Abre `https://webarena.app/arena/sp-sports`
2. Percorre os **quatro tipos de quadra de interesse** — Vôlei de praia, Futebol de
   salão, Grama 7 e Grama 5 — ignorando os demais esportes do site
3. Para cada um, percorre o **dia atual e os próximos** (`DIAS_A_FRENTE`), achando cada
   data no calendário pelo `aria-label` da célula (`21/08/26 - sexta-feira`)
4. Percorre os períodos **Manhã**, **Tarde** e **Noite**
5. Em cada período, percorre **cada quadra** do esporte separadamente
6. Imprime os horários de cada quadra (🟢 Livre / 🔴 Indisponível) e quantas vagas ficaram livres

O **preço só é aberto no dia de hoje**. Ler o valor custa um clique por horário livre, e
os dias à frente são quase todos livres; cada um deles ainda será visitado no seu próprio
dia, que é quando o preço entra na linha.

Um esporte que falhe por lentidão do site é reportado e pulado, sem derrubar a coleta
dos demais; uma execução que não colete nada sai com código de erro, em vez de gravar
silêncio — o modo de falha mais caro num coletor agendado.

## Os módulos

| Arquivo | Papel |
| --- | --- |
| `main.py` | **Ponto de entrada.** Chama os coletores em sequência, imprime o relatório e manda gravar |
| `config.py` | O que se edita: URL da arena, coordenadas, tipos de quadra, diretório de saída |
| `courts_collector.py` | Coleta das reservas — API JSON e navegador. É biblioteca, não roda sozinho |
| `weather_collector.py` | Coleta as condições atuais e a previsão hora a hora, pela API Open-Meteo |
| `tratamento.py` | Casa clima e previsão com as reservas: a janela do jogo e o instante da reserva |
| `persistencia.py` | Gravação do CSV por quadra, com upsert. Não depende do Playwright |

A separação não é enfeite: `persistencia.py` é importado por quem não abre navegador
nenhum, e o coletor carrega o Playwright já no `import`. Juntos, um consultaria o
Chromium para ler o nome de uma coluna.

## Configuração

Tudo que muda de instalação para instalação vive em `config.py` — a URL da arena, as
coordenadas usadas na consulta de clima e o diretório onde as extrações são gravadas.
Trocar de arena é editar uma linha, sem abrir o coletor.

`DIAS_A_FRENTE` é o quanto a coleta enxerga além de hoje (2, ou seja, três dias por
rodada). É o parâmetro que decide quanta antecedência de reserva o histórico consegue
registrar, e o que mais pesa no tempo de execução: cada dia a mais custa por volta de
meio minuto por rodada. O site libera 60 dias, então o teto é prático, não do site. A
previsão acompanha o mesmo horizonte automaticamente.

## Saída: um CSV por quadra

Cada quadra encontrada ganha o seu próprio arquivo, `<slug-da-quadra>-extracoes.csv`,
criado na primeira vez que ela aparece — `futsal-interna-extracoes.csv`,
`areia-4-externa-extracoes.csv` e assim por diante. É o que garante a unicidade do
horário: um esporte pode ter várias quadras (o vôlei de praia tem quatro), e o `17:00`
de uma nunca deve disputar linha com o `17:00` de outra.

Duas colunas saem do nome da quadra: `tipo_quadra`, normalizada para `Vôlei de praia`,
`Futebol de salão`, `Grama 7` ou `Grama 5`; e `quadra_coberta`, `true` para
interna/coberta e `false` para externa/descoberta.

## Quando a reserva foi feita

Coletando só o dia atual, um horário das 20:00 que já aparece `Indisponível` às 09:00 não
conta nada: ele foi reservado antes, e não há como saber quando. **A hora da reserva não
se lê, se testemunha** — é preciso ter visto o horário livre em uma rodada e ocupado na
seguinte. Daí a coleta dos dias à frente: o horário passa a ser observado desde três dias
antes do jogo, e a virada de status acontece sob observação.

Quatro colunas registram isso:

| Coluna | O que guarda |
| --- | --- |
| `primeira_coleta` | Quando aquele horário entrou em observação pela primeira vez |
| `reservado_em` | A rodada em que ele passou de `Livre` a `Indisponível` |
| `periodo_da_reserva` | Em que período do dia isso aconteceu — inclusive `Madrugada` |
| `antecedencia_horas` | Quantas horas separavam a reserva do início do jogo |

`periodo_da_reserva` tem quatro valores, e não três: o site só vende Manhã, Tarde e Noite
porque a arena não abre de madrugada, mas **reservar** às três da manhã acontece, e é a
hora da reserva que essa coluna descreve — não a do jogo, que continua em `periodo`.

`reservado_em` vazio quer dizer uma de duas coisas, e é `primeira_coleta` que distingue:
com o status `Livre`, ninguém reservou; com o status `Indisponível`, o horário **já
chegou ocupado** à primeira observação, e a hora da reserva é anterior ao histórico. Uma
coisa que a coluna nunca faz é chutar: carimbar a hora da coleta seria inventar dado.

Um cancelamento — de `Indisponível` de volta para `Livre` — **apaga** o que a reserva
deixou: as três colunas que a descrevem e os dois blocos de clima congelados na virada
(`reserva_*` e `previsao_*`). Manter o carimbo antigo seria afirmar uma reserva que não
existe mais; se o horário for reservado de novo, a próxima virada grava a data nova.
`primeira_coleta` fica de fora: a observação daquele horário não recomeçou.

> A virada é detectada **na gravação**, comparando o status que está no CSV com o que a
> coleta acabou de trazer. Só vale enquanto o horário está no futuro: depois que o jogo
> começa a linha congela, como já congelava para status e preço.

## Clima: uma tabela à parte

Cada execução também registra as condições do momento na arena, pela API pública da
[Open-Meteo](https://open-meteo.com), em `clima-leituras.csv` — um arquivo só, série
temporal, uma linha por leitura. As coordenadas ficam no `config.py`.

O `weather_code` da API é um número; a tradução para texto (`Encoberto`, `Chuva
fraca`, `Trovoada`…) acontece **na extração**, para o histórico nascer legível. Um
código fora do mapa grava descrição vazia, mas o número bruto fica em `codigo_clima`:
lacuna a investigar é melhor do que clima errado.

A API já devolve o horário arredondado em baldes de 15 minutos, e é esse horário que
serve de chave — duas coletas no mesmo balde atualizam a mesma linha em vez de inchar
o arquivo. As unidades são fixas: °C, %, mm e km/h.

O sufixo do arquivo é `-leituras.csv`, e não `-extracoes.csv`, de propósito: quem varre
as quadras por padrão de nome não pode topar com a tabela de clima no meio do caminho.
Vale o mesmo para `clima-previsoes.csv`.

Uma queda da Open-Meteo **não derruba a execução**: o aviso vai para o `stderr` e as
quadras, que são o dado caro de coletar, seguem gravadas.

## Previsão: a outra tabela de clima

Reserva feita dois dias antes não se explica pelo tempo que fazia na hora do jogo — se
explica, se é que o tempo pesou, pela **previsão que estava publicada quando a pessoa
reservou**. Por isso a mesma API é consultada duas vezes por rodada, com perguntas
diferentes: `clima-leituras.csv` guarda o que está acontecendo agora, e
`clima-previsoes.csv`, o que se espera hora a hora nos dias que a coleta percorre.

As duas tabelas se comportam de maneira oposta, de propósito:

- **leituras** é histórico e só cresce: uma observação do passado nunca muda;
- **previsões** é reescrita inteira a cada rodada, porque de uma hora prevista só
  interessa a versão mais recente. A versão antiga que importa guardar já está congelada
  na linha da reserva que ela ajudou a explicar.

A previsão traz uma variável a mais que a observação, `probabilidade_chuva`, que só
existe para o futuro — não há probabilidade de uma chuva que já caiu.

## A janela de clima de cada reserva

Cada linha carrega **três blocos de clima**, com as mesmas cinco variáveis, respondendo a
perguntas diferentes. Confundi-los é fácil, e a diferença é o ponto:

| Bloco | Que instante descreve | Quando é escrito |
| --- | --- | --- |
| `clima`, `temperatura`, … | O tempo pouco antes do jogo | Rodada a rodada na janela — vale a **última** |
| `reserva_*` | O tempo na hora em que a pessoa reservou | Uma vez, na virada de status |
| `previsao_*` | O que se previa para a hora do jogo | Uma vez, na virada de status |

Depois das duas coletas, o `tratamento.py` escreve `clima`, `temperatura`, `umidade`,
`precipitacao` e `velocidade_vento` nas reservas — mas só nas que estão na **janela**:
de 4 horas antes até 1 hora antes do horário reservado, com as duas pontas incluídas.

Para uma reserva das 20:00, com coleta a cada 15 minutos:

```
15:00  (-5h)     não escreve — a observação envelheceria até o jogo
16:00  (-4h)     escreve            <- primeira
17:30  (-2h30)   sobrescreve
19:00  (-1h)     sobrescreve        <- última, é a que fica
19:30  (-30min)  não escreve
20:00            não escreve — o registro já está congelado
```

Cada rodada dentro da janela vale mais que a anterior, então **o que fica gravado é a
observação de uma hora antes da reserva** — a mais próxima do jogo. Fora da janela as
colunas ficam vazias, e vazio aqui quer dizer "não houve observação nessa janela", não
"choveu zero". Os limites são editáveis em `config.py`.

Duas recusas deliberadas: leitura de clima **futura** é ignorada (indica relógio
desalinhado, não previsão), e leitura **velha demais** também
(`TOLERANCIA_LEITURA_CLIMA_MIN`) — carimbar numa reserva o clima de três horas atrás é
pior do que deixar a lacuna.

### O clima que fazia na hora de reservar

A mesma virada de status que data a reserva serve para saber **que tempo fazia quando ela
foi feita**: detectado o `reservado_em`, o tratamento procura no histórico de observações
a leitura daquele instante e a congela em `reserva_clima`, `reserva_temperatura`,
`reserva_umidade`, `reserva_precipitacao` e `reserva_velocidade_vento`.

É a variável que faltava para a pergunta do trabalho. `previsao_*` diz o que a pessoa
**esperava** para a hora do jogo; `reserva_*` diz o que ela estava **vendo pela janela** na
hora de decidir. Uma tarde de chuva enche a quadra coberta na mesma medida em que esvazia
a de areia, e isso não aparece na previsão do jogo nem na observação de uma hora antes.

A leitura escolhida é a **mais próxima do instante da reserva, antes ou depois dele**: a
API arredonda o horário em baldes de 15 minutos, então a reserva das 14:32 fica entre a
leitura das 14:30 e a das 14:45, e as duas descrevem o mesmo tempo. Se nem a mais próxima
estiver dentro de `TOLERANCIA_LEITURA_CLIMA_MIN` — a rodada em que a Open-Meteo caiu —, a
coluna fica vazia, pela mesma regra da janela: clima de outra hora é pior do que a lacuna.

Escrito uma vez, o bloco não é reescrito: ele descreve um instante que já passou. Enquanto
ninguém reservou, fica vazio — é propriedade da reserva, não do horário.

### A previsão congelada no ato da reserva

As cinco colunas `previsao_*` espelham exatamente as observadas, e por isso dá para
comparar as duas ponta a ponta: o que se esperava do tempo contra o que de fato fez. Elas
seguem a regra inversa da janela — em vez de a última rodada valer, **vale a primeira**.

Detectada a virada de status, o tratamento copia para a linha a previsão daquela hora e
não mexe mais: é a resposta a "o que se sabia do tempo na hora de reservar". Uma previsão
melhor, feita horas depois, já não é o que a pessoa viu. Slots de meia hora usam a
previsão da hora cheia (a reserva das 21:30 pega a das 21:00), porque a Open-Meteo prevê
de hora em hora.

Enquanto ninguém reservou, as colunas ficam vazias: a previsão congelada é propriedade da
reserva, não do horário. E se a previsão daquela hora não estiver na tabela — por estar
além do horizonte, ou porque a API caiu naquela rodada —, a coluna fica vazia em vez de
receber a previsão de outra hora; havendo falha, a rodada seguinte preenche.

> A comparação de horários usa o relógio da máquina, e a API responde no fuso de
> `config.FUSO_HORARIO`. Numa VPS em UTC a janela erra por 3 horas em silêncio: mantenha
> o servidor em `America/Sao_Paulo`.

## Instalação
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso
```bash
python main.py          # roda sem abrir janela (headless)
python main.py --ver    # abre o navegador pra você ASSISTIR o passo a passo
```

## Testes

```bash
pip install -r requirements-dev.txt
pytest
```

A suíte padrão roda **offline**: as regras puras (slug, tipo e cobertura da quadra,
preço, CSV) e a extração contra *fixtures* — cópias congeladas do HTML real do site,
em `tests/fixtures/`. Elas exercitam os seletores CSS de verdade sem depender do site
no ar.

Separado disso há o **canário**, o único teste que acessa a rede. Ele não afirma
valores (horário e preço mudam de hora em hora), só a forma: o seletor ainda encontra
quadras, elas ainda têm nome, a nomenclatura de cobertura continua reconhecível e o
calendário ainda libera os dias à frente com o `aria-label` no formato esperado. É o
que avisa quando o site é republicado e o scraper para de achar as coisas — inclusive no
modo de falha mais discreto, em que a coleta continua funcionando mas só enxerga hoje, e
a hora da reserva some do histórico sem nenhum erro.

```bash
pytest -m rede                        # roda o canário, sob demanda
python scripts/capturar_fixtures.py   # regrava as fixtures com o HTML de hoje
```

## Agendamento

A série temporal não se produz à mão. Quem dispara a coleta é o `cron`, chamando
`scripts/rodar_extracao.sh` — nunca o `main.py` direto:

```bash
crontab -e
```

```
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
HOME=/home/tavares
TZ=America/Sao_Paulo
CRON_TZ=America/Sao_Paulo
MAILTO=""

*/15 * * * * /caminho/para/projeto-codigo-tcc/scripts/rodar_extracao.sh
```

O `PATH` é declarado porque o `cron` do Ubuntu **herda** o do ambiente em vez de fixá-lo,
e o wrapper precisa de `flock`, `timeout` e `logger`. `TZ` e `CRON_TZ` são redundantes
numa máquina já em `America/Sao_Paulo` e existem para o caso da VPS — sem eles a janela
de clima erra por 3 horas em silêncio.

### Por que um wrapper, e não a linha crua no crontab

Duas coisas que uma linha de crontab não faz. A primeira é o `cd`:
`DIRETORIO_EXTRACOES` é um caminho **relativo**, então uma execução a partir de outro
diretório criaria um `.extracoes/` paralelo no `$HOME` e partiria o dataset em dois, sem
avisar. A segunda é o `flock`: a gravação lê o CSV inteiro e reescreve, de modo que duas
rodadas sobrepostas se sobrescrevem por completo — a que terminar por último apaga os
slots que a outra acabou de inserir. Rodada que encontra a trava tomada **sai com 0** e
anota "pulado" no log; ela não entra na fila, porque a rodada em andamento já está
colhendo dado mais fresco do que a duplicata colheria.

Um `timeout` de 5 minutos fecha o terceiro buraco: sem ele, um Chromium travado seguraria
a trava para sempre e mataria todas as coletas seguintes. Uma rodada normal leva por volta
de **2min30s** com `DIAS_A_FRENTE = 2`, então o limite ainda é folgado — quando ele
dispara, o código é 124, distinguível do 1. Quem aumentar o horizonte precisa refazer essa
conta: cada dia a mais custa cerca de meio minuto, e passar de 7 dias encosta no limite.

### Por que 15 minutos, o dia inteiro

O intervalo sai da seção anterior: dentro da janela de cada reserva, a última rodada é a
que fica, e a cada 15 minutos a observação gravada é sempre de uma hora a uma hora e
quinze antes do jogo. Também é folga contra falha — quando a Open-Meteo cai, o tratamento
recorre à leitura anterior, que só vale se tiver menos de `TOLERANCIA_LEITURA_CLIMA_MIN`;
com 15 minutos de intervalo ela vale sempre, e a rodada enriquece mesmo com a API fora.

O intervalo também é a **resolução** de `reservado_em`: a reserva é datada na rodada que a
enxergou, então 15 minutos é a margem de erro da hora registrada — e o teto da precisão
que `antecedencia_horas` pode ter.

O dia inteiro porque a coleta parte sempre do **dia atual**: à 00:15 o calendário já
aponta para a data nova e o CSV nasce completo desde a meia-noite. As rodadas da madrugada
não escrevem clima observado — para uma delas cair na janela seria preciso um horário
entre 03:00 e 06:00, e a arena vai das 09:30 às 23:00 — mas são justamente elas que
flagram a reserva feita de madrugada, nos horários que ainda estão no futuro.

### Quando alguma coisa falha

Não há e-mail: a máquina não tem MTA, e o `MAILTO=""` declara isso em vez de deixar o
`cron` falando sozinho. O rastro fica em três lugares:

```bash
tail .logs/execucoes.csv                            # instante, código e duração por rodada
awk -F, 'NR > 1 && $2 != 0' .logs/execucoes.csv     # só as que falharam
journalctl -t extrator-sp-sports -p err --since today
less .logs/extracao-$(date +%F).log                 # o relatório completo da rodada
```

O `execucoes.csv` é o que se olha primeiro — uma linha por rodada que chegou a rodar. A
rodada pulada não deixa linha ali, de propósito: ela sai antes, e o ledger é o registro do
que foi coletado, não do que o `cron` tentou. Quem conta as puladas é o log do dia, com
`grep -c "pulado: a execução anterior"` — subindo, é sinal de que a cadência ficou
apertada para a duração real. O padrão importa: `grep pulado` sozinho também casaria com
o esporte pulado por tempo esgotado, que é degradação normal, não disputa de trava.
Os logs são podados depois de 14 dias; ficam cerca de 20 KB por rodada, uns 25 MB em
regime — o relatório cresceu junto com os dias coletados. `.logs/` fica fora do Git, como
`.extracoes/`.

> O `cron` não recupera execução perdida, e `anacron` não cobre intervalo menor que um
> dia. Máquina suspensa, desligada ou sem rede vira buraco na série temporal — num
> desktop isso é aceitável se for documentado; o que fecha de vez é subir para uma VPS.

## Próximos passos (para evoluir no TCC)
- **Alertar**: notificar quando um horário mudar de "Indisponível" para "Livre" — a
  virada já é detectada na gravação, falta o aviso
- Parametrizar esporte/período/data via argumentos de linha de comando
  (a função `coletar_horarios` já aceita `esporte`, `periodo` e `dias_a_frente`; o
  `main.py` percorre os quatro tipos de quadra, mas não aceita recorte pela linha de
  comando)
- Preencher `feriado`, `evento_grande` e `jogo_em_porto_alegre`, as três colunas de
  contexto que existem no CSV e ainda nascem vazias

## Conceito-chave
Sempre desça a "escada" do mais leve pro mais pesado:
`requests` (HTML estático) → **API JSON** (aba Network) → **navegador headless**.
Esta aplicação usa os dois últimos degraus de propósito: a lista de esportes
sai da API JSON (barato), e os horários — que só existem depois de clicar no
esporte, no dia e no período — exigem o navegador.