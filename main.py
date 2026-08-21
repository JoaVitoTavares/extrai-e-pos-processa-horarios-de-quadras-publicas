"""Gerenciador das extrações: roda os coletores em sequência e grava o resultado."""

import sys
import requests
from playwright.sync_api import TimeoutError as PWTimeout

from courts_collector import coletar_horarios, esportes_alvo, listar_esportes, tipos_ausentes
from persistencia import salvar_extracao
from tratamento import TratamentoDeDados
from weather_collector import coletar_clima, coletar_previsao


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


def registrar_clima() -> str | None:
    print("\n>> CLIMA (API Open-Meteo): condições atuais na arena...")
    try:
        return coletar_clima()
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] clima não coletado: {erro}", file=sys.stderr)
        return None


def registrar_previsao() -> str | None:
    print("\n>> PREVISÃO (API Open-Meteo): horas à frente na arena...")
    try:
        return coletar_previsao()
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] previsão não coletada: {erro}", file=sys.stderr)
        return None


def _imprimir_extracao(dados: dict) -> None:
    print("\n" + "=" * 46)
    print(f"  {dados['esporte']}  |  {dados['data']}  |  Período: {dados['periodo']}")
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
    """Executa a extração ponta a ponta: coleta as quadras de hoje e dos próximos dias,
    imprime o que achou, grava um CSV por quadra — é na gravação que a reserva feita
    entre duas rodadas é detectada —, registra a leitura de clima e a previsão, e aplica
    as duas nas reservas. Uma execução que não colete quadra nenhuma sai com erro em vez
    de gravar silêncio — o modo de falha mais caro num coletor agendado."""
    modo_visivel = "--ver" in sys.argv

    resultados = coletar_quadras(modo_visivel)
    for dados in resultados:
        _imprimir_extracao(dados)

    caminhos = salvar_extracao(resultados)
    caminho_clima = registrar_clima()
    caminho_previsao = registrar_previsao()
    enriquecidos = TratamentoDeDados().aplicar()

    if not caminhos:
        print("\n[ERRO] nenhuma quadra coletada em nenhum esporte.", file=sys.stderr)
        sys.exit(1)

    print(f"\n>> Extração salva/atualizada em {len(caminhos)} arquivo(s):")
    for caminho in caminhos:
        print(f"   {caminho}")
    if caminho_clima:
        print(f"\n>> Clima registrado em {caminho_clima}")
    if caminho_previsao:
        print(f">> Previsão registrada em {caminho_previsao}")
    print(f">> Clima aplicado em {len(enriquecidos)} arquivo(s) de quadra.")
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
