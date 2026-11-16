
import streamlit as st
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(
    page_title="Arb Desk Mobile",
    page_icon="📈",
    layout="centered"
)

st.title("📈 ARB DESK MOBILE")
st.caption("Versão 0.3 | Monitoramento e simulação")

st.warning(
    "MODO TESTE — Nenhuma operação real é executada."
)

capital = st.number_input(
    "Capital simulado (USDT)",
    min_value=100.0,
    value=1000.0,
    step=100.0
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

st.caption(
    "Os valores estão em USDT. "
    "O capital inicial de R$ 5.000 ainda não "
    "é convertido automaticamente."
)

MOEDAS = {
    "BTC": {
        "Kraken": "XBTUSDT",
        "Coinbase": "BTC-USDT"
    },
    "ETH": {
        "Kraken": "ETHUSDT",
        "Coinbase": "ETH-USDT"
    },
    "SOL": {
        "Kraken": "SOLUSDT",
        "Coinbase": "SOL-USDT"
    }
}

def buscar_json(url, params, nome):
    try:
        resposta = requests.get(
            url,
            params=params,
            timeout=12,
            headers={
                "Accept": "application/json",
                "User-Agent": "ArbDeskMobile/0.3"
            }
        )

        if resposta.status_code != 200:
            raise ValueError(
                f"{nome}: HTTP {resposta.status_code}"
            )

        try:
            return resposta.json()
        except ValueError:
            raise ValueError(
                f"{nome}: resposta JSON inválida"
            )

    except requests.RequestException as erro:
        raise ValueError(
            f"{nome}: falha de conexão ({erro})"
        )

def consultar_kraken(par):
    dados = buscar_json(
        "https://api.kraken.com/0/public/Ticker",
        {"pair": par},
        "Kraken"
    )

    if dados.get("error"):
        raise ValueError(
            "Kraken: " + str(dados["error"])
        )

    resultado = dados.get("result", {})

    if not resultado:
        raise ValueError(
            "Kraken: cotação indisponível"
        )

    ticker = next(iter(resultado.values()))

    return {
        "ask": float(ticker["a"][0]),
        "bid": float(ticker["b"][0])
    }

def consultar_coinbase(par):
    dados = buscar_json(
        "https://api.exchange.coinbase.com/products/"
        + par + "/ticker",
        None,
        "Coinbase"
    )

    return {
        "ask": float(dados["ask"]),
        "bid": float(dados["bid"])
    }

def consultar_mercado(moeda, corretora, par):
    if corretora == "Kraken":
        precos = consultar_kraken(par)
    else:
        precos = consultar_coinbase(par)

    if precos["ask"] <= 0 or precos["bid"] <= 0:
        raise ValueError(
            f"{corretora}: preço inválido"
        )

    if precos["ask"] < precos["bid"]:
        raise ValueError(
            f"{corretora}: preços inconsistentes"
        )

    return moeda, corretora, precos

st.subheader("🔎 Monitoramento de mercado")

tarefas = []

for moeda, corretoras in MOEDAS.items():
    for corretora, par in corretoras.items():
        tarefas.append((moeda, corretora, par))

cotacoes = {}
diagnosticos = []

with st.spinner("Consultando corretoras..."):
    with ThreadPoolExecutor(max_workers=6) as executor:
        futuros = [
            executor.submit(
                consultar_mercado,
                moeda,
                corretora,
                par
            )
            for moeda, corretora, par in tarefas
        ]

        for tarefa, futuro in zip(tarefas, futuros):
            moeda, corretora, par = tarefa

            try:
                _, _, precos = futuro.result()
                cotacoes[(moeda, corretora)] = precos

                diagnosticos.append({
                    "Moeda": moeda,
                    "Corretora": corretora,
                    "Status": "Conectada"
                })

            except (
                ValueError,
                KeyError,
                TypeError,
                IndexError,
                StopIteration
            ) as erro:
                diagnosticos.append({
                    "Moeda": moeda,
                    "Corretora": corretora,
                    "Status": str(erro)
                })

resultados = []

for moeda in MOEDAS:
    for origem, destino in [
        ("Kraken", "Coinbase"),
        ("Coinbase", "Kraken")
    ]:
        if (
            (moeda, origem) not in cotacoes
            or (moeda, destino) not in cotacoes
        ):
            continue

        compra = cotacoes[(moeda, origem)]["ask"]
        venda = cotacoes[(moeda, destino)]["bid"]

        quantidade = (
            capital / compra
        ) * (1 - taxa_compra / 100)

        recebido = (
            quantidade * venda
        ) * (1 - taxa_venda / 100)

        resultado = recebido - capital
        percentual = resultado / capital * 100

        resultados.append({
            "Moeda": moeda,
            "Comprar": origem,
            "Vender": destino,
            "Compra": round(compra, 6),
            "Venda": round(venda, 6),
            "Resultado (USDT)": round(resultado, 4),
            "Retorno (%)": round(percentual, 3)
        })

st.subheader("📊 Comparação de arbitragem")

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
        item["Resultado (USDT)"] > 0
        for item in resultados
    )

    st.metric(
        "Diferenças positivas estimadas",
        positivas
    )

    melhor = resultados[0]

    st.metric(
        "Maior retorno estimado",
        f"{melhor['Retorno (%)']:.3f}%"
    )

else:
    st.info(
        "Não foi possível comparar as duas "
        "corretoras neste momento."
    )

st.subheader("🌐 Diagnóstico das conexões")

for item in diagnosticos:
    descricao = (
        f"{item['Moeda']} | "
        f"{item['Corretora']} — "
        f"{item['Status']}"
    )

    if item["Status"] == "Conectada":
        st.success(descricao)
    else:
        st.error(descricao)

st.info(
    "As diferenças são estimativas baseadas "
    "nas melhores ofertas disponíveis. "
    "Não consideram profundidade do livro, "
    "slippage, transferências, latência "
    "ou execução simultânea. "
    "Não representam lucro realizado."
)

st.caption(
    "Última consulta (UTC): "
    + datetime.now(timezone.utc).strftime(
        "%d/%m/%Y %H:%M:%S"
    )
)

if st.button("🔄 Atualizar cotações"):
    st.rerun()
