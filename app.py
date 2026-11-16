
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import ccxt
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Arb Desk Mobile v0.9", page_icon="💱", layout="wide")
st.title("💱 Arb Desk Mobile v0.9")
st.caption("USDT/BRL • Arbitragem entre corretoras • Simulação, sem ordens reais")
st.warning("Preços podem mudar durante a transferência. Um resultado estimado positivo não garante lucro.")

EXCHANGES = {
    "Foxbit": "foxbit", "Bitget": "bitget", "Mercado Bitcoin": "mercado",
    "Kraken": "kraken", "Coinbase": "coinbase", "KuCoin": "kucoin",
    "MEXC": "mexc", "Bybit": "bybit",
}

with st.expander("⚙️ Configurações", expanded=True):
    capital = st.number_input("Capital inicial (R$)", min_value=100.0, value=5000.0, step=100.0)
    buy_fee = st.number_input("Taxa de compra (%)", min_value=0.0, max_value=10.0, value=0.10, step=0.05)
    sell_fee = st.number_input("Taxa de venda (%)", min_value=0.0, max_value=10.0, value=0.10, step=0.05)
    network_fee = st.number_input("Taxa de envio (USDT)", min_value=0.0, value=1.0, step=0.1)
    withdrawal_fee = st.number_input("Custo adicional de retirada (R$)", min_value=0.0, value=0.0, step=1.0)
    minimum_profit = st.number_input("Alerta a partir de lucro estimado (R$)", min_value=0.0, value=20.0, step=5.0)
    selected = st.multiselect("Corretoras", list(EXCHANGES), default=["Foxbit", "Bitget", "Mercado Bitcoin"])
    show_losses = st.checkbox("Mostrar também operações com prejuízo", value=True)


def simulate_book(levels, amount, is_buy):
    remaining = float(amount)
    received = 0.0
    for level in levels:
        price, volume = float(level[0]), float(level[1])
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


@st.cache_data(ttl=30, show_spinner=False)
def fetch_market(name):
    try:
        cls = getattr(ccxt, EXCHANGES[name], None)
        if cls is None:
            return None, "Integração CCXT não disponível"
        ex = cls({"enableRateLimit": True, "timeout": 7000})
        ex.load_markets()
        symbol = "USDT/BRL"
        if symbol not in ex.markets:
            return None, "USDT/BRL não listado"
        market = ex.market(symbol)
        if market.get("spot") is False or market.get("active") is False:
            return None, "Mercado spot inativo ou indisponível"
        book = ex.fetch_order_book(symbol, limit=20)
        asks, bids = book.get("asks") or [], book.get("bids") or []
        if not asks or not bids:
            return None, "Livro de ofertas vazio"
        ask, bid = float(asks[0][0]), float(bids[0][0])
        if ask <= 0 or bid <= 0:
            return None, "Preços inválidos"
        return {"ask": ask, "bid": bid, "asks": asks, "bids": bids}, "Conectada"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:105]}"


def telegram_config():
    try:
        return st.secrets.get("TELEGRAM_BOT_TOKEN", ""), st.secrets.get("TELEGRAM_CHAT_ID", "")
    except Exception:
        return "", ""


def send_telegram(message):
    token, chat_id = telegram_config()
    if not token or not chat_id:
        return False, "Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nos Secrets do Streamlit."
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": str(chat_id), "text": message}, timeout=8,
        )
        response.raise_for_status()
        return True, "Mensagem enviada."
    except requests.RequestException as exc:
        return False, f"Falha no Telegram: {type(exc).__name__}"


if st.button("🔄 Consultar preços agora", type="primary"):
    fetch_market.clear()
    st.rerun()

st.subheader("🌐 Diagnóstico das conexões")
quotes, diagnostics = {}, []
if selected:
    progress = st.progress(0)
    with ThreadPoolExecutor(max_workers=min(4, len(selected))) as pool:
        futures = {pool.submit(fetch_market, name): name for name in selected}
        for count, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            try:
                data, status = future.result()
            except Exception as exc:
                data, status = None, type(exc).__name__
            diagnostics.append({"Corretora": name, "Situação": status})
            if data:
                quotes[name] = data
            progress.progress(count / len(selected))
else:
    st.info("Selecione pelo menos uma corretora.")

left, right = st.columns(2)
left.metric("Conectadas", len(quotes))
right.metric("Selecionadas", len(selected))
if diagnostics:
    st.dataframe(pd.DataFrame(diagnostics), hide_index=True, use_container_width=True)

st.subheader("💵 Preços USDT/BRL")
if quotes:
    st.dataframe(pd.DataFrame([
        {"Corretora": name, "Comprar (R$)": q["ask"], "Vender (R$)": q["bid"]}
        for name, q in quotes.items()
    ]), hide_index=True, use_container_width=True)
else:
    st.info("Nenhum livro USDT/BRL disponível nesta consulta.")

results = []
for buyer, b in quotes.items():
    quantity, unspent = simulate_book(b["asks"], capital, True)
    if unspent > 0.01:
        continue
    sent = quantity * (1 - buy_fee / 100) - network_fee
    if sent <= 0:
        continue
    for seller, s in quotes.items():
        if buyer == seller:
            continue
        proceeds, unsold = simulate_book(s["bids"], sent, False)
        if unsold > 1e-6:
            continue
        net_brl = proceeds * (1 - sell_fee / 100) - withdrawal_fee
        profit = net_brl - capital
        results.append({
            "Comprar": buyer, "Vender": seller,
            "Preço compra": b["ask"], "Preço venda": s["bid"],
            "USDT enviado": round(sent, 4), "Receber BRL": round(net_brl, 2),
            "Lucro estimado": round(profit, 2), "Retorno (%)": round(100 * profit / capital, 3),
        })

st.subheader("📊 Comprar → Transferir → Vender")
if results:
    df = pd.DataFrame(results).sort_values("Lucro estimado", ascending=False)
    best = df.iloc[0]
    st.metric("Melhor resultado estimado", f"R$ {best['Lucro estimado']:.2f}")
    st.write(f"**Comprar:** {best['Comprar']}  |  **Vender:** {best['Vender']}")
    st.write(f"**Preço de compra:** R$ {best['Preço compra']:.4f}  |  **Preço de venda:** R$ {best['Preço venda']:.4f}")
    st.write(f"**USDT após taxas de compra e envio:** {best['USDT enviado']:.4f}")
    st.write(f"**Recebimento final estimado:** R$ {best['Receber BRL']:.2f}")
    visible = df if show_losses else df[df["Lucro estimado"] >= 0]
    if not visible.empty:
        st.dataframe(visible, hide_index=True, use_container_width=True)
    eligible = df[df["Lucro estimado"] >= minimum_profit]
    if not eligible.empty:
        st.success(f"{len(eligible)} comparação(ões) acima do lucro mínimo de R$ {minimum_profit:.2f}.")
        alert = eligible.iloc[0]
        message = (
            "ARB DESK — ALERTA SIMULADO\n"
            f"Comprar USDT: {alert['Comprar']}\n"
            f"Vender USDT: {alert['Vender']}\n"
            f"Capital: R$ {capital:.2f}\n"
            f"Lucro líquido estimado: R$ {alert['Lucro estimado']:.2f}\n"
            "Não é ordem de negociação. Verifique rede, saques, depósitos e preços."
        )
        if st.button("📨 Enviar melhor oportunidade ao Telegram"):
            ok, info = send_telegram(message)
            (st.success if ok else st.error)(info)
    else:
        st.info("Nenhuma oportunidade atingiu o lucro mínimo nesta consulta.")
else:
    st.info("São necessárias pelo menos duas corretoras com USDT/BRL e liquidez suficiente.")

st.caption("Horário UTC: " + datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S"))
st.error(
    "Limitações: taxas de negociação e rede são estimativas configuradas pelo usuário; "
    "não há verificação de depósitos/saques, compatibilidade de redes, transferências, "
    "slippage durante o envio, tributos ou execução real. "
    "O Telegram só envia mensagens quando o botão é pressionado; "
    "não há monitoramento contínuo em segundo plano."
)
