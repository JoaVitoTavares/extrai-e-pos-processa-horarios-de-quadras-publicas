# Convenções do projeto

## Documentação e comentários

A documentação do código vive em **uma docstring por função**, no topo da função
(primeira linha após a assinatura — é o "bloco de documentação" da função em
Python). Nada de banners de módulo, divisores de seção (`# ---- ... ----`) nem
comentários soltos explicando linhas dentro das funções.

Regras da docstring de cada função:

- **Um parágrafo apenas**, explicando o que a função faz.
- **No máximo 6 linhas.**
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
