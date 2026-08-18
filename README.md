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
3. Para cada um, seleciona o **dia atual** no calendário (`.picker__day--today`)
4. Percorre os períodos **Manhã**, **Tarde** e **Noite**
5. Em cada período, percorre **cada quadra** do esporte separadamente
6. Imprime os horários de cada quadra (🟢 Livre / 🔴 Indisponível) e quantas vagas ficaram livres

Um esporte que falhe por lentidão do site é reportado e pulado, sem derrubar a coleta
dos demais; uma execução que não colete nada sai com código de erro, em vez de gravar
silêncio — o modo de falha mais caro num coletor agendado.

## Os módulos

| Arquivo | Papel |
| --- | --- |
| `main.py` | **Ponto de entrada.** Chama os coletores em sequência, imprime o relatório e manda gravar |
| `config.py` | O que se edita: URL da arena, coordenadas, tipos de quadra, diretório de saída |
| `courts_collector.py` | Coleta das reservas — API JSON e navegador. É biblioteca, não roda sozinho |
| `weather_collector.py` | Coleta as condições atuais na arena pela API Open-Meteo |
| `tratamento.py` | Casa a leitura de clima com as reservas que estão na janela |
| `persistencia.py` | Gravação do CSV por quadra, com upsert. Não depende do Playwright |

A separação não é enfeite: `persistencia.py` é importado por quem não abre navegador
nenhum, e o coletor carrega o Playwright já no `import`. Juntos, um consultaria o
Chromium para ler o nome de uma coluna.

## Configuração

Tudo que muda de instalação para instalação vive em `config.py` — a URL da arena, as
coordenadas usadas na consulta de clima e o diretório onde as extrações são gravadas.
Trocar de arena é editar uma linha, sem abrir o coletor.

## Saída: um CSV por quadra

Cada quadra encontrada ganha o seu próprio arquivo, `<slug-da-quadra>-extracoes.csv`,
criado na primeira vez que ela aparece — `futsal-interna-extracoes.csv`,
`areia-4-externa-extracoes.csv` e assim por diante. É o que garante a unicidade do
horário: um esporte pode ter várias quadras (o vôlei de praia tem quatro), e o `17:00`
de uma nunca deve disputar linha com o `17:00` de outra.

Duas colunas saem do nome da quadra: `tipo_quadra`, normalizada para `Vôlei de praia`,
`Futebol de salão`, `Grama 7` ou `Grama 5`; e `quadra_coberta`, `true` para
interna/coberta e `false` para externa/descoberta.

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

Uma queda da Open-Meteo **não derruba a execução**: o aviso vai para o `stderr` e as
quadras, que são o dado caro de coletar, seguem gravadas.

## A janela de clima de cada reserva

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
quadras, elas ainda têm nome, e a nomenclatura de cobertura continua reconhecível. É o
que avisa quando o site é republicado e o scraper para de achar as coisas.

```bash
pytest -m rede                        # roda o canário, sob demanda
python scripts/capturar_fixtures.py   # regrava as fixtures com o HTML de hoje
```

## Próximos passos (para evoluir no TCC)
- **Agendar** de 15/30 min: `cron` em uma VPS Linux (`*/15 * * * *`)
- **Alertar**: notificar quando um horário mudar de "Indisponível" para "Livre"
- Parametrizar esporte/período/data via argumentos de linha de comando
  (a função `coletar_horarios` já aceita `esporte` e `periodo`; o `main.py` percorre os
  quatro tipos de quadra, mas não aceita recorte pela linha de comando)

## Conceito-chave
Sempre desça a "escada" do mais leve pro mais pesado:
`requests` (HTML estático) → **API JSON** (aba Network) → **navegador headless**.
Esta aplicação usa os dois últimos degraus de propósito: a lista de esportes
sai da API JSON (barato), e os horários — que só existem depois de clicar no
esporte, no dia e no período — exigem o navegador.