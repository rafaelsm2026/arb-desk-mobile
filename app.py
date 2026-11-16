
import streamlit as st
import pandas as pd
import ccxt

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

st.set_page_config(
    page_title="Arb Desk Mobile v0.8",
    page_icon="💱",
    layout="wide"
)

st.title("💱 Arb Desk Mobile v0.8")
st.caption("Arbitragem USDT/BRL | Monitoramento e simulação")

st.warning(
    "Somente simulação. O aplicativo não executa compras, "
    "vendas ou transferências reais."
)

EXCHANGES = {
    "Mercado Bitcoin": "mercado",
    "Foxbit": "foxbit",
    "Kraken": "kraken",
    "Coinbase": "coinbase",
    "Bitget": "bitget",
    "KuCoin": "kucoin",
    "MEXC": "mexc",
    "Bybit": "bybit",
}

with st.expander("⚙️ Configurações", expanded=True):

    capital = st.number_input(
        "Capital inicial (R$)",
        min_value=100.0,
        value=5000.0,
        step=100.0
    )

    fee_buy = st.number_input(
        "Taxa de compra (%)",
        min_value=0.0,
        value=0.1,
        step=0.05
    )

    fee_sell = st.number_input(
        "Taxa de venda (%)",
        min_value=0.0,
        value=0.1,
        step=0.05
    )

    transfer_fee = st.number_input(
        "Taxa de transferência (USDT)",
        min_value=0.0,
        value=1.0,
        step=0.1
    )

    min_profit = st.number_input(
        "Lucro mínimo (R$)",
        min_value=0.0,
        value=10.0,
        step=5.0
    )

    selected = st.multiselect(
        "Corretoras",
        list(EXCHANGES.keys()),
        default=["Mercado Bitcoin", "Foxbit"]
    )

    show_all = st.checkbox(
        "Mostrar operações mesmo sem lucro",
        value=False
    )

st.info(
    "Esta versão consulta USDT/BRL. "
    "Corretoras sem esse mercado serão identificadas no diagnóstico."
)


def simulate_book(levels, amount, buy=False):
    remaining = float(amount)
    received = 0.0

    for level in levels:
        price = float(level[0])
        quantity = float(level[1])

        if price <= 0 or quantity <= 0:
            continue

        if buy:
            spent = min(remaining, price * quantity)
            received += spent / price
            remaining -= spent
        else:
            sold = min(remaining, quantity)
            received += sold * price
            remaining -= sold

        if remaining < 0.00000001:
            break

    return received, remaining


@st.cache_data(ttl=30, show_spinner=False)
def fetch_exchange(name):

    exchange_id = EXCHANGES[name]

    try:
        exchange_class = getattr(ccxt, exchange_id, None)

        if exchange_class is None:
            return None, "Integração indisponível no CCXT"

        exchange = exchange_class({
            "enableRateLimit": True,
            "timeout": 8000,
        })

        exchange.load_markets()

        symbol = "USDT/BRL"

        if symbol not in exchange.markets:
            return None, "USDT/BRL não listado"

        market = exchange.market(symbol)

        if market.get("spot") is False:
            return None, "Mercado não é spot"

        if market.get("active") is False:
            return None, "Mercado inativo"

        book = exchange.fetch_order_book(
            symbol,
            limit=20
        )

        asks = book.get("asks") or []
        bids = book.get("bids") or []

        if not asks or not bids:
            return None, "Livro de ofertas vazio"

        ask = float(asks[0][0])
        bid = float(bids[0][0])

        if ask <= 0 or bid <= 0:
            return None, "Preços inválidos"

        return {
            "ask": ask,
            "bid": bid,
            "asks": asks,
            "bids": bids,
        }, "Conectada"

    except Exception as error:
        message = str(error).replace("\n", " ")
        return None, (
            type(error).__name__ + ": " + message[:130]
        )


if st.button("🔄 Atualizar cotações", type="primary"):
    fetch_exchange.clear()
    st.rerun()


st.subheader("🌐 Diagnóstico das conexões")

quotes = {}
diagnostics = []

if selected:

    progress = st.progress(0)
    status_text = st.empty()

    with ThreadPoolExecutor(
        max_workers=min(4, len(selected))
    ) as executor:

        futures = {
            executor.submit(fetch_exchange, name): name
            for name in selected
        }

        for index, future in enumerate(
            as_completed(futures), start=1
        ):

            name = futures[future]

            try:
                quote, status = future.result()
            except Exception as error:
                quote = None
                status = type(error).__name__

            diagnostics.append({
                "Corretora": name,
                "Situação": status,
            })

            if quote:
                quotes[name] = quote

            progress.progress(index / len(selected))
            status_text.write(
                f"Consultas concluídas: {index}/{len(selected)}"
            )

else:
    st.info("Selecione pelo menos uma corretora.")

c1, c2 = st.columns(2)

c1.metric("Conectadas", len(quotes))
c2.metric("Selecionadas", len(selected))

if diagnostics:
    st.dataframe(
        pd.DataFrame(diagnostics),
        hide_index=True,
        use_container_width=True
    )


st.subheader("💰 Preços do USDT em reais")

price_rows = []

for name, quote in quotes.items():

    price_rows.append({
        "Corretora": name,
        "Comprar USDT (R$)": quote["ask"],
        "Vender USDT (R$)": quote["bid"],
    })

if price_rows:
    st.dataframe(
        pd.DataFrame(price_rows),
        hide_index=True,
        use_container_width=True
    )
else:
    st.info(
        "Nenhuma cotação USDT/BRL disponível "
        "nas corretoras selecionadas."
    )


st.subheader("📊 Oportunidades de arbitragem")

results = []

for buy_name, buy_quote in quotes.items():

    quantity, unspent = simulate_book(
        buy_quote["asks"],
        capital,
        buy=True
    )

    if unspent > 0.01:
        continue

    quantity *= (1 - fee_buy / 100)
    quantity -= transfer_fee

    if quantity <= 0:
        continue

    for sell_name, sell_quote in quotes.items():

        if buy_name == sell_name:
            continue

        proceeds, unsold = simulate_book(
            sell_quote["bids"],
            quantity,
            buy=False
        )

        if unsold > 0.000001:
            continue

        final_brl = proceeds * (1 - fee_sell / 100)

        profit = final_brl - capital
        percent = profit / capital * 100

        results.append({
            "Comprar": buy_name,
            "Vender": sell_name,
            "USDT transferido": round(quantity, 4),
            "Receber (R$)": round(final_brl, 2),
            "Lucro estimado (R$)": round(profit, 2),
            "Retorno (%)": round(percent, 3),
        })


if results:

    df = pd.DataFrame(results).sort_values(
        "Lucro estimado (R$)",
        ascending=False
    )

    best = df.iloc[0]

    st.metric(
        "Melhor resultado estimado",
        f"R$ {best['Lucro estimado (R$)']:.2f}"
    )

    if not show_all:
        df = df[df["Lucro estimado (R$)"] >= min_profit]

    if df.empty:
        st.info(
            "Nenhuma oportunidade superou o lucro mínimo."
        )
    else:
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True
        )

else:
    st.info(
        "São necessárias duas corretoras com USDT/BRL "
        "e liquidez suficiente para calcular a arbitragem."
    )


st.caption(
    "Consulta UTC: " +
    datetime.now(timezone.utc).strftime(
        "%d/%m/%Y %H:%M:%S"
    )
)

st.error(
    "Os resultados não garantem lucro. "
    "O sistema ainda não verifica disponibilidade de "
    "depósitos e saques, redes compatíveis, taxas reais "
    "de transferência, impostos, tempo de envio ou "
    "mudanças de preço durante a operação. "
    "Alertas Telegram ainda não estão ativos."
)
