# Testes feitos com o modelo

## Teste 1 — Predição de ocupação com divisão temporal 90/10

**Data do teste:** 25/10/2026
**Objetivo:** verificar se o modelo consegue prever a ocupação (disponibilidade) das quadras em dias que ele não viu, usando os dias mais antigos para treinar e os mais recentes para validar.

### Dados utilizados

- Pasta: `.extracoes-ate-27-09-2026-pos-processamento`
- 20.032 horários, 77 quadras, 21 arenas, de 21/08/2026 a 01/10/2026
- Alvo: `ocupado` = 1 quando o status é Indisponível e 0 quando é Livre
- Colunas usadas pelo modelo (`FEATURES` de `model/train.py`):
  - horário: `hora`, `dia_semana`, `periodo`
  - clima: `clima`, `temperatura`, `umidade`, `precipitacao`, `velocidade_vento`
  - quadra: `tipo_quadra`, `quadra_coberta`
- Fora do modelo: `arena`, `cidade`, `quadra`, `valor_horario`, `reservado_em`, `periodo_da_reserva`, `antecedencia_horas`, todas as `reserva_*`, todas as `previsao_*`, `feriado`, `evento_grande` e `jogo_em_porto_alegre`

### Como o modelo foi treinado

1. **Ordenação e corte por data:** os horários foram ordenados por data e hora. O corte foi feito no dia em que se atingem 90% das linhas, para que um dia nunca fique dividido entre treino e validação.
2. **Normal da quadra só com o treino:** a taxa média de ocupação de cada quadra (`normal_treino`) foi calculada apenas com os dias de treino, para não levar a resposta da validação para dentro do modelo.
3. **Alvo do treino:** `ocupado − normal_treino`, ou seja, quanto cada horário ficou acima ou abaixo da ocupação normal da sua quadra. Assim o modelo aprende o efeito de horário e clima, e não o peso da quadra ou da arena.
4. **Algoritmo:** `HistGradientBoostingRegressor` (scikit-learn 1.9.1, `random_state=0`).
5. **Previsão:** probabilidade de ocupação = `normal_treino + previsão do modelo`, limitada entre 0 e 1. Com probabilidade ≥ 0,5, o horário é classificado como Ocupado.

### Separação dos dias

| Conjunto | Dias | Linhas | % |
|---|---|---|---|
| Treino | 21/08/2026 a 20/09/2026 | 17.936 | 89,5% |
| Validação | 21/09/2026 a 01/10/2026 | 2.096 | 10,5% |

O corte é por dia inteiro, por isso a validação ficou com 10,5% das linhas em vez de exatos 10%.

### Comando utilizado

O teste foi executado direto no terminal, a partir da raiz do projeto, reaproveitando as funções de `model/train.py`. Duas linhas sem efeito no resultado foram removidas abaixo.

```bash
.venv/bin/python -c "
import numpy as np, pandas as pd
import model.train as t
from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score, confusion_matrix
df=t.build_features(t.load_extraction('.extracoes-ate-27-09-2026-pos-processamento'))
df=df.sort_values(['data','horario_inicio']).reset_index(drop=True)
corte=df.data.iloc[int(len(df)*0.9)]
tr=df[df.data<corte].copy(); te=df[df.data>=corte].copy()
print('treino:',tr.data.min(),'->',tr.data.max(),len(tr),' teste:',te.data.min(),'->',te.data.max(),len(te), f'({len(te)/len(df):.1%})')
key=['arena_pasta','quadra_arquivo']
normal=tr.groupby(key)['ocupado'].mean().rename('normal_treino')
tr=tr.join(normal,on=key); te=te.join(normal,on=key)
te['normal_treino']=te['normal_treino'].fillna(tr.ocupado.mean())
tr['alvo']=tr.ocupado-tr.normal_treino
m=t.new_model().fit(tr[t.FEATURES],tr.alvo)
te['prob']=np.clip(te.normal_treino+m.predict(te[t.FEATURES]),0,1)
te['previsto']=(te.prob>=0.5).astype(int)
y=te.ocupado
print('ocupação real no teste:', round(y.mean(),3))
for nome,p in [('só normal',te.normal_treino),('modelo',te.prob)]:
    pr=(p>=0.5).astype(int)
    print(f'{nome:10s} auc={roc_auc_score(y,p):.3f} acerto={accuracy_score(y,pr):.3f} precisao={precision_score(y,pr,zero_division=0):.3f} recall={recall_score(y,pr):.3f}')
print('acerto se chutar sempre Livre:', round(1-y.mean(),3))
print('matriz (linhas=real Livre/Ocupado, colunas=previsto):'); print(confusion_matrix(y,te.previsto))
te['acertou']=te.previsto==y
print(te.groupby('periodo').agg(linhas=('acertou','size'),acerto=('acertou','mean'),ocup_real=('ocupado','mean'),ocup_prevista=('prob','mean')).round(3).to_string())
"
```

### Resultados gerais

Ocupação real nos dias de validação: 27,6%.

| Abordagem | Acerto | AUC | Precisão | Recall |
|---|---|---|---|---|
| Chutar sempre "Livre" | 72,4% | — | — | 0% |
| Só o normal da quadra | 75,6% | 0,807 | 59,1% | 37,0% |
| **Modelo** | **84,0%** | **0,910** | **70,8%** | **71,6%** |

- **Acerto:** porcentagem dos horários classificados corretamente.
- **AUC:** capacidade de separar horários ocupados de livres (0,5 = acaso, 1 = perfeito).
- **Precisão:** dos horários que o modelo previu como ocupados, quantos estavam de fato ocupados.
- **Recall:** dos horários que de fato estavam ocupados, quantos o modelo encontrou.

Matriz de confusão:

| | Previu Livre | Previu Ocupado |
|---|---|---|
| **Real Livre** | 1.347 | 171 |
| **Real Ocupado** | 164 | 414 |

### Resultados por período

| Período | Linhas | Acerto | Ocupação real | Ocupação prevista |
|---|---|---|---|---|
| Manhã | 606 | 86,3% | 24,9% | 24,3% |
| Tarde | 572 | 82,9% | 17,8% | 23,5% |
| Noite | 918 | 83,2% | 35,4% | 42,0% |

### Conclusões

- O modelo supera as duas referências: acerta 84,0% contra 75,6% usando só o normal da quadra e encontra quase o dobro dos horários ocupados (recall de 71,6% contra 37,0%).
- De manhã, a ocupação prevista ficou praticamente igual à real.
- À tarde e à noite, o modelo previu mais ocupação do que aconteceu: nos dias de validação a ocupação nesses períodos ficou abaixo da registrada no treino.
- A validação cobre só 11 dias. Os resultados precisam ser confirmados com extrações mais longas.

## Teste 2 — Predição de ocupação só com a Grande Porto Alegre, divisão temporal 90/10

**Data do teste:** 27/10/2026
**Objetivo:** repetir o Teste 1 só com as quadras da Grande Porto Alegre e verificar se um modelo regional prevê a ocupação melhor que o modelo com todas as arenas.

### Dados utilizados

- Pasta: `.extracoes-ate-27-09-2026-pos-processamento`
- 13.508 horários, 43 quadras e 11 arenas, de 21/08/2026 a 30/09/2026
- Alvo: `ocupado` = 1 quando o status é Indisponível e 0 quando é Livre
- Colunas usadas pelo modelo (`FEATURES` de `model/train.py`):
  - horário: `hora`, `dia_semana`, `periodo`
  - clima: `clima`, `temperatura`, `umidade`, `precipitacao`, `velocidade_vento`
  - quadra: `tipo_quadra`, `quadra_coberta`
- Fora do modelo: `arena`, `cidade`, `quadra`, `valor_horario`, `reservado_em`, `periodo_da_reserva`, `antecedencia_horas`, todas as `reserva_*`, todas as `previsao_*`, `feriado`, `evento_grande` e `jogo_em_porto_alegre`

Arenas mantidas (Região Metropolitana de Porto Alegre):

| Cidade | Arenas |
|---|---|
| Porto Alegre | `beach-brasil`, `beach-place-poa` |
| Canoas | `sp-sports`, `esporte-e-lazer-fenix`, `home-sports-bar` |
| Alvorada | `arena-grenal` |
| Novo Hamburgo | `casarao-nh-sports` |
| Taquara | `arena-yes-play`, `ct-belotto` |
| Parobé | `arena-santi` |
| Araricá | `racket-garden` |

Arenas excluídas (fora da Grande Porto Alegre):

| Cidade | Arena |
|---|---|
| Três Coroas (RS) | `arena-trescopark` |
| Camaquã (RS) | `aabb-camaqua` |
| São Lourenço do Sul (RS) | `playpadel` |
| Erechim (RS) | `ravena-beach` |
| Blumenau (SC) | `vila-society` |
| Franca (SP) | `gol-de-placa` |
| Patrocínio (MG) | `mundial-society-club` |
| Belém (PA) | `arena-sabino-futebol-society` |
| Ananindeua (PA) | `arena-darc-sports` |
| Paço do Lumiar (MA) | `complexo-rams` |

### Como o modelo foi treinado

1. **Exclusão das arenas:** as arenas de fora da Grande Porto Alegre são removidas já na leitura dos dados, pela opção `--excluir` do `model/train.py`.
2. **Ordenação e corte por data:** os horários foram ordenados por data e hora. O corte foi feito no dia em que se atingem 90% das linhas, para que um dia nunca fique dividido entre treino e validação.
3. **Normal da quadra só com o treino:** a taxa média de ocupação de cada quadra (`normal_treino`) foi calculada apenas com os dias de treino, para não levar a resposta da validação para dentro do modelo.
4. **Alvo do treino:** `ocupado − normal_treino`, ou seja, quanto cada horário ficou acima ou abaixo da ocupação normal da sua quadra. Assim o modelo aprende o efeito de horário e clima, e não o peso da quadra ou da arena.
5. **Algoritmo:** `HistGradientBoostingRegressor` (scikit-learn 1.9.1, `random_state=0`).
6. **Previsão:** probabilidade de ocupação = `normal_treino + previsão do modelo`, limitada entre 0 e 1. Com probabilidade ≥ 0,5, o horário é classificado como Ocupado.

Os passos 2 a 6 são os mesmos do Teste 1, agora executados pela opção `--teste` do `model/train.py` (função `evaluate_holdout`). Rodando o script com todas as arenas, os resultados do Teste 1 são reproduzidos exatamente.

### Separação dos dias

| Conjunto | Dias | Linhas | % |
|---|---|---|---|
| Treino | 21/08/2026 a 20/09/2026 | 12.003 | 88,9% |
| Validação | 21/09/2026 a 30/09/2026 | 1.505 | 11,1% |

O corte é por dia inteiro, por isso a validação ficou com 11,1% das linhas em vez de exatos 10%. Sem as arenas de fora da região, não há dados de 01/10/2026, então a validação vai até 30/09/2026.

### Comando utilizado

Executado a partir da raiz do projeto. O modelo treinado com todos os 13.508 horários foi salvo em `.modelo/grande-poa.joblib`.

```bash
.venv/bin/python -m model.train .extracoes-ate-27-09-2026-pos-processamento --saida .modelo/grande-poa.joblib --teste 0.1 \
  --excluir arena-trescopark aabb-camaqua playpadel ravena-beach vila-society gol-de-placa \
            mundial-society-club arena-sabino-futebol-society arena-darc-sports complexo-rams
```

### Resultados gerais

Ocupação real nos dias de validação: 30,2%.

| Abordagem | Acerto | AUC | Precisão | Recall |
|---|---|---|---|---|
| Chutar sempre "Livre" | 69,8% | — | — | 0% |
| Só o normal da quadra | 74,0% | 0,827 | 58,8% | 46,5% |
| **Modelo Grande POA** | **85,9%** | **0,930** | **77,7%** | **74,5%** |
| *Modelo com todas as arenas (Teste 1)* | *84,0%* | *0,910* | *70,8%* | *71,6%* |

- **Acerto:** porcentagem dos horários classificados corretamente.
- **AUC:** capacidade de separar horários ocupados de livres (0,5 = acaso, 1 = perfeito).
- **Precisão:** dos horários que o modelo previu como ocupados, quantos estavam de fato ocupados.
- **Recall:** dos horários que de fato estavam ocupados, quantos o modelo encontrou.

Matriz de confusão:

| | Previu Livre | Previu Ocupado |
|---|---|---|
| **Real Livre** | 954 | 97 |
| **Real Ocupado** | 116 | 338 |

### Resultados por período

| Período | Linhas | Acerto | Ocupação real | Ocupação prevista |
|---|---|---|---|---|
| Manhã | 504 | 86,1% | 25,6% | 25,1% |
| Tarde | 458 | 87,1% | 21,2% | 24,8% |
| Noite | 543 | 84,5% | 42,0% | 45,5% |

### Conclusões

- O modelo regional supera o modelo com todas as arenas em todas as métricas, principalmente na precisão (77,7% contra 70,8%).
- O acerto à tarde subiu de 82,9% para 87,1%, e a diferença entre a ocupação prevista e a real à noite caiu de 6,6 para 3,5 pontos.
- De manhã, a ocupação prevista segue praticamente igual à real.
- A validação tem só 10 dias e 1.505 horários. A melhora é consistente, mas precisa ser confirmada com extrações mais longas.

## Teste 3 — Inclusão do preço do horário, modelo total e Grande Porto Alegre, divisão temporal 90/10

**Data do teste:** 27/10/2026
**Objetivo:** repetir os Testes 1 e 2 com o preço do horário (`valor_horario`) entre as colunas do modelo e verificar se ele melhora a previsão de ocupação.

### Dados utilizados

- Pasta: `.extracoes-ate-27-09-2026-pos-processamento`
- Modelo total: 20.032 horários, 77 quadras, 21 arenas, de 21/08/2026 a 01/10/2026 (mesmos dados do Teste 1)
- Modelo Grande POA: 13.508 horários, 43 quadras, 11 arenas, de 21/08/2026 a 30/09/2026 (mesmas arenas do Teste 2)
- Alvo: `ocupado` = 1 quando o status é Indisponível e 0 quando é Livre
- Colunas usadas pelo modelo (`FEATURES` de `model/train.py`):
  - horário: `hora`, `dia_semana`, `periodo`
  - clima: `clima`, `temperatura`, `umidade`, `precipitacao`, `velocidade_vento`
  - quadra: `tipo_quadra`, `quadra_coberta`
  - preço: `valor_horario` (numérico; vazio quando o horário não tem preço)
- Fora do modelo: `arena`, `cidade`, `quadra`, `reservado_em`, `periodo_da_reserva`, `antecedencia_horas`, todas as `reserva_*`, todas as `previsao_*`, `feriado`, `evento_grande` e `jogo_em_porto_alegre`

O preço aparece em 99,6% dos horários livres e em 95,3% dos ocupados. Portanto, a presença do preço quase não revela se o horário está ocupado.

### Como o modelo foi treinado

Mesmo procedimento dos Testes 1 e 2 (corte por dia inteiro em 90/10, normal da quadra só com o treino, alvo `ocupado − normal_treino`, `HistGradientBoostingRegressor` com `random_state=0` e limiar de 0,5). A única mudança em `model/train.py` foi incluir `valor_horario` em `NUMERIC_FEATURES` e convertê-lo para número em `build_features`.

### Separação dos dias

| Modelo | Conjunto | Dias | Linhas | % |
|---|---|---|---|---|
| Total | Treino | 21/08/2026 a 20/09/2026 | 17.936 | 89,5% |
| Total | Validação | 21/09/2026 a 01/10/2026 | 2.096 | 10,5% |
| Grande POA | Treino | 21/08/2026 a 20/09/2026 | 12.003 | 88,9% |
| Grande POA | Validação | 21/09/2026 a 30/09/2026 | 1.505 | 11,1% |

### Comandos utilizados

Executados a partir da raiz do projeto. Os modelos treinados com todos os horários foram salvos em `.modelo/total-com-preco.joblib` e `.modelo/grande-poa-com-preco.joblib`.

```bash
.venv/bin/python -m model.train .extracoes-ate-27-09-2026-pos-processamento --saida .modelo/total-com-preco.joblib --teste 0.1

.venv/bin/python -m model.train .extracoes-ate-27-09-2026-pos-processamento --saida .modelo/grande-poa-com-preco.joblib --teste 0.1 \
  --excluir arena-trescopark aabb-camaqua playpadel ravena-beach vila-society gol-de-placa \
            mundial-society-club arena-sabino-futebol-society arena-darc-sports complexo-rams
```

### Resultados gerais

Ocupação real nos dias de validação: 27,6% no modelo total e 30,2% no Grande POA.

| Abordagem | Acerto | AUC | Precisão | Recall |
|---|---|---|---|---|
| *Total sem preço (Teste 1)* | *84,0%* | *0,910* | *70,8%* | *71,6%* |
| **Total com preço** | **83,8%** | **0,914** | **71,4%** | **68,7%** |
| *Grande POA sem preço (Teste 2)* | *85,9%* | *0,930* | *77,7%* | *74,5%* |
| **Grande POA com preço** | **86,3%** | **0,937** | **79,8%** | **73,1%** |

As referências "chutar sempre Livre" e "só o normal da quadra" são as mesmas dos Testes 1 e 2, porque não dependem das colunas do modelo.

Matriz de confusão, modelo total com preço:

| | Previu Livre | Previu Ocupado |
|---|---|---|
| **Real Livre** | 1.359 | 159 |
| **Real Ocupado** | 181 | 397 |

Matriz de confusão, modelo Grande POA com preço:

| | Previu Livre | Previu Ocupado |
|---|---|---|
| **Real Livre** | 967 | 84 |
| **Real Ocupado** | 122 | 332 |

### Resultados por período

| Modelo | Período | Linhas | Acerto | Ocupação real | Ocupação prevista |
|---|---|---|---|---|---|
| Total | Manhã | 606 | 85,8% | 24,9% | 23,3% |
| Total | Tarde | 572 | 82,3% | 17,8% | 23,3% |
| Total | Noite | 918 | 83,3% | 35,4% | 39,8% |
| Grande POA | Manhã | 504 | 86,5% | 25,6% | 24,3% |
| Grande POA | Tarde | 458 | 87,3% | 21,2% | 24,7% |
| Grande POA | Noite | 543 | 85,3% | 42,0% | 42,6% |

### Validação por arena (GroupKFold, 5 rodadas)

Cada rodada testa em arenas que o modelo não viu no treino. Valores médios das 5 rodadas:

| Modelo | Erro sem modelo | Erro com modelo | AUC só normal | AUC com modelo |
|---|---|---|---|---|
| Total com preço | 0,337 | 0,300 | 0,727 | 0,811 |
| Grande POA com preço | 0,347 | 0,323 | 0,712 | 0,779 |

Importância das colunas (quanto o erro piora sem a coluna), as cinco primeiras:

| Coluna | Total | Grande POA |
|---|---|---|
| `hora` | 0,0476 | 0,0437 |
| `valor_horario` | 0,0124 | 0,0059 |
| `dia_semana` | 0,0094 | 0,0023 |
| `periodo` | 0,0027 | 0,0013 |
| `tipo_quadra` | 0,0026 | 0,0010 |

### Conclusões

- O preço passa a ser a segunda coluna mais importante nos dois modelos, atrás apenas da hora.
- No modelo Grande POA, o preço melhora todas as métricas, exceto o recall: a precisão sobe de 77,7% para 79,8%, a AUC de 0,930 para 0,937, e a diferença entre a ocupação prevista e a real à noite cai de 3,5 para 0,6 pontos.
- No modelo total, o efeito é praticamente nulo: AUC e precisão sobem um pouco, mas o recall cai de 71,6% para 68,7% e o acerto fica 0,2 ponto abaixo.
- O ganho é pequeno, provavelmente porque o preço varia pouco dentro de uma mesma quadra e o efeito já é captado em boa parte pelo normal da quadra. Um próximo teste pode usar o preço relativo à média da própria quadra.
- Como nos testes anteriores, a validação tem só 10 a 11 dias, e os resultados precisam ser confirmados com extrações mais longas.

## Teste 4 — Impacto do preço por segmento de esporte (futebol × areia), divisão temporal 90/10

**Data do teste:** 27/10/2026
**Objetivo:** verificar se o preço influencia a ocupação de forma diferente conforme o esporte. A hipótese é que no futebol o valor é dividido entre muitos jogadores e pesa menos, enquanto nos esportes de areia, com menos pessoas por horário, o preço pesa mais.

### Dados utilizados

- Pasta: `.extracoes-ate-27-09-2026-pos-processamento`
- Alvo: `ocupado` = 1 quando o status é Indisponível e 0 quando é Livre
- Colunas usadas pelo modelo: as mesmas do Teste 3, incluindo `valor_horario`. Nas rodadas "sem preço", `valor_horario` é retirado de `FEATURES` só durante a execução.
- Segmentos (`SPORT_SEGMENTS` de `model/train.py`, filtrados pela opção `--segmentos`):

| Segmento | Esportes |
|---|---|
| futebol | Futebol society, Futebol de salão, Grama 5, Grama 7 |
| areia | Beach Tennis, Futevôlei, Vôlei de praia |
| outros (fora deste teste) | Padel, Handebol |

| Segmento | Região | Horários | Quadras | Arenas | Cidades |
|---|---|---|---|---|---|
| Areia | Total | 12.965 | 34 | 10 | Araricá, Blumenau, Canoas, Erechim, Parobé, Porto Alegre, Taquara, Três Coroas |
| Areia | Grande POA | 10.970 | 25 | 7 | Araricá, Canoas, Parobé, Porto Alegre, Taquara |
| Futebol | Total | 5.942 | 40 | 10 | Alvorada, Ananindeua, Belém, Canoas, Franca, Novo Hamburgo, Patrocínio, Paço do Lumiar |
| Futebol | Grande POA | 2.538 | 18 | 5 | Alvorada, Canoas, Novo Hamburgo |

A Grande POA usa a mesma lista de arenas excluídas do Teste 2. A `sp-sports` (Canoas) tem quadras dos dois segmentos e aparece nos dois, cada uma com as suas quadras.

### Como o modelo foi treinado

Mesmo procedimento dos Testes 1 a 3 (corte por dia inteiro em 90/10, normal da quadra só com o treino, alvo `ocupado − normal_treino`, `HistGradientBoostingRegressor` com `random_state=0` e limiar de 0,5). A única novidade é o filtro `--segmentos`, aplicado às linhas logo após a leitura, antes de calcular o normal da quadra.

### Separação dos dias

| Segmento | Região | Treino | Linhas | Validação | Linhas | % validação |
|---|---|---|---|---|---|---|
| Areia | Total | 21/08/2026 a 19/09/2026 | 11.516 | 20/09/2026 a 01/10/2026 | 1.449 | 11,2% |
| Areia | Grande POA | 21/08/2026 a 20/09/2026 | 9.736 | 21/09/2026 a 25/09/2026 | 1.234 | 11,3% |
| Futebol | Total | 21/08/2026 a 20/09/2026 | 5.343 | 21/09/2026 a 30/09/2026 | 599 | 10,1% |
| Futebol | Grande POA | 21/08/2026 a 20/09/2026 | 2.267 | 21/09/2026 a 30/09/2026 | 271 | 10,7% |

### Comandos utilizados

Executados a partir da raiz do projeto. Com preço (`$SEG` = `futebol` ou `areia`; para a Grande POA, acrescentar o mesmo `--excluir` do Teste 2):

```bash
.venv/bin/python -m model.train .extracoes-ate-27-09-2026-pos-processamento --saida .modelo/$SEG-total-com-preco.joblib --teste 0.1 --segmentos $SEG
```

Sem preço, retirando `valor_horario` das colunas só nesta execução:

```bash
.venv/bin/python -c "
import sys, model.train as t
t.FEATURES.remove('valor_horario')
sys.argv=['train']+sys.argv[1:]
t.main()" .extracoes-ate-27-09-2026-pos-processamento --saida /tmp/$SEG-total-sem-preco.joblib --teste 0.1 --segmentos $SEG
```

Os modelos com preço foram salvos em `.modelo/{futebol,areia}-{total,grande-poa}-com-preco.joblib`.

### Resultados gerais

| Segmento | Região | Ocupação real | Abordagem | Acerto | AUC | Precisão | Recall |
|---|---|---|---|---|---|---|---|
| Areia | Total | 28,0% | Só o normal da quadra | 74,8% | 0,808 | 56,3% | 45,1% |
| Areia | Total | | Sem preço | 84,4% | 0,904 | 72,8% | 70,7% |
| Areia | Total | | **Com preço** | **87,2%** | **0,925** | **76,6%** | **78,1%** |
| Areia | Grande POA | 27,9% | Só o normal da quadra | 75,5% | 0,839 | 58,0% | 43,0% |
| Areia | Grande POA | | Sem preço | 84,8% | 0,928 | 73,4% | 71,2% |
| Areia | Grande POA | | **Com preço** | **86,7%** | **0,939** | **75,7%** | **77,0%** |
| Futebol | Total | 32,2% | Só o normal da quadra | 72,0% | 0,728 | 61,7% | 34,2% |
| Futebol | Total | | Sem preço | 79,6% | 0,874 | 71,3% | 61,7% |
| Futebol | Total | | **Com preço** | **80,0%** | **0,883** | **71,1%** | **63,7%** |
| Futebol | Grande POA | 40,6% | Só o normal da quadra | 67,5% | 0,752 | 60,6% | 57,3% |
| Futebol | Grande POA | | Sem preço | 81,9% | 0,893 | 80,8% | 72,7% |
| Futebol | Grande POA | | **Com preço** | **82,3%** | **0,913** | **81,6%** | **72,7%** |

Matrizes de confusão dos modelos com preço:

| Segmento | Região | Real Livre → Previu Livre | Real Livre → Previu Ocupado | Real Ocupado → Previu Livre | Real Ocupado → Previu Ocupado |
|---|---|---|---|---|---|
| Areia | Total | 946 | 97 | 89 | 317 |
| Areia | Grande POA | 805 | 85 | 79 | 265 |
| Futebol | Total | 356 | 50 | 70 | 123 |
| Futebol | Grande POA | 143 | 18 | 30 | 80 |

### Resultados por período (modelos com preço)

| Segmento | Região | Período | Linhas | Acerto | Ocupação real | Ocupação prevista |
|---|---|---|---|---|---|---|
| Areia | Total | Manhã | 451 | 91,6% | 24,0% | 23,9% |
| Areia | Total | Tarde | 467 | 83,9% | 22,9% | 27,3% |
| Areia | Total | Noite | 531 | 86,3% | 36,0% | 38,3% |
| Areia | Grande POA | Manhã | 407 | 87,0% | 21,9% | 22,4% |
| Areia | Grande POA | Tarde | 377 | 86,2% | 21,5% | 25,8% |
| Areia | Grande POA | Noite | 450 | 86,9% | 38,7% | 40,3% |
| Futebol | Total | Manhã | 137 | 75,2% | 45,3% | 33,1% |
| Futebol | Total | Tarde | 125 | 84,0% | 16,8% | 19,3% |
| Futebol | Total | Noite | 337 | 80,4% | 32,6% | 37,9% |
| Futebol | Grande POA | Manhã | 97 | 82,5% | 41,2% | 36,0% |
| Futebol | Grande POA | Tarde | 81 | 80,2% | 19,8% | 22,8% |
| Futebol | Grande POA | Noite | 93 | 83,9% | 58,1% | 53,1% |

### Validação por arena (GroupKFold, 5 rodadas)

AUC média das 5 rodadas, sempre testando em arenas que o modelo não viu, e importância do preço (quanto o erro piora sem a coluna):

| Segmento | Região | AUC só normal | AUC sem preço | AUC com preço | Importância do preço | Posição |
|---|---|---|---|---|---|---|
| Areia | Total | 0,699 | 0,749 | 0,758 | 0,0240 | 2º |
| Areia | Grande POA | 0,688 | 0,771 | 0,756 | 0,0057 | 3º |
| Futebol | Total | 0,630 | 0,770 | 0,776 | −0,0032 | 10º |
| Futebol | Grande POA | 0,590 | 0,726 | 0,730 | −0,0003 | 6º |

Para comparação, no modelo com todos os esportes (Teste 3) a importância do preço foi 0,0124 no total e 0,0059 na Grande POA.

### Conclusões

- Na areia, o preço melhora a previsão nos dias mais recentes: no total, o acerto sobe de 84,4% para 87,2% e o recall de 70,7% para 78,1%. É a segunda coluna mais importante, com quase o dobro da importância que tem no modelo com todos os esportes.
- No futebol, o preço não ajuda: a importância fica negativa e as métricas mudam muito pouco. Na Grande POA, a diferença no acerto corresponde a 1 horário em 271.
- Esse resultado é coerente com a hipótese de que o preço pesa menos no futebol, mas não a comprova. Boa parte das quadras de futebol tem preço fixo (as 12 da `arena-grenal`, em Alvorada, por exemplo), então o modelo tem pouca variação de preço para aprender. Para separar os dois efeitos, seria preciso comparar só quadras de futebol cujo preço varia ao longo do dia.
- Na validação por arena da areia na Grande POA, a AUC cai de 0,771 para 0,756 com preço: o preço ajuda a prever dias futuros nas arenas conhecidas, mas não a generalizar para uma arena nova.
- As amostras são pequenas, sobretudo no futebol da Grande POA (5 arenas, 271 horários de validação), e a validação da areia na Grande POA cobre só de 21/09 a 25/09.
- Algumas quadras de futebol aparecem em mais de um arquivo (os de nome `...sem-horarios-cadastrados...`, em Belém e Ananindeua), o que infla a contagem de quadras e divide o normal dessas quadras.
