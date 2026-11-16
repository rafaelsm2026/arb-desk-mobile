
import streamlit as st
import requests
from datetime import datetime

st.set_page_config(
    page_title="Arb Desk Mobile",
    page_icon="📈",
    layout="centered"
)

st.title("📈 ARB DESK MOBILE")
st.caption("Arbitragem de criptomoedas | Simulação")

st.warning(
    "Modo teste: nenhuma compra ou venda real será realizada."
)

capital = st.number_input(
    "Capital simulado (USDT)",
    min_value=100.0,
    value=1000.0,
    step=100.0
)

st.caption(
    "O capital está em USDT. "
    "A conversão de R$ 5.000 para USDT "
    "será implementada posteriormente."
)

taxa_compra = st.number_input(
    "Taxa de compra (%)",
    min_value=0.0,
    value=0.10,
    step=0.01
)

taxa_venda = st.number_input(
    "Taxa de venda (%)",
    min_value=0.0,
    value=0.10,
    step=0.01
)

def consultar_json(url, params, corretora):
    try:
        resposta = requests.get(
            url,
            params=params,
            timeout=12,
            headers={
                "User-Agent": "ArbDeskMobile/0.1",
                "Accept": "application/json"
            }
        )

        if resposta.status_code != 200:
            raise ValueError(
                f"{corretora}: HTTP {resposta.status_code}"
            )

        try:
            dados = resposta.json()
        except ValueError:
            raise ValueError(
                f"{corretora}: resposta não é JSON válido"
            )

        return dados

    except requests.RequestException as erro:
        raise ValueError(
            f"{corretora}: falha de conexão: {erro}"
        )

def consultar_binance(moeda):
    dados = consultar_json(
        "https://api.binance.com/api/v3/ticker/bookTicker",
        {"symbol": moeda},
        "Binance"
    )

    if not isinstance(dados, dict):
        raise ValueError("Binance: formato inesperado")

    if "askPrice" not in dados or "bidPrice" not in dados:
        raise ValueError(
            "Binance: preços indisponíveis ou API bloqueada"
        )

    return {
        "ask": float(dados["askPrice"]),
        "bid": float(dados["bidPrice"])
    }

def consultar_bybit(moeda):
    dados = consultar_json(
        "https://api.bybit.com/v5/market/tickers",
        {"category": "spot", "symbol": moeda},
        "Bybit"
    )

    if not isinstance(dados, dict):
        raise ValueError("Bybit: formato inesperado")

    if dados.get("retCode") != 0:
        raise ValueError(
            f"Bybit: {dados.get('retMsg', 'Erro na API')}"
        )

    lista = dados.get("result", {}).get("list", [])

    if not lista:
        raise ValueError("Bybit: cotação não encontrada")

    return {
        "ask": float(lista[0]["ask1Price"]),
        "bid": float(lista[0]["bid1Price"])
    }

st.subheader("🔎 Monitoramento de mercado")

moedas = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

resultados = []
erros = []

with st.spinner("Consultando corretoras..."):
    for moeda in moedas:
        precos = {}

        try:
            precos["Binance"] = consultar_binance(moeda)
        except (ValueError, KeyError, TypeError) as erro:
            erros.append(f"{moeda} | {erro}")

        try:
            precos["Bybit"] = consultar_bybit(moeda)
        except (ValueError, KeyError, TypeError) as erro:
            erros.append(f"{moeda} | {erro}")

        if len(precos) != 2:
            continue

        for origem, destino in [
            ("Binance", "Bybit"),
            ("Bybit", "Binance")
        ]:
            compra = precos[origem]["ask"]
            venda = precos[destino]["bid"]

            if compra <= 0 or venda <= 0:
                continue

            quantidade = (
                capital / compra
            ) * (1 - taxa_compra / 100)

            recebido = (
                quantidade * venda
            ) * (1 - taxa_venda / 100)

            lucro = recebido - capital
            retorno = (lucro / capital) * 100

            resultados.append({
                "Moeda": moeda,
                "Comprar": origem,
                "Vender": destino,
                "Compra (USDT)": round(compra, 6),
                "Venda (USDT)": round(venda, 6),
                "Resultado estimado (USDT)": round(lucro, 4),
                "Retorno (%)": round(retorno, 3)
            })

if resultados:
    resultados.sort(
        key=lambda x: x["Retorno (%)"],
        reverse=True
    )

    st.dataframe(
        resultados,
        use_container_width=True,
        hide_index=True
    )

    positivas = sum(
        1 for item in resultados
        if item["Resultado estimado (USDT)"] > 0
    )

    st.metric(
        "Diferenças positivas estimadas",
        positivas
    )
else:
    st.info(
        "Ainda não foi possível comparar as duas corretoras."
    )

if erros:
    with st.expander("⚠️ Diagnóstico das conexões", expanded=True):
        for erro in erros:
            st.error(erro)

st.info(
    "Os cálculos são indicativos. Não consideram "
    "profundidade do livro, slippage, transferências, "
    "latência nem garantia de execução. "
    "Não representam lucro realizado."
)

st.caption(
    "Consulta realizada em: "
    + datetime.now().strftime("%d/%m/%Y %H:%M:%S")
)

if st.button("🔄 Atualizar cotações"):
    st.rerun()
