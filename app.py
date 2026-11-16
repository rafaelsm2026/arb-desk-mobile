import streamlit as st
import pandas as pd
import ccxt
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

st.set_page_config(page_title='Arb Desk Mobile v1.1', page_icon='💱', layout='wide')
st.title('💱 Arb Desk Mobile v1.1')
st.caption('Monitoramento de arbitragem spot • Apenas simulação')
st.warning('Resultados indicativos, não são ordens nem lucros garantidos. Transferências podem atrasar e os preços podem mudar.')

EXCHANGES = {'Foxbit':'foxbit','Bitget':'bitget','Mercado Bitcoin':'mercado','Kraken':'kraken','Coinbase':'coinbase','KuCoin':'kucoin','MEXC':'mexc','Bybit':'bybit'}
COINS = ['BTC','ETH','SOL','XRP','BNB','DOGE','USDC','LTC','XLM','TRX','ADA','LINK','AVAX','BCH']
DEFAULT_TRANSFER = {coin: 0.0 for coin in COINS}

with st.expander('⚙️ Configurações', expanded=True):
    capital_brl = st.number_input('Capital para USDT/BRL (R$)', min_value=100.0, value=5000.0, step=100.0)
    capital_usdt = st.number_input('Capital para outras moedas (USDT)', min_value=10.0, value=1000.0, step=100.0)
    fee_buy = st.number_input('Taxa de compra (%)', min_value=0.0, max_value=10.0, value=0.10, step=0.05)
    fee_sell = st.number_input('Taxa de venda (%)', min_value=0.0, max_value=10.0, value=0.10, step=0.05)
    fee_usdt = st.number_input('Transferência de USDT (USDT)', min_value=0.0, value=1.0, step=0.1)
    fee_brl = st.number_input('Outros custos em reais (R$)', min_value=0.0, value=0.0, step=1.0)
    min_brl = st.number_input('Lucro mínimo USDT/BRL (R$)', min_value=0.0, value=20.0, step=5.0)
    min_usdt = st.number_input('Lucro mínimo em criptomoedas (USDT)', min_value=0.0, value=4.0, step=1.0)
    exchanges = st.multiselect('Corretoras', list(EXCHANGES), default=['Foxbit','Bitget','Mercado Bitcoin','Kraken','Coinbase','KuCoin','MEXC','Bybit'])
    coins = st.multiselect('Criptomoedas', COINS, default=COINS)
    show_all = st.checkbox('Mostrar também operações abaixo do filtro', value=False)

with st.expander('🚚 Taxas de envio por criptomoeda (quantidade da moeda)', expanded=False):
    st.caption('Preencha a taxa de retirada da corretora de origem para cada moeda. Os valores iniciais são ZERO apenas para teste e NÃO significam transferência gratuita. Sem confirmar a taxa e a rede, nenhuma oportunidade está validada.')
    transfer_fees = {}
    for coin in coins:
        transfer_fees[coin] = st.number_input(f'Taxa de envio {coin} ({coin})', min_value=0.0, value=DEFAULT_TRANSFER[coin], format='%.8f', key=f'transfer_{coin}')


def book_execute(levels, amount, buy):
    remaining, received = float(amount), 0.0
    for level in levels:
        price, qty = float(level[0]), float(level[1])
        if price <= 0 or qty <= 0:
            continue
        if buy:
            used = min(remaining, price * qty)
            received += used / price
        else:
            used = min(remaining, qty)
            received += used * price
        remaining -= used
        if remaining <= 1e-8:
            break
    return received, remaining


@st.cache_data(ttl=45, show_spinner=False)
def fetch_exchange(name, symbols):
    try:
        cls = getattr(ccxt, EXCHANGES[name], None)
        if cls is None:
            return {}, 'Integração indisponível no CCXT'
        ex = cls({'enableRateLimit': True, 'timeout': 6500})
        ex.load_markets()
        quotes, problems = {}, []
        for symbol in symbols:
            market = ex.markets.get(symbol)
            if not market:
                continue
            if market.get('spot') is False or market.get('active') is False:
                continue
            try:
                book = ex.fetch_order_book(symbol, limit=20)
                asks, bids = book.get('asks') or [], book.get('bids') or []
                if not asks or not bids:
                    continue
                if float(asks[0][0]) <= 0 or float(bids[0][0]) <= 0:
                    continue
                quotes[symbol] = {'asks': asks, 'bids': bids, 'ask': float(asks[0][0]), 'bid': float(bids[0][0])}
            except Exception as exc:
                problems.append(f'{symbol}: {type(exc).__name__}')
        return quotes, '; '.join(problems[:4]) or 'Consulta concluída'
    except Exception as exc:
        return {}, f'{type(exc).__name__}: {str(exc)[:100]}'


if st.button('🔄 Atualizar cotações', type='primary'):
    fetch_exchange.clear()
    st.rerun()

symbols = tuple(['USDT/BRL'] + [f'{coin}/USDT' for coin in coins])
quotes, diagnostics = {}, []
st.subheader('🌐 Diagnóstico das conexões')
if exchanges:
    progress = st.progress(0)
    with ThreadPoolExecutor(max_workers=min(4, len(exchanges))) as pool:
        futures = {pool.submit(fetch_exchange, name, symbols): name for name in exchanges}
        for i, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            try:
                data, status = future.result()
            except Exception as exc:
                data, status = {}, type(exc).__name__
            for symbol, q in data.items():
                quotes[(name, symbol)] = q
            diagnostics.append({'Corretora': name, 'Pares OK': len(data), 'Situação': status})
            progress.progress(i / len(exchanges))
else:
    st.info('Selecione pelo menos uma corretora.')
if diagnostics:
    st.dataframe(pd.DataFrame(diagnostics), hide_index=True, use_container_width=True)
st.metric('Pares consultados com sucesso', len(quotes))

st.subheader('🇧🇷 USDT/BRL — comprar, transferir e vender')
brl_rows = []
for buyer in exchanges:
    b = quotes.get((buyer, 'USDT/BRL'))
    if not b:
        continue
    qty, unspent = book_execute(b['asks'], capital_brl, True)
    if unspent > 0.01:
        continue
    sent = qty * (1 - fee_buy / 100) - fee_usdt
    if sent <= 0:
        continue
    for seller in exchanges:
        if seller == buyer:
            continue
        s = quotes.get((seller, 'USDT/BRL'))
        if not s:
            continue
        proceeds, unsold = book_execute(s['bids'], sent, False)
        if unsold > 1e-6:
            continue
        final = proceeds * (1 - fee_sell / 100) - fee_brl
        profit = final - capital_brl
        brl_rows.append({'Comprar': buyer, 'Vender': seller, 'USDT enviado': round(sent, 5), 'Receber (R$)': round(final, 2), 'Lucro estimado (R$)': round(profit, 2), 'Retorno (%)': round(100 * profit / capital_brl, 3)})
if brl_rows:
    brl_df = pd.DataFrame(brl_rows).sort_values('Lucro estimado (R$)', ascending=False)
    best = brl_df.iloc[0]
    st.metric('Melhor resultado estimado em reais', f"R$ {best['Lucro estimado (R$)']:.2f}")
    shown = brl_df if show_all else brl_df[brl_df['Lucro estimado (R$)'] >= min_brl]
    if shown.empty:
        st.info('Nenhuma operação USDT/BRL atingiu o lucro mínimo.')
    else:
        st.dataframe(shown, hide_index=True, use_container_width=True)
else:
    st.info('Não há duas corretoras com livros USDT/BRL e liquidez suficiente.')

st.subheader('🪙 Outras moedas — resultado estimado em USDT')
crypto_rows = []
for coin in coins:
    symbol = f'{coin}/USDT'
    for buyer in exchanges:
        b = quotes.get((buyer, symbol))
        if not b:
            continue
        qty, unspent = book_execute(b['asks'], capital_usdt, True)
        if unspent > 0.01:
            continue
        sent = qty * (1 - fee_buy / 100) - transfer_fees[coin]
        if sent <= 0:
            continue
        for seller in exchanges:
            if seller == buyer:
                continue
            s = quotes.get((seller, symbol))
            if not s:
                continue
            proceeds, unsold = book_execute(s['bids'], sent, False)
            if unsold > 1e-6:
                continue
            final = proceeds * (1 - fee_sell / 100)
            profit = final - capital_usdt
            crypto_rows.append({'Moeda': coin, 'Comprar': buyer, 'Vender': seller, 'Taxa envio (moeda)': transfer_fees[coin], 'Lucro estimado (USDT)': round(profit, 4), 'Retorno (%)': round(100 * profit / capital_usdt, 3)})
if crypto_rows:
    crypto_df = pd.DataFrame(crypto_rows).sort_values('Lucro estimado (USDT)', ascending=False)
    shown = crypto_df if show_all else crypto_df[crypto_df['Lucro estimado (USDT)'] >= min_usdt]
    if shown.empty:
        st.info('Nenhuma comparação superou o filtro em USDT.')
    else:
        st.dataframe(shown, hide_index=True, use_container_width=True)
else:
    st.info('Sem comparações válidas entre corretoras para as moedas selecionadas.')

st.caption('Consulta UTC: ' + datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S'))
st.error('ATENÇÃO: taxas de envio por moeda começam em zero e precisam ser verificadas por corretora/rede. O sistema NÃO valida depósitos/saques, redes, saldos, tempos de transferência, taxas reais, impostos ou execução futura. Os valores em USDT NÃO são lucro líquido convertido para reais. Não há ordens reais nem alertas automáticos.')
