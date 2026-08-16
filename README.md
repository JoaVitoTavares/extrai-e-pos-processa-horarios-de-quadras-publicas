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

## Saída: um CSV por quadra

Cada quadra encontrada ganha o seu próprio arquivo, `<slug-da-quadra>-extracoes.csv`,
criado na primeira vez que ela aparece — `futsal-interna-extracoes.csv`,
`areia-4-externa-extracoes.csv` e assim por diante. É o que garante a unicidade do
horário: um esporte pode ter várias quadras (o vôlei de praia tem quatro), e o `17:00`
de uma nunca deve disputar linha com o `17:00` de outra.

Duas colunas saem do nome da quadra: `tipo_quadra`, normalizada para `Vôlei de praia`,
`Futebol de salão`, `Grama 7` ou `Grama 5`; e `quadra_coberta`, `true` para
interna/coberta e `false` para externa/descoberta.

## Instalação
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso
```bash
python courts_collector.py          # roda sem abrir janela (headless)
python courts_collector.py --ver    # abre o navegador pra você ASSISTIR o passo a passo
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
  (a função `coletar_horarios` já aceita `esporte` e `periodo`; o `main` percorre os
  quatro tipos de quadra, mas não aceita recorte pela linha de comando)

## Conceito-chave
Sempre desça a "escada" do mais leve pro mais pesado:
`requests` (HTML estático) → **API JSON** (aba Network) → **navegador headless**.
Esta aplicação usa os dois últimos degraus de propósito: a lista de esportes
sai da API JSON (barato), e os horários — que só existem depois de clicar no
esporte, no dia e no período — exigem o navegador.