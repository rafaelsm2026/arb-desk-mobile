
import streamlit as st
import pandas as pd
import ccxt
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

st.set_page_config(
    page_title="Arb Desk Mobile v1.0",
    page_icon="💱",
    layout="wide"
)

st.title("💱 Arb Desk Mobile v1.0")
st.caption("Monitor de arbitragem entre corretoras")
st.warning(
    "Simulação: não executa ordens nem transferências. "
    "Preços e oportunidades podem mudar rapidamente."
)

EXCHANGES = {
    "Foxbit": "foxbit",
    "Bitget": "bitget",
    "Mercado Bitcoin": "mercado",
    "Kraken": "kraken",
    "Coinbase": "coinbase",
    "KuCoin": "kucoin",
    "MEXC": "mexc",
    "Bybit": "bybit",
}

COINS = [
    "BTC", "ETH", "SOL", "XRP",
    "BNB", "DOGE", "USDC",
    "LTC", "XLM", "TRX", "ADA",
    "LINK", "AVAX", "BCH"
]

with st.expander("⚙️ Configurações", expanded=True):

    capital_brl = st.number_input(
        "Capital de referência (R$)",
        min_value=100.0,
        value=5000.0,
        step=100.0
    )

    capital_usdt = st.number_input(
        "Capital para simulações em USDT",
        min_value=10.0,
        value=1000.0,
        step=100.0
    )

    fee_buy = st.number_input(
        "Taxa de compra (%)",
        min_value=0.0,
        max_value=10.0,
        value=0.10,
        step=0.05
    )

    fee_sell = st.number_input(
        "Taxa de venda (%)",
        min_value=0.0,
        max_value=10.0,
        value=0.10,
        step=0.05
    )

    transfer_usdt = st.number_input(
        "Custo estimado de transferência (USDT)",
        min_value=0.0,
        value=1.0,
        step=0.1
    )

    minimum_profit_brl = st.number_input(
        "Lucro mínimo para USDT/BRL (R$)",
        min_value=0.0,
        value=20.0,
        step=5.0
    )

    selected_exchanges = st.multiselect(
        "Corretoras",
        list(EXCHANGES),
        default=["Foxbit", "Bitget"]
    )

    selected_coins = st.multiselect(
        "Criptomoedas",
        COINS,
        default=COINS
    )

    st.caption(
        "Para testar mais rapidamente, selecione "
        "apenas algumas moedas e corretoras."
    )


def simulate_book(levels, amount, is_buy):
    remaining = float(amount)
    received = 0.0

    for level in levels:
        price = float(level[0])
        volume = float(level[1])

        if price <= 0 or volume <= 0:
            continue

        if is_buy:
            used = min(remaining, price * volume)
            received += used / price
            remaining -= used
        else:
            used = min(remaining, volume)
            received += used * price
            remaining -= used

        if remaining <= 1e-8:
            break

    return received, remaining


@st.cache_data(ttl=40, show_spinner=False)
def fetch_exchange(name, symbols):

    exchange_id = EXCHANGES[name]

    try:
        cls = getattr(ccxt, exchange_id, None)

        if cls is None:
            return {}, "Integração indisponível"

        exchange = cls({
            "enableRateLimit": True,
            "timeout": 7000,
        })

        exchange.load_markets()

        quotes = {}
        errors = []

        for symbol in symbols:

            if symbol not in exchange.markets:
                errors.append(f"{symbol}: não listado")
                continue

            market = exchange.market(symbol)

            if market.get("spot") is False:
                errors.append(f"{symbol}: não é spot")
                continue

            if market.get("active") is False:
                errors.append(f"{symbol}: inativo")
                continue

            try:
                book = exchange.fetch_order_book(
                    symbol,
                    limit=20
                )

                asks = book.get("asks") or []
                bids = book.get("bids") or []

                if not asks or not bids:
                    errors.append(f"{symbol}: sem ofertas")
                    continue

                ask = float(asks[0][0])
                bid = float(bids[0][0])

                if ask <= 0 or bid <= 0:
                    errors.append(f"{symbol}: preço inválido")
                    continue

                quotes[symbol] = {
                    "ask": ask,
                    "bid": bid,
                    "asks": asks,
                    "bids": bids,
                }

            except Exception as exc:
                errors.append(
                    f"{symbol}: {type(exc).__name__}"
                )

        return quotes, "; ".join(errors[:8])

    except Exception as exc:
        return {}, (
            f"{type(exc).__name__}: {str(exc)[:100]}"
        )


if st.button("🔄 Atualizar cotações", type="primary"):
    fetch_exchange.clear()
    st.rerun()


symbols = ["USDT/BRL"]
symbols += [
    f"{coin}/USDT"
    for coin in selected_coins
]

symbols = list(dict.fromkeys(symbols))

all_quotes = {}
diagnostics = []

st.subheader("🌐 Diagnóstico das conexões")

if selected_exchanges:

    progress = st.progress(0)

    with ThreadPoolExecutor(
        max_workers=min(4, len(selected_exchanges))
    ) as executor:

        futures = {
            executor.submit(
                fetch_exchange,
                name,
                tuple(symbols)
            ): name
            for name in selected_exchanges
        }

        for index, future in enumerate(
            as_completed(futures), start=1
        ):

            name = futures[future]

            try:
                quotes, errors = future.result()
            except Exception as exc:
                quotes = {}
                errors = type(exc).__name__

            for symbol, data in quotes.items():
                all_quotes[(name, symbol)] = data

            diagnostics.append({
                "Corretora": name,
                "Pares OK": len(quotes),
                "Observações": errors or "Conectada"
            })

            progress.progress(
                index / len(selected_exchanges)
            )

else:
    st.info("Selecione pelo menos uma corretora.")

if diagnostics:
    st.dataframe(
        pd.DataFrame(diagnostics),
        hide_index=True,
        use_container_width=True
    )

st.metric(
    "Total de pares com cotações",
    len(all_quotes)
)


st.subheader("🇧🇷 Arbitragem direta USDT/BRL")

brl_results = []

for buyer in selected_exchanges:

    buy = all_quotes.get((buyer, "USDT/BRL"))

    if not buy:
        continue

    quantity, unspent = simulate_book(
        buy["asks"],
        capital_brl,
        True
    )

    if unspent > 0.01:
        continue

    quantity *= (1 - fee_buy / 100)
    quantity -= transfer_usdt

    if quantity <= 0:
        continue

    for seller in selected_exchanges:

        if seller == buyer:
            continue

        sell = all_quotes.get(
            (seller, "USDT/BRL")
        )

        if not sell:
            continue

        proceeds, unsold = simulate_book(
            sell["bids"],
            quantity,
            False
        )

        if unsold > 0.000001:
            continue

        final_brl = proceeds * (
            1 - fee_sell / 100
        )

        profit = final_brl - capital_brl

        brl_results.append({
            "Comprar": buyer,
            "Vender": seller,
            "Receber (R$)": round(final_brl, 2),
            "Lucro (R$)": round(profit, 2),
            "Retorno (%)": round(
                profit / capital_brl * 100, 3
            ),
        })


if brl_results:

    df_brl = pd.DataFrame(
        brl_results
    ).sort_values(
        "Lucro (R$)",
        ascending=False
    )

    best = df_brl.iloc[0]

    st.metric(
        "Melhor resultado em reais",
        f"R$ {best['Lucro (R$)']:.2f}"
    )

    st.dataframe(
        df_brl,
        hide_index=True,
        use_container_width=True
    )

    alerts = df_brl[
        df_brl["Lucro (R$)"] >= minimum_profit_brl
    ]

    if not alerts.empty:
        st.success(
            f"{len(alerts)} oportunidade(s) "
            "acima do lucro mínimo."
        )

else:
    st.info(
        "São necessárias duas corretoras com "
        "USDT/BRL e liquidez suficiente."
    )


st.subheader("🪙 Arbitragem de criptomoedas")

crypto_results = []

for coin in selected_coins:

    symbol = f"{coin}/USDT"

    for buyer in selected_exchanges:

        buy = all_quotes.get((buyer, symbol))

        if not buy:
            continue

        quantity, unspent = simulate_book(
            buy["asks"],
            capital_usdt,
            True
        )

        if unspent > 0.01:
            continue

        quantity *= (1 - fee_buy / 100)

        for seller in selected_exchanges:

            if seller == buyer:
                continue

            sell = all_quotes.get(
                (seller, symbol)
            )

            if not sell:
                continue

            proceeds, unsold = simulate_book(
                sell["bids"],
                quantity,
                False
            )

            if unsold > 0.000001:
                continue

            final_usdt = proceeds * (
                1 - fee_sell / 100
            )

            profit_usdt = (
                final_usdt - capital_usdt
            )

            crypto_results.append({
                "Moeda": coin,
                "Comprar": buyer,
                "Vender": seller,
                "Lucro bruto de transferência (USDT)": round(
                    profit_usdt, 4
                ),
                "Retorno (%)": round(
                    profit_usdt / capital_usdt * 100,
                    3
                ),
            })


if crypto_results:

    df_crypto = pd.DataFrame(
        crypto_results
    ).sort_values(
        "Lucro bruto de transferência (USDT)",
        ascending=False
    )

    st.dataframe(
        df_crypto,
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        "Esses resultados descontam as taxas "
        "de compra e venda configuradas, mas "
        "NÃO descontam a taxa de transferência "
        "da criptomoeda, nem a conversão final "
        "para reais."
    )

else:
    st.info(
        "Não foram encontradas comparações "
        "entre duas corretoras para as moedas "
        "selecionadas."
    )


st.caption(
    "Consulta UTC: " +
    datetime.now(timezone.utc).strftime(
        "%d/%m/%Y %H:%M:%S"
    )
)

st.error(
    "Os valores são simulações. "
    "Não há execução real, verificação de "
    "redes compatíveis, depósitos e saques, "
    "taxas reais de transferência, impostos "
    "ou garantia de execução. "
    "Alertas Telegram ainda não estão ativos."
)
