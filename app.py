
import streamlit as st
import requests
from datetime import datetime

st.set_page_config(
    page_title="Arb Desk Mobile",
    page_icon="📈",
    layout="wide"
)

st.title("📈 ARB DESK MOBILE")
st.caption("Monitoramento de arbitragem | Modo simulação")

st.warning("Sistema em teste. Nenhuma operação real será executada.")

capital = st.number_input(
    "Capital simulado (R$)",
    min_value=100.0,
    value=5000.0,
    step=100.0
)

taxa_compra = st.number_input(
    "Taxa de compra (%)",
    value=0.10,
    min_value=0.0
)

taxa_venda = st.number_input(
    "Taxa de venda (%)",
    value=0.10,
    min_value=0.0
)

moedas = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
resultados = []

for moeda in moedas:
    try:
        binance = requests.get(
            "https://api.binance.com/api/v3/ticker/bookTicker",
            params={"symbol": moeda},
            timeout=10
        ).json()

        bybit = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "spot", "symbol": moeda},
            timeout=10
        ).json()

        if "bidPrice" not in binance:
            raise ValueError("Cotação Binance indisponível")

        if bybit.get("retCode") != 0:
            raise ValueError("Cotação Bybit indisponível")

        cotacao_bybit = bybit["result"]["list"][0]

        precos = {
            "Binance": {
                "compra": float(binance["askPrice"]),
                "venda": float(binance["bidPrice"])
            },
            "Bybit": {
                "compra": float(cotacao_bybit["ask1Price"]),
                "venda": float(cotacao_bybit["bid1Price"])
            }
        }

        for origem, destino in [
            ("Binance", "Bybit"),
            ("Bybit", "Binance")
        ]:
            compra = precos[origem]["compra"]
            venda = precos[destino]["venda"]

            if compra <= 0 or venda <= 0:
                continue

            quantidade = (
                capital / compra
            ) * (1 - taxa_compra / 100)

            receita = (
                quantidade * venda
            ) * (1 - taxa_venda / 100)

            lucro = receita - capital
            percentual = (lucro / capital) * 100

            resultados.append({
                "Moeda": moeda,
                "Comprar": origem,
                "Vender": destino,
                "Lucro estimado (USDT)": round(lucro, 4),
                "Retorno (%)": round(percentual, 3)
            })

    except (requests.RequestException, ValueError, KeyError,
            IndexError, TypeError) as erro:
        st.error(f"{moeda}: {erro}")

st.subheader("Oportunidades encontradas")

if resultados:
    resultados.sort(
        key=lambda item: item["Retorno (%)"],
        reverse=True
    )
    st.dataframe(resultados, use_container_width=True)
else:
    st.info("Nenhuma cotação disponível no momento.")

st.caption(
    "Cálculo indicativo em USDT, não em reais. "
    "Não considera profundidade do livro, slippage, "
    "transferências ou execução simultânea. "
    "Não representa lucro realizado."
)

st.caption(
    "Última consulta: "
    + datetime.now().strftime("%d/%m/%Y %H:%M:%S")
)

if st.button("🔄 Atualizar cotações"):
    st.rerun()
