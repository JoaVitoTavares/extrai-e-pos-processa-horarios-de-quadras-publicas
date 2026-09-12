# CLAUDE.md

Instruções para trabalho neste repositório. Leia antes de propor qualquer alteração.

## Como conduzir uma task

- Plano primeiro, código depois. Antes de escrever qualquer linha, descreva o que
  será alterado, em quais arquivos, e o que a alteração quebra ou não quebra.
- Uma etapa por vez. Entregue a menor unidade que pode ser lida, avaliada e
  commitada isoladamente. Não emende a etapa seguinte sem aprovação.
- Mudança mínima. Altere apenas o que a task exige. Não refatore código vizinho,
  não reordene funções, não renomeie o que não está no escopo.
- Não reescreva o que já funciona. Se um trecho existente resolve o problema,
  use ele.
- Diga o que você não sabe. Se a decisão depende de algo que não está no código
  acessível, pergunte em vez de assumir.

## Documentação e comentários

A documentação do código vive em **uma docstring por função**, no topo da função
(primeira linha após a assinatura, o "bloco de documentação" da função em
Python). Nada de banners de módulo, divisores de seção (`# ---- ... ----`) nem
comentários soltos explicando linhas dentro das funções.

Regras da docstring de cada função:

- **Um parágrafo apenas**, explicando o que a função faz.
- **No máximo 3 linhas.**
- Aspas triplas (`"""..."""`) logo abaixo do `def`.

O que **evitar**:

- Comentários inline explicando o passo a passo (`# --- setup ---`, `# espera ...`).
  Se um trecho precisa de explicação, prefira um nome melhor de variável/função.
- Docstring de módulo em formato de banner. No máximo uma linha curta de título.
- Comentários acima de constantes; o nome da constante deve se explicar sozinho.

Exemplo:

```python
def coletar_horarios(esporte, periodo=None, headless=True):
    """Abre o navegador uma vez e extrai os horários de um esporte. Com `periodo`
    informado coleta apenas aquele; com None percorre PERIODOS_PADRAO. Retorna
    sempre uma lista, com um item por período coletado."""
    ...
```

## Nomes

- Código e identificadores em inglês, seguindo o que já existe no arquivo.
- Constantes em maiúsculas, com nome autoexplicativo.
- Docstrings em portugues.


## Dependências

- Não adicione camadas de abstração, type hints, testes ou logging estruturado
  que não foram pedidos., você pode sugeri-los quando realmente necessário

## Fora do escopo sem aprovação

- Criar testes os quais não foram pedidos