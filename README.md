# Extrator de quadras — aplicação base (TCC)

Exemplo mínimo de **web scraping de site dinâmico** (feito no Bubble.io).
Parte dos dados não vem no HTML pronto, então a aplicação combina duas
técnicas: uma chamada direta à **API JSON** do site (leve, sem navegador) e
um **navegador real controlado por Playwright** para o que só aparece depois
da interação.

A coleta percorre uma **lista de arenas**, e não um site só. Todas compartilham o mesmo
front, então o mesmo coletor serve para todas; o que muda é a URL, e com ela as quadras,
o endereço e — o ponto que faz diferença no dado — **a cidade em que o tempo é medido**.

São **29 arenas** no `ARENAS`, e 21 delas entregam quadra:

| Arena | Cidade | Quadras |
| --- | --- | --- |
| SP Sports | Canoas, RS | 7 — Vôlei de praia, Futebol de salão, Grama 7, Grama 5 |
| AABB Camaquã | Camaquã, RS | 1 × Handebol (o ginásio) |
| Arena Darc Sports | Ananindeua, PA | 3 × Futebol society |
| Arena Grenal | Alvorada, RS | 1 × Futebol society |
| Arena Sabino Futebol Society | Belém, PA | 1 × Futebol society |
| Arena Santi | Parobé, RS | 4 × Beach Tennis |
| Arena Trescopark | Três Coroas, RS | 2 × Vôlei de praia |
| Arena Yes Play | Taquara, RS | 4 × Vôlei de praia |
| Beach Brasil | Porto Alegre, RS | 2 × Futevôlei |
| Beach Place Poa | Porto Alegre, RS | 4 × Beach Tennis |
| Casarão NH Sports | Novo Hamburgo, RS | 1 × Futebol society |
| Complexo Rams | Paço do Lumiar, MA | 2 × Futebol society |
| CT Belotto | Taquara, RS | 3 × Beach Tennis |
| Esporte e Lazer Fênix | Canoas, RS | 1 × Futebol society |
| Gol de Placa | Franca, SP | 1 × Futebol society |
| Home Sports Bar | Canoas, RS | 1 × Futebol society |
| Mundial Society Club | Patrocínio, MG | 1 × Futebol society |
| Playpadel | São Lourenço do Sul, RS | 2 × Padel |
| Racket Garden | Araricá, RS | 4 × Beach Tennis |
| Ravena Beach | Erechim, RS | 5 × Futevôlei |
| Vila Society | Blumenau, SC | 2 × Beach Tennis |

São dezesseis cidades e seis estados: entre Canoas e Belém há mais de três mil quilômetros
e dois regimes de chuva diferentes — em agosto, 8 °C na Grande Porto Alegre contra 27 °C
no Pará, no mesmo instante. É essa dispersão que faz o clima valer como variável: uma
tabela de tempo só, de um ponto só, descreveria o lugar errado em vinte das vinte e uma
pastas.

> **Oito arenas estão na lista e não entregam quadra** — são as que aparecem com
> `quadras_verificadas = 0` no log de verificações —, cada uma por um motivo que a rodada
> nomeia na saída quando chamada à mão. **Arena Grings** e **CT Kliks** não vendem pela web: o site responde "Local
> indisponível para marcações pela web" no lugar do campo de data, e a rodada encerra
> aquela arena em cinco segundos, com o aviso e sem linha no CSV. **Na 5 Beach Sport**
> pede login — a página anuncia "Faça seu login" e a agenda não abre para quem não entrou.
> **Arena Total 90**, **Ginásio Bigornão Futsal**, **MB Arena**, **My Beach Sport** e
> **Table Tennis Place** usam o outro fluxo de reserva: escolhida a data, elas pedem
> "Escolha uma quadra" antes de mostrar horário nenhum, e o coletor espera a lista inteira
> de uma vez. O JSON da arena entrega quais são antes de abrir o navegador — é o campo
> `tipo_selecao_horario`, que vale `lista_turno_duracao` exatamente nessas cinco e
> `lista_turno` em todas as vinte e uma que coletam. Elas ficam na lista porque o dia em
> que o segundo fluxo for implementado é uma linha a menos para reescrever; o preço é o
> tempo que gastam por rodada sem trazer nada.

## O que ele faz

Para **cada arena** de `ARENAS`:

**Técnica 1 — API JSON (sem navegador).**
Chama `/api/1.1/init/data` no domínio da própria arena com `requests` e lista os
esportes disponíveis direto do JSON, sem abrir o Chromium.

**Técnica 2 — navegador headless (Playwright).**
1. Abre a URL da arena
2. Percorre os **tipos de quadra que aquela arena declara no config**, ignorando os demais
   esportes do site
3. Lê o **endereço** que a arena publica logo abaixo do esporte escolhido, de onde saem
   as coordenadas do clima
4. Para cada um, percorre o **dia atual e os próximos** (`DIAS_A_FRENTE`), achando cada
   data no calendário pelo `aria-label` da célula (`21/08/26 - sexta-feira`)
5. Percorre os períodos **Manhã**, **Tarde** e **Noite**
6. Em cada período, percorre **cada quadra** do esporte separadamente
7. Imprime os horários de cada quadra (🟢 Livre / 🔴 Indisponível) e quantas vagas ficaram livres

O **preço só é aberto no dia de hoje**. Ler o valor custa um clique por horário livre, e
os dias à frente são quase todos livres; cada um deles ainda será visitado no seu próprio
dia, que é quando o preço entra na linha.

Um esporte que falhe por lentidão do site é reportado e pulado, sem derrubar a coleta
dos demais; **uma arena que falhe inteira também** — a lista de sites não fica refém do
pior deles. Uma execução que não colete nada em arena nenhuma sai com código de erro, em
vez de gravar silêncio — o modo de falha mais caro num coletor agendado.

### Cinco formas de a mesma página aparecer

O front é um só, mas cada arena o preenche com o que tem, e o passo 2 acima esbarra nas
cinco formas:

- **Vários esportes.** A lista aparece e a coleta clica no esporte pedido. É o caso da SP
  Sports.
- **Um esporte só.** A página já abre com ele escolhido, e o item da lista fica na página
  **escondido**. Clicar ali é esperar por um elemento que nunca fica visível, e era assim
  que Sabino, Grenal e Darc saíam da rodada por tempo esgotado, sem coletar nada. Quando o
  campo de data já está na tela, não há o que clicar.
- **Sem agenda na web.** No lugar do campo de data vem *"Local indisponível para marcações
  pela web"* — a arena existe, publica o endereço, e não vende por ali. Reconhecer o aviso
  encerra o esporte na hora, com `aviso` na saída e nenhuma linha no CSV; sem isso a coleta
  insistiria no calendário em cada dia do horizonte, a cada esporte, a cada quinze minutos.
  Grings e CT Kliks estão nesse estado.
- **Atrás de login.** A página lista os esportes, mas escolher um não abre agenda nenhuma:
  o que vem é *"Faça seu login"*. Não há aviso a reconhecer, então a arena gasta o tempo de
  espera e volta vazia. É a Na 5 Beach Sport.
- **Escolha por quadra.** Escolhida a data, a arena pede *"Escolha uma quadra"* e só depois
  mostra horário — é o outro fluxo de reserva do mesmo Bubble, e o coletor lê a lista de
  quadras toda de uma vez. **Não é preciso abrir o navegador para saber quem faz assim**:
  o `tipo_selecao_horario` do `/api/1.1/init/data` vale `lista_turno_duracao` nessas e
  `lista_turno` nas que o coletor já lê.

**A troca de período é confirmada pelo realce do botão**, e não por o conteúdo mudar. A
página abre com um período já escolhido — Noite, em todas as arenas vistas até aqui —, e
clicar naquele não muda texto nenhum: uma arena que só venda à noite ficaria de fora
inteira, com os horários na tela o tempo todo. Trocado o realce, o conteúdo ainda precisa
acompanhar antes da leitura, senão o que se grava no período novo são os horários do
anterior.

## Os módulos

| Arquivo | Papel |
| --- | --- |
| `main.py` | **Ponto de entrada.** Roda as arenas em paralelo, chama os coletores de cada uma e manda gravar |
| `config.py` | O que se edita: lista de arenas, tipos de quadra, diretório de saída |
| `courts_collector.py` | Coleta das reservas e do endereço — API JSON e navegador. É biblioteca, não roda sozinho |
| `localizacao.py` | Traduz o endereço da arena em coordenadas, e lembra o resultado |
| `weather_collector.py` | Coleta as condições atuais e a previsão hora a hora, pela API Open-Meteo |
| `tratamento.py` | Casa clima e previsão com as reservas: a janela do jogo e o instante da reserva |
| `persistencia.py` | Gravação do CSV por quadra e do log de verificações, com upsert. Não depende do Playwright |

A separação não é enfeite: `persistencia.py` é importado por quem não abre navegador
nenhum, e o coletor carrega o Playwright já no `import`. Juntos, um consultaria o
Chromium para ler o nome de uma coluna.

## Configuração

Tudo que muda de instalação para instalação vive em `config.py`. O que mais importa é a
lista de arenas:

```python
ARENAS = [
    {"nome": "SP Sports", "url": "https://webarena.app/arena/sp-sports"},
    {
        "nome": "Arena Grenal",
        "url": "https://webarena.app/arena/arena-grenal",
        "tipos": ["Futebol society"],
    },
]
```

Acrescentar um site é acrescentar uma linha. Só a `url` é obrigatória — dela saem a
página que o navegador abre, o endereço da API JSON (mesmo caminho, domínio da própria
arena, então um site fora do `webarena.app` também serve) e o **diretório onde a arena
grava**, tirado do último trecho da URL. O `nome` é o que vai à coluna `arena` do CSV; na
falta dele, vale o identificador da URL. É a URL que identifica a arena, e não o nome:
renomear no config não desgarra o histórico já coletado.

`tipos` é o **catálogo daquela arena**: os tipos de quadra que a coleta procura na lista
de esportes do site. Sem ele vale `TIPOS_QUADRA`, o padrão de quatro tipos que a primeira
arena usa. Cada site vende o que quer — só futebol society, só o ginásio, areia em três
esportes diferentes —, e uma lista fixa para todas deixaria as demais voltando vazias sem
erro nenhum.

A grafia que se escreve aqui é a que vai para a coluna `tipo_quadra` do CSV, e a
comparação com o site ignora acento, caixa e a diferença entre futsal e futebol de salão.
É por isso que `"Futebol society"` casa com o `Futebol Society` da Arena Darc e com o
`Futebol society` da Grenal: no dataset as duas viram um tipo só, em vez de dois nomes
para a mesma quadra.

> Quando um site oferece **vários esportes na mesma quadra física** — a areia da SP Sports
> aparece em Vôlei de praia e em Beach Tennis, e o mesmo ginásio costuma aparecer em
> futsal, vôlei, basquete e handebol —, o catálogo escolhe **um**. Coletar mais de um
> gravaria o mesmo horário uma vez por esporte, e uma reserva viraria várias linhas no
> dataset. A Vila Society é a demonstração: Beach Tennis e Futevôlei devolvem as mesmas
> `Areia 1`, `Areia 2` e `Areia 3`.

**Qual dos esportes escolher não é livre.** Na maioria das arenas o dono pendurou as
quadras em **um** dos esportes que anuncia, e os outros existem só na vitrine: escolher o
errado devolve zero quadra, sem erro, gastando o horizonte inteiro de dias tentando. Foi
assim que a lista saiu — abrindo cada arena e vendo qual esporte tem agenda. Não há padrão
a decorar: a AABB Camaquã anuncia futsal, vôlei, basquete e handebol, e o ginásio está no
**handebol**; a Beach Brasil e a Ravena Beach penduraram a areia no **futevôlei**; a Beach
Place Poa, no **beach tennis**; a Trescopark, no **vôlei de praia**. Arena nova entra pelo
mesmo caminho, e o `pytest -m rede -k toda_arena_ainda_oferece` avisa quando um site
renomeia o esporte por baixo.

Uma quarta chave, opcional, é a saída de emergência:

```python
    {"nome": "Arena X", "url": "...", "coordenadas": (-29.65, -50.81)},
```

Coordenadas fixadas à mão vencem a geocodificação, para o caso do endereço que o mapa não
reconhece. Sem elas — o caso normal —, o endereço publicado pela arena basta.

`DIAS_A_FRENTE` é o quanto a coleta enxerga além de hoje. É o parâmetro que decide quanta
antecedência de reserva o histórico consegue registrar, e o que mais pesa no tempo de
execução: cada dia a mais custa por volta de **8 segundos por esporte coletado** — hoje são
trinta e um. O site libera 60 dias, então o teto é prático, não do site. A previsão
acompanha o mesmo horizonte automaticamente.

> Ele vale **5** desde que a lista deixou de ter uma arena só. Com 14, a rodada completa
> não cabia no intervalo de 15 minutos do `cron`; com 5, sobra folga. O preço está
> anotado: **reserva feita com mais de cinco dias de antecedência chega já indisponível**,
> e o histórico a registra com `primeira_coleta` preenchida e `reservado_em` vazia — "já
> chegou ocupada", e não "ninguém reservou". Subir o número de volta é refazer a conta do
> limite de execução junto.

`ARENAS_EM_PARALELO` é quantas arenas rodam ao mesmo tempo. Elas são independentes por
construção — navegador, diretório, endereço e clima próprios —, então o paralelismo não
precisou de trava nenhuma na gravação: cada uma escreve só na pasta dela. A exceção é a
**geocodificação**, que roda com trava e uma arena de cada vez, porque o Nominatim é um
serviço público que pede no máximo uma consulta por segundo e a primeira rodada de uma
lista nova resolveria as 29 de uma vez. O log de verificações é a outra: ele é um arquivo
só, lido e reescrito inteiro a cada linha, então quem grava nele é o laço que recolhe as
arenas prontas — ali elas voltam a ser uma de cada vez. A saída continua legível porque
cada arena guarda o que imprimiria e só solta o bloco inteiro quando termina; sem isso,
quatro arenas escrevendo ao mesmo tempo entrelaçariam as linhas.

> Vale **4**. O teto não é o processador — a coleta passa o tempo esperando o site —, é a
> **memória**: cada arena no ar segura um Chromium, uns 400 MB, e estourar a RAM derruba a
> rodada inteira. Com 29 arenas em sequência a rodada passaria de **50 minutos**; com
> quatro ao mesmo tempo, fica em **12**.

## O endereço, e as coordenadas que saem dele

Escolhido o esporte, a arena publica o endereço dela logo abaixo — `Boqueirão 2710,
Canoas`, `20 de Junho 54, Parobé`. É a única coisa na página que diz **onde a quadra
fica**, e é dela que sai o clima: sem isso, arenas de cidades diferentes receberiam todas
o tempo de um ponto fixo no `config`, e a variável central do trabalho passaria a
descrever o lugar errado.

A leitura é **pela posição na tela**, não pela ordem do HTML: o Bubble publica os blocos
fora de ordem e os coloca no lugar com `order` do CSS. O endereço é o primeiro texto
abaixo do nome do esporte e acima do campo de data que tenha uma **vírgula** — é ela que
o separa do rótulo `Escolha uma data.`, que é o mesmo tipo de bloco. Não achando nada,
a leitura devolve vazio, e a arena segue com o local que já conhecia.

O endereço vira coordenada no [Nominatim](https://nominatim.openstreetmap.org), o
geocodificador do OpenStreetMap — público, gratuito e sem chave. A pergunta desce do
específico para o genérico até uma forma responder:

```
"20 de Junho 54, Parobé"   ->  como veio
"20 de Junho, Parobé"      ->  sem o número do prédio
"Parobé"                   ->  só a cidade
```

Descer um degrau é melhor do que devolver nada: para o clima a cidade já basta — a grade
da Open-Meteo tem quilômetros de lado —, e o número do prédio é justamente o que costuma
faltar no mapa. Nenhuma delas respondendo, a arena passa a rodada sem clima; carimbar nela
o tempo de outro lugar seria pior do que a lacuna.

O resultado fica em `local.json`, no diretório da arena:

```json
{
  "endereco": "Boqueirão 2710, Canoas",
  "latitude": -29.904984,
  "longitude": -51.1612617,
  "cidade": "Canoas",
  "origem": "Boqueirão 2710, Canoas",
  "resolvido_em": "2026-08-21T07:18:08"
}
```

O arquivo é memória e registro ao mesmo tempo. **Memória** porque o geocodificador só é
consultado quando o endereço lido agora é diferente do que está ali: o endereço de uma
quadra não muda, e bater no serviço quatro vezes por hora para reconfirmar o que ninguém
mudou seria abusar de um serviço público limitado a uma consulta por segundo. **Registro**
porque é ele que diz de onde o clima daquela pasta foi medido.

Duas recusas deliberadas, do mesmo feitio das outras do projeto. Rodada em que o endereço
não foi lido fica com o local já gravado — a arena não mudou de lugar só porque a página
não pintou a tempo. E endereço **novo** que o mapa não reconhece devolve lacuna em vez de
herdar as coordenadas do endereço antigo, que descrevem outro ponto: se a arena se mudou,
o clima do lugar velho não é o dela.

> O `User-Agent` que identifica a aplicação (`IDENTIFICACAO_GEOCODIFICACAO`) é exigência
> do Nominatim, que recusa chamada anônima. A [política de
> uso](https://operations.osmfoundation.org/policies/nominatim/) pede também um contato
> de quem opera o coletor — é o lugar de acrescentá-lo, se a coleta crescer.

## Saída: um diretório por arena, um CSV por quadra

```
.extracoes/
├── sp-sports/
│   ├── local.json
│   ├── clima-leituras.csv
│   ├── clima-previsoes.csv
│   ├── areia-1-interna-extracoes.csv
│   └── futsal-interna-extracoes.csv
├── arena-grenal/
│   ├── local.json
│   ├── clima-leituras.csv
│   ├── clima-previsoes.csv
│   └── society-extracoes.csv
└── arena-darc-sports/
    ├── local.json
    └── ...
```

Cada quadra encontrada ganha o seu próprio arquivo, `<slug-da-quadra>-extracoes.csv`,
criado na primeira vez que ela aparece — `futsal-interna-extracoes.csv`,
`areia-4-externa-extracoes.csv` e assim por diante. É o que garante a unicidade do
horário: um esporte pode ter várias quadras (o vôlei de praia tem quatro), e o `17:00`
de uma nunca deve disputar linha com o `17:00` de outra.

O diretório por arena é a mesma ideia um nível acima. Duas arenas podem ter uma `Quadra 1`
cada, e o slug das duas é o mesmo: sem a pasta, uma sobrescreveria o histórico da outra —
e as duas tabelas de clima, que são de uma cidade só, viveriam o mesmo conflito.

Duas colunas abrem o CSV e dizem de onde a linha veio: `arena`, o nome do config, e
`cidade`, a que o geocodificador resolveu. Elas são o que permite juntar os arquivos de
várias arenas num dataset só sem perder o lugar de cada reserva — e são o que falta hoje
para preencher `feriado`, `evento_grande` e `jogo_em_porto_alegre`, que dependem da cidade.

> `cidade` vazia quer dizer "ainda não sei", e não "não tem": a rodada em que o
> geocodificador falhar não apaga a cidade que a anterior descobriu, e a que a descobrir
> preenche as linhas que já estavam gravadas — enquanto o horário não tiver chegado.

Outras duas colunas dizem que quadra é aquela: `tipo_quadra`, o esporte escolhido
normalizado para a grafia do `tipos` da arena — `Vôlei de praia`, `Futebol de salão`,
`Grama 7`, `Grama 5`, `Futebol society` —; e `quadra_coberta`, que sai do **nome** da
quadra: `true` para interna, coberta ou ginásio, `false` para externa ou descoberta.

> `quadra_coberta` fica **vazia** quando o nome não diz — `SFS`, `Society`, `Arena 1`. É
> lacuna assumida, e não `false`: as arenas de futebol society não anunciam a cobertura no
> nome da quadra, e chutar "descoberta" para todas afirmaria no dataset uma coisa que
> ninguém observou. O `tipo_quadra` daquela linha é o que sobra para responder a pergunta.

### Migrando o histórico que já existe

O dataset coletado antes da lista de arenas está solto na raiz de `.extracoes-ate-27-09-2026`, onde a
coleta não procura mais. **Antes da primeira rodada nova** — que numa máquina com o `cron`
ligado é a dos próximos quinze minutos —, os arquivos precisam descer para a pasta da
arena:

```bash
mkdir -p .extracoes/sp-sports && mv .extracoes/*.csv .extracoes/sp-sports/
```

Feito depois, não se perde nada de irreversível, mas o histórico se parte em dois: os
horários já observados nascem de novo na pasta nova, com `primeira_coleta` recomeçando, e
a virada de status de quem já estava sob observação passa despercebida.

As linhas antigas ficam com `arena` e `cidade` vazias — elas são anteriores às colunas. Os
horários que ainda não chegaram se preenchem sozinhos na próxima rodada; para os que já
passaram, que estão congelados, vale um preenchimento de uma vez:

```python
import glob, pandas as pd

for caminho in glob.glob(".extracoes-ate-27-09-2026/sp-sports/*-extracoes.csv"):
        df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
        df.loc[df["arena"] == "", ["arena", "cidade"]] = ["SP Sports", "Canoas"]
        df.to_csv(caminho, index=False)
```

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
(`reserva_*` e `previsao_para_o_jogo_no_momento_da_reserva_*`). Manter o carimbo antigo seria afirmar uma reserva que não
existe mais; se o horário for reservado de novo, a próxima virada grava a data nova.
`primeira_coleta` fica de fora: a observação daquele horário não recomeçou.

> A virada é detectada **na gravação**, comparando o status que está no CSV com o que a
> coleta acabou de trazer. Só vale enquanto o horário está no futuro: depois que o jogo
> começa a linha congela, como já congelava para status e preço.

## Clima: uma tabela à parte

Cada execução também registra as condições do momento **em cada arena**, pela API pública
da [Open-Meteo](https://open-meteo.com), em `clima-leituras.csv` — um arquivo por arena,
série temporal, uma linha por leitura. As coordenadas são as que saíram do endereço
daquela arena, e vão gravadas na própria linha.

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
| `previsao_para_o_jogo_no_momento_da_reserva_*` | O que se previa para a hora do jogo | Uma vez, na virada de status |

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

É a variável que faltava para a pergunta do trabalho. `previsao_para_o_jogo_no_momento_da_reserva_*` diz o que a pessoa
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

As cinco colunas `previsao_para_o_jogo_no_momento_da_reserva_*` espelham exatamente as observadas, e por isso dá para
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

Com `--ver` abrem `ARENAS_EM_PARALELO` janelas ao mesmo tempo, uma por arena em coleta.
Para acompanhar uma só, baixe o valor para 1.

### Logs de depuração

Os prints de `debug()` só aparecem com a variável `EXTRATOR_DEBUG` ligada
(qualquer valor diferente de vazio ou `0`):

```bash
EXTRATOR_DEBUG=1 python main.py          # headless, com logs de debug
EXTRATOR_DEBUG=1 python main.py --ver    # navegador visível, com logs de debug
```

Os logs saem no **stderr**; para gravar tudo num arquivo, use
`EXTRATOR_DEBUG=1 python main.py > saida.log 2>&1`. O cron não define a variável,
então a coleta agendada segue sem debug. Uma execução manual grava em `.extracoes-ate-27-09-2026`
como qualquer rodada do cron.

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
quadras, elas ainda têm nome, a nomenclatura de cobertura continua reconhecível, a arena
ainda publica o endereço com a vírgula que o distingue do rótulo vizinho, e o
calendário ainda libera os dias à frente com o `aria-label` no formato esperado. É o
que avisa quando o site é republicado e o scraper para de achar as coisas — inclusive nos
modos de falha mais discretos, em que a coleta continua funcionando mas só enxerga hoje e
a hora da reserva some do histórico, ou em que o endereço deixa de ser lido e o clima
passa a vir do último ponto conhecido, sem nenhum erro aparecer.

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
diretório criaria um `.extracoes-ate-27-09-2026` paralelo no `$HOME` e partiria o dataset em dois, sem
avisar. A segunda é o `flock`: a gravação lê o CSV inteiro e reescreve, de modo que duas
rodadas sobrepostas se sobrescrevem por completo — a que terminar por último apaga os
slots que a outra acabou de inserir. Rodada que encontra a trava tomada **sai com 0** e
anota "pulado" no `journald`; ela não entra na fila, porque a rodada em andamento já está
colhendo dado mais fresco do que a duplicata colheria.

Um `timeout` fecha o terceiro buraco: sem ele, um Chromium travado seguraria a trava para
sempre e mataria todas as coletas seguintes. Quando ele dispara, o código é 124,
distinguível do 1.

**O limite é a conta que precisa ser refeita a cada arena acrescentada.** O que custa não é
a arena, é o **esporte**: cada um abre o seu próprio navegador e percorre o horizonte
inteiro de dias, um dia de cada vez. Medido no `execucoes.csv`, um dia de um esporte custa
por volta de **8 segundos**. O que divide a conta é `ARENAS_EM_PARALELO`: as arenas rodam
ao mesmo tempo, cada uma com navegador, diretório e clima próprios:

```
LIMITE  ≈  8s × n_esportes × (DIAS_A_FRENTE + 1) / ARENAS_EM_PARALELO
```

Com as 29 arenas da lista, `DIAS_A_FRENTE = 5` e quatro arenas ao mesmo tempo, a rodada dá
por volta de **11 minutos** — contra quase uma hora se fossem uma de cada vez, que é o que
tirou a lista inteira de dentro do intervalo do `cron` e obrigou o paralelismo.

O paralelismo tem dois tetos. O de **memória**: cada arena no ar segura um Chromium, uns
400 MB, e estourar a RAM da máquina derruba a rodada inteira, não só a arena. O de
**educação com o site**: as 29 são o mesmo domínio, e subir demais o número transforma a
coleta em rajada. Quatro é o que coube na máquina de hoje com o desktop em uso; a
geocodificação fica de fora dessa conta de propósito — o Nominatim pede no máximo uma
consulta por segundo, então ela acontece com trava, uma arena de cada vez.

`LIMITE_DE_EXECUCAO`, no topo de `scripts/rodar_extracao.sh`, é onde a conta entra — `14m`,
com folga para as rodadas ruins e ainda abaixo do intervalo do `cron`. Duas coisas a olhar
junto: um limite **curto** demais corta a rodada no meio, e as arenas do fim da fila nunca
chegam a ser coletadas; um limite **maior que o intervalo do cron** faz a rodada seguinte
encontrar a trava tomada e sair pulando — o `flock` protege o dataset, mas a cadência real
deixa de ser a que está no crontab. Passando disso, o intervalo é que precisa crescer.

> **É a conta que decidiu `DIAS_A_FRENTE = 5`.** Mantido o horizonte de 14, a rodada
> passaria dos 15 minutos do `cron`: uma em cada duas execuções encontraria a trava
> tomada, e a cadência real — não a do crontab — viraria a resolução de `reservado_em`.
> Encurtar o horizonte foi o caminho escolhido para manter os 15 minutos; o outro seria
> subir o intervalo para 30 e assumir a resolução no texto.

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
`cron` falando sozinho. A rodada agendada **não guarda relatório de texto** — o que ela
imprime vai para o `stdout`, que o `cron` descarta; o rastro fica em três lugares:

```bash
column -s, -t .logs/verificacoes.csv                # arena por arena: quando e quais quadras
tail .logs/execucoes.csv                            # instante, código e duração por rodada
awk -F, 'NR > 1 && $2 != 0' .logs/execucoes.csv     # só as que falharam
journalctl -t extrator-quadras --since today        # falhas e rodadas puladas
```

O `verificacoes.csv` é o log da coleta: **uma linha por arena**, com o instante em que ela
foi verificada pela última vez, quantas quadras foram lidas ali e quais. É um retrato do
agora, não um histórico — a rodada seguinte reescreve a linha da arena no lugar, e por
isso o arquivo fica em 29 linhas em vez de crescer 29 por rodada, quase três mil por dia.
O histórico de quem já esteve lá é o próprio `.extracoes-ate-27-09-2026`. Duas leituras: um
`ultima_verificacao` velho enquanto as vizinhas estão frescas é arena que caiu ou que a
rodada não alcançou dentro do tempo; `quadras_verificadas = 0` é arena que respondeu sem
entregar quadra — o site pede login, não vende pela web, ou o catálogo do `config` deixou
de casar com os esportes que ela publica.

O `execucoes.csv` diz se a rodada como um todo terminou — uma linha por rodada que chegou
a rodar. A rodada pulada não deixa linha ali, de propósito: ela sai antes, e o ledger é o
registro do que foi coletado, não do que o `cron` tentou. Quem registra as puladas é o
`journald`, com `journalctl -t extrator-quadras -p warning`; subindo, é sinal de que a
cadência ficou apertada para a duração real. `.logs/` fica fora do Git, como `.extracoes-ate-27-09-2026`.

Para ver o relatório completo de uma rodada — os horários um a um, os avisos de cada
arena —, a saída existe: basta chamar à mão, que aí ela vai para o terminal.

```bash
.venv/bin/python main.py
```

> O `cron` não recupera execução perdida, e `anacron` não cobre intervalo menor que um
> dia. Máquina suspensa, desligada ou sem rede vira buraco na série temporal — num
> desktop isso é aceitável se for documentado; o que fecha de vez é subir para uma VPS.

## Próximos passos (para evoluir no TCC)
- **Alertar**: notificar quando um horário mudar de "Indisponível" para "Livre" — a
  virada já é detectada na gravação, falta o aviso
- Parametrizar arena/esporte/período/data via argumentos de linha de comando
  (a função `collect_schedules` já aceita `sport`, `arena_url`, `period` e
  `days_ahead` e `types`; o `main.py` percorre todas as arenas e o catálogo de cada
  uma, mas não aceita recorte pela linha de comando)
- Preencher `feriado`, `evento_grande` e `jogo_em_porto_alegre`, as três colunas de
  contexto que existem no CSV e ainda nascem vazias — agora que a coluna `cidade` diz a
  que lugar cada linha se refere, as três passam a ser respondíveis para arenas de
  cidades diferentes, e `jogo_em_porto_alegre` provavelmente vira uma pergunta por cidade

## Conceito-chave
Sempre desça a "escada" do mais leve pro mais pesado:
`requests` (HTML estático) → **API JSON** (aba Network) → **navegador headless**.
Esta aplicação usa os dois últimos degraus de propósito: a lista de esportes
sai da API JSON (barato), e os horários — que só existem depois de clicar no
esporte, no dia e no período — exigem o navegador.