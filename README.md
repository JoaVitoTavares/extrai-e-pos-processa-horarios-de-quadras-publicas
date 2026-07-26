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
2. Clica no esporte **Futebol de salão**
3. Seleciona o **dia atual** no calendário (`.picker__day--today`)
4. Percorre os períodos **Manhã**, **Tarde** e **Noite**
5. Imprime os horários de cada período (🟢 Livre / 🔴 Indisponível) e quantas vagas ficaram livres

## Instalação
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso
```bash
python coletor.py          # roda sem abrir janela (headless)
python coletor.py --ver    # abre o navegador pra você ASSISTIR o passo a passo
```

## Próximos passos (para evoluir no TCC)
- **Agendar** de 15/30 min: `cron` em uma VPS Linux (`*/15 * * * *`)
- **Guardar histórico**: salvar cada coleta em SQLite/CSV
- **Alertar**: notificar quando um horário mudar de "Indisponível" para "Livre"
- Parametrizar esporte/período/data via argumentos de linha de comando
  (a função `coletar_horarios` já aceita `esporte` e `periodo`; falta só expor isso no `main`)

## Conceito-chave
Sempre desça a "escada" do mais leve pro mais pesado:
`requests` (HTML estático) → **API JSON** (aba Network) → **navegador headless**.
Esta aplicação usa os dois últimos degraus de propósito: a lista de esportes
sai da API JSON (barato), e os horários — que só existem depois de clicar no
esporte, no dia e no período — exigem o navegador.