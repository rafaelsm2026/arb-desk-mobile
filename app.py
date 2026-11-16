
import streamlit as st
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import permutations

st.set_page_config(page_title="Arb Desk Mobile v0.5", page_icon="📈", layout="wide")
st.title("📈 Arb Desk Mobile v0.5")
st.caption("Scanner de preços spot • Simulação • Sem ordens reais")
st.warning("Apenas simulação. Diferenças indicativas NÃO são lucro realizado nem garantia de execução.")

EXCHANGES = ["Kraken", "Coinbase", "Bitget", "KuCoin", "MEXC", "Bybit"]
COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "USDC"]

with st.expander("⚙️ Configurações", expanded=True):
    capital = st.number_input("Capital hipotético (USDT)", min_value=10.0, value=1000.0, step=100.0)
    fee_pct = st.number_input("Taxa por lado (%) — estimativa", min_value=0.0, max_value=5.0, value=0.10, step=0.01)
    min_return = st.number_input("Retorno mínimo estimado (%)", min_value=0.0, max_value=100.0, value=0.30, step=0.05)
    exchanges = st.multiselect("Corretoras", EXCHANGES, default=EXCHANGES)
    coins = st.multiselect("Moedas (pares com USDT)", COINS, default=COINS)
    only_positive = st.checkbox("Exibir apenas oportunidades acima do filtro", value=True)
    st.caption("USDT é a moeda de cotação. O valor em reais não é convertido automaticamente. Taxas e capital são hipotéticos.")

@st.cache_data(ttl=20, show_spinner=False)
def fetch_quote(exchange, coin):
    symbol = coin + "USDT"
    headers = {"Accept": "application/json", "User-Agent": "ArbDeskMobile/0.5"}
    try:
        if exchange == "Kraken":
            pair = "XBTUSDT" if coin == "BTC" else symbol
            url = "https://api.kraken.com/0/public/Ticker"
            params = {"pair": pair}
        elif exchange == "Coinbase":
            url = f"https://api.exchange.coinbase.com/products/{coin}-USDT/ticker"
            params = None
        elif exchange == "Bitget":
            url = "https://api.bitget.com/api/v2/spot/market/tickers"
            params = {"symbol": symbol}
        elif exchange == "KuCoin":
            url = "https://api.kucoin.com/api/v1/market/orderbook/level1"
            params = {"symbol": f"{coin}-USDT"}
        elif exchange == "MEXC":
            url = "https://api.mexc.com/api/v3/ticker/bookTicker"
            params = {"symbol": symbol}
        elif exchange == "Bybit":
            url = "https://api.bybit.com/v5/market/tickers"
            params = {"category": "spot", "symbol": symbol}
        else:
            return None, "Corretora desconhecida"

        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code in (400, 404, 422):
            return None, f"Par indisponível ou requisição rejeitada (HTTP {response.status_code})"
        if response.status_code != 200:
            return None, f"Acesso/API HTTP {response.status_code}"
        try:
            data = response.json()
        except ValueError:
            return None, "Resposta não é JSON válido"

        if exchange == "Kraken":
            if data.get("error"):
                return None, "Par indisponível/API: " + str(data["error"])[:90]
            entries = data.get("result", {})
            if not entries:
                return None, "Par indisponível ou sem ofertas"
            ticker = next(iter(entries.values()))
            ask, bid = ticker["a"][0], ticker["b"][0]
        elif exchange == "Coinbase":
            if "ask" not in data or "bid" not in data:
                return None, "Par indisponível ou sem ofertas"
            ask, bid = data["ask"], data["bid"]
        elif exchange == "Bitget":
            if str(data.get("code")) != "00000":
                return None, "Par indisponível/API: " + str(data.get("msg", "erro"))[:90]
            entries = data.get("data") or []
            if not entries:
                return None, "Par indisponível ou sem ofertas"
            ask, bid = entries[0]["askPr"], entries[0]["bidPr"]
        elif exchange == "KuCoin":
            if str(data.get("code")) != "200000":
                return None, "Par indisponível/API: " + str(data.get("msg", "erro"))[:90]
            ticker = data.get("data") or {}
            ask, bid = ticker.get("bestAsk"), ticker.get("bestBid")
        elif exchange == "MEXC":
            if isinstance(data, dict) and ("askPrice" not in data or "bidPrice" not in data):
                return None, "Par indisponível/API: " + str(data.get("msg", "sem ofertas"))[:90]
            ask, bid = data["askPrice"], data["bidPrice"]
        else:
            if data.get("retCode") != 0:
                return None, "Par indisponível/API: " + str(data.get("retMsg", "erro"))[:90]
            entries = (data.get("result") or {}).get("list") or []
            if not entries:
                return None, "Par indisponível ou sem ofertas"
            ask, bid = entries[0]["ask1Price"], entries[0]["bid1Price"]

        ask, bid = float(ask), float(bid)
        if ask <= 0 or bid <= 0 or ask < bid:
            return None, "Ofertas ausentes ou inconsistentes"
        return {"ask": ask, "bid": bid}, "Conectada"
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError, StopIteration) as exc:
        return None, f"Erro de consulta: {type(exc).__name__}"

if st.button("🔄 Atualizar cotações"):
    fetch_quote.clear()
    st.rerun()

tasks = [(ex, coin) for ex in exchanges for coin in coins]
quotes, diagnostics = {}, []
if tasks:
    with st.spinner("Consultando ofertas públicas..."):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch_quote, ex, coin): (ex, coin) for ex, coin in tasks}
            for future in as_completed(futures):
                ex, coin = futures[future]
                try:
                    quote, status = future.result()
                except Exception as exc:
                    quote, status = None, f"Falha inesperada: {type(exc).__name__}"
                diagnostics.append({"Corretora": ex, "Moeda": coin, "Situação": status})
                if quote:
                    quotes[(ex, coin)] = quote
else:
    st.info("Selecione pelo menos uma moeda e uma corretora.")

st.subheader("🌐 Diagnóstico das conexões")
a, b = st.columns(2)
a.metric("Consultas OK", len(quotes))
b.metric("Consultas solicitadas", len(tasks))
if diagnostics:
    diagnostics.sort(key=lambda x: (EXCHANGES.index(x["Corretora"]), COINS.index(x["Moeda"])))
    with st.expander("Ver conexões e pares indisponíveis", expanded=len(quotes) != len(tasks)):
        st.dataframe(pd.DataFrame(diagnostics), hide_index=True, use_container_width=True)

results = []
for coin in coins:
    available = [ex for ex in exchanges if (ex, coin) in quotes]
    for buy_ex, sell_ex in permutations(available, 2):
        ask = quotes[(buy_ex, coin)]["ask"]
        bid = quotes[(sell_ex, coin)]["bid"]
        quantity = (capital / ask) * (1 - fee_pct / 100)
        proceeds = quantity * bid * (1 - fee_pct / 100)
        net = proceeds - capital
        ret = 100 * net / capital
        results.append({
            "Moeda": coin, "Comprar": buy_ex, "Vender": sell_ex,
            "Ask (USDT)": ask, "Bid (USDT)": bid,
            "Resultado estimado (USDT)": round(net, 4),
            "Retorno estimado (%)": round(ret, 4)
        })

st.subheader("📊 Comparações de arbitragem")
if results:
    df = pd.DataFrame(results).sort_values("Retorno estimado (%)", ascending=False)
    qualified = df[df["Retorno estimado (%)"] >= min_return]
    c1, c2 = st.columns(2)
    c1.metric("Acima do filtro", len(qualified))
    c2.metric("Melhor retorno estimado", f"{df.iloc[0]['Retorno estimado (%)']:.3f}%")
    shown = qualified if only_positive else df
    if shown.empty:
        st.info("Nenhuma comparação superou o filtro nesta consulta.")
    else:
        st.dataframe(shown, hide_index=True, use_container_width=True)
    with st.expander("Ver todas as comparações"):
        st.dataframe(df, hide_index=True, use_container_width=True)
else:
    st.info("É necessário obter ofertas válidas de duas corretoras para a mesma moeda.")

st.caption("Horário da consulta do painel (UTC): " + datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S"))
st.error("Atenção: cotações são consultadas em momentos diferentes; não há verificação de profundidade, quantidade disponível, taxas reais por corretora, slippage, latência, saldos, saque/depósito ou transferências. Não há execução automática, histórico persistente ou alertas Telegram nesta versão.")
