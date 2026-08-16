"""Gerenciador das extrações: roda os coletores em sequência e grava o resultado."""

import sys
import requests
from playwright.sync_api import TimeoutError as PWTimeout

from courts_collector import coletar_horarios, esportes_alvo, listar_esportes, tipos_ausentes
from persistencia import salvar_extracao


def coletar_quadras(modo_visivel: bool = False) -> list[dict]:
    """Roda as duas técnicas do coletor de quadras e devolve tudo o que foi extraído,
    relatando o progresso no terminal. Um esporte que estoure o tempo é reportado e
    pulado, para a lentidão do site em um não derrubar a coleta dos outros."""
    print(">> TÉCNICA 1 (API JSON, sem navegador): listando esportes...\n")
    esportes = listar_esportes()
    for i, e in enumerate(esportes, 1):
        print(f"   {i}. {e}")

    alvos = esportes_alvo(esportes)
    ausentes = tipos_ausentes(alvos)
    if ausentes:
        print(f"\n[AVISO] tipos de quadra não encontrados no site: {', '.join(ausentes)}")

    resultados = []
    for esporte in alvos:
        print(f"\n>> TÉCNICA 2 (Playwright): horários de '{esporte}' (todos os períodos)...")
        try:
            resultados.extend(coletar_horarios(esporte, periodo=None, headless=not modo_visivel))
        except PWTimeout as erro:
            print(f"[AVISO] '{esporte}' pulado por tempo esgotado: {erro}", file=sys.stderr)
    return resultados


def _imprimir_extracao(dados: dict) -> None:
    """Imprime o bloco de uma quadra num período: cabeçalho com esporte e cobertura,
    um horário por linha com 🟢 para livre e 🔴 para indisponível, e o resumo de vagas.
    Um período que não carregou mostra só o aviso, já que não há horário para listar."""
    print("\n" + "=" * 46)
    print(f"  {dados['esporte']}  |  Período: {dados['periodo']}")
    if dados["quadra"]:
        cobertura = {"true": "coberta", "false": "descoberta"}.get(dados["quadra_coberta"], "?")
        print(f"  {dados['quadra']}  ({cobertura})")
    print(f"  Coletado em: {dados['coletado_em']}")
    print("=" * 46)
    if dados["aviso"]:
        print(f"  ⚠️  {dados['aviso']}")
        print("=" * 46)
        return
    for h in dados["horarios"]:
        marca = "🟢" if h["status"].lower() == "livre" else "🔴"
        preco = f"  R$ {h['valor']:.2f}" if h.get("valor") is not None else ""
        print(f"  {marca} {h['hora']}  -  {h['status']}{preco}")
    livres = [h["hora"] for h in dados["horarios"] if h["status"].lower() == "livre"]
    print("=" * 46)
    print(f"  Livres: {len(livres)}  ->  {', '.join(livres) or '(nenhum)'}")


def main() -> None:
    """Executa a extração ponta a ponta: coleta as quadras, imprime o que achou e grava
    um CSV por quadra. Uma execução que não colete nada sai com erro em vez de gravar
    silêncio — o modo de falha mais caro num coletor agendado."""
    modo_visivel = "--ver" in sys.argv

    resultados = coletar_quadras(modo_visivel)
    for dados in resultados:
        _imprimir_extracao(dados)

    caminhos = salvar_extracao(resultados)
    if not caminhos:
        print("\n[ERRO] nenhuma quadra coletada em nenhum esporte.", file=sys.stderr)
        sys.exit(1)

    print(f"\n>> Extração salva/atualizada em {len(caminhos)} arquivo(s):")
    for caminho in caminhos:
        print(f"   {caminho}")
    print()


if __name__ == "__main__":
    try:
        main()
    except PWTimeout as e:
        print(f"\n[ERRO] Tempo esgotado: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\n[ERRO] Falha na API JSON: {e}", file=sys.stderr)
        sys.exit(1)
