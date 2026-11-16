
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import ccxt

st.set_page_config(page_title='Arb Desk Mobile v0.7', page_icon='💱', layout='wide')
st.title('💱 Arb Desk Mobile v0.7')
st.caption('Monitor de arbitragem USDT → BRL | Somente simulação | Sem ordens reais')
st.warning('As oportunidades são indicativas. A transferência entre corretoras pode demorar e alterar completamente o resultado.')

EXCHANGES = {
    'Kraken': 'kraken', 'Coinbase': 'coinbase', 'Bitget': 'bitget',
    'KuCoin': 'kucoin', 'MEXC': 'mexc', 'Bybit': 'bybit',
    'Mercado Bitcoin': 'mercado', 'Foxbit': 'foxbit',
}
ASSETS = ['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'USDC']

with st.expander('⚙️ Configurações', expanded=True):
    capital_brl = st.number_input('Capital inicial (R$)', min_value=100.0, value=5000.0, step=100.0)
    fee_buy = st.number_input('Taxa de compra (%)', min_value=0.0, max_value=10.0, value=0.1, step=0.05)
    fee_sell = st.number_input('Taxa de venda (%)', min_value=0.0, max_value=10.0, value=0.1, step=0.05)
    transfer_fee_usdt = st.number_input('Taxa de transferência (USDT)', min_value=0.0, value=1.0, step=0.1)
    withdrawal_brl = st.number_input('Custo de retirada em reais (R$)', min_value=0.0, value=0.0, step=1.0)
    min_profit = st.number_input('Lucro mínimo para exibir (R$)', min_value=0.0, value=10.0, step=5.0)
    selected = st.multiselect('Corretoras', list(EXCHANGES), default=list(EXCHANGES))
    other_assets = st.multiselect('Outras moedas para diagnóstico (pares com USDT)', ASSETS, default=ASSETS)
    show_all = st.checkbox('Mostrar operações mesmo sem lucro', value=False)

st.info('O cálculo direto USDT/BRL exige ofertas reais em BRL nas duas corretoras. Pares USDT/USDC não são convertidos automaticamente para BRL.')

@st.cache_data(ttl=45, show_spinner=False)
def load_exchange(name):
    ex_id = EXCHANGES[name]
    cls = getattr(ccxt, ex_id, None)
    if cls is None:
        return None, f'Integração {ex_id} não disponível nesta versão do CCXT'
    try:
        ex = cls({'enableRateLimit': True, 'timeout': 12000})
        markets = ex.load_markets()
        return sorted(markets.keys()), ''
    except Exception as exc:
        return None, f'{type(exc).__name__}: {str(exc)[:100]}'

@st.cache_data(ttl=20, show_spinner=False)
def quote(name, symbol):
    cls = getattr(ccxt, EXCHANGES[name], None)
    if cls is None:
        return None, 'Integração indisponível'
    try:
        ex = cls({'enableRateLimit': True, 'timeout': 12000})
        ex.load_markets()
        if symbol not in ex.markets:
            return None, 'Par não listado'
        market = ex.market(symbol)
        if not market.get('spot', False) or market.get('active') is False:
            return None, 'Par não está ativo no mercado spot'
        book = ex.fetch_order_book(symbol, limit=20)
        asks = book.get('asks') or []
        bids = book.get('bids') or []
        if not asks or not bids:
            return None, 'Livro sem ofertas de compra/venda'
        ask, bid = float(asks[0][0]), float(bids[0][0])
        if ask <= 0 or bid <= 0:
            return None, 'Ofertas inválidas'
        return {'ask': ask, 'bid': bid, 'asks': asks, 'bids': bids}, 'Conectada'
    except Exception as exc:
        return None, f'{type(exc).__name__}: {str(exc)[:100]}'

def execute_book(levels, amount, spend_quote):
    """Simula execução no livro. spend_quote=True: compra gastando quote; False: vende base."""
    remaining = float(amount)
    received = 0.0
    for price, qty, *_ in levels:
        price, qty = float(price), float(qty)
        if price <= 0 or qty <= 0:
            continue
        if spend_quote:
            spend = min(remaining, price * qty)
            received += spend / price
            remaining -= spend
        else:
            sold = min(remaining, qty)
            received += sold * price
            remaining -= sold
        if remaining <= 1e-8:
            break
    return received, remaining

if st.button('🔄 Atualizar cotações', type='primary'):
    quote.clear()
    load_exchange.clear()
    st.rerun()

symbols = ['USDT/BRL', 'USDT/USDC'] + [f'{a}/USDT' for a in other_assets]
tasks = [(name, symbol) for name in selected for symbol in symbols]
quotes, statuses = {}, []
if tasks:
    with st.spinner('Consultando livros de ofertas públicos...'):
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(quote, name, symbol): (name, symbol) for name, symbol in tasks}
            for future in as_completed(futures):
                name, symbol = futures[future]
                try:
                    q, status = future.result()
                except Exception as exc:
                    q, status = None, f'Erro inesperado: {type(exc).__name__}'
                statuses.append({'Corretora': name, 'Par': symbol, 'Situação': status})
                if q:
                    quotes[(name, symbol)] = q

st.subheader('🌐 Diagnóstico das conexões')
a, b = st.columns(2)
a.metric('Consultas OK', len(quotes))
b.metric('Consultas solicitadas', len(tasks))
with st.expander('Ver conexões e pares indisponíveis'):
    if statuses:
        st.dataframe(pd.DataFrame(statuses).sort_values(['Corretora', 'Par']), hide_index=True, use_container_width=True)

st.subheader('🇧🇷 Arbitragem USDT → BRL')
st.caption('Compra com BRL na corretora A, transferência hipotética de USDT e venda em BRL na corretora B.')
results = []
for buy_name in selected:
    buy = quotes.get((buy_name, 'USDT/BRL'))
    if not buy:
        continue
    # Compra usando capital em reais; verifica profundidade das ofertas
    qty, brl_unspent = execute_book(buy['asks'], capital_brl, True)
    if brl_unspent > 0.01:
        continue
    qty_after_buy = qty * (1 - fee_buy / 100)
    qty_after_transfer = qty_after_buy - transfer_fee_usdt
    if qty_after_transfer <= 0:
        continue
    for sell_name in selected:
        if sell_name == buy_name:
            continue
        sell = quotes.get((sell_name, 'USDT/BRL'))
        if not sell:
            continue
        proceeds, unsold = execute_book(sell['bids'], qty_after_transfer, False)
        if unsold > 0.000001:
            continue
        final_brl = proceeds * (1 - fee_sell / 100) - withdrawal_brl
        profit = final_brl - capital_brl
        results.append({
            'Comprar': buy_name, 'Vender': sell_name,
            'Ask inicial (R$)': buy['ask'], 'Bid inicial (R$)': sell['bid'],
            'USDT após transferência': round(qty_after_transfer, 5),
            'Receber (R$)': round(final_brl, 2),
            'Lucro líquido estimado (R$)': round(profit, 2),
            'Retorno (%)': round(100 * profit / capital_brl, 3),
        })

if results:
    df = pd.DataFrame(results).sort_values('Lucro líquido estimado (R$)', ascending=False)
    best = df.iloc[0]
    x, y = st.columns(2)
    x.metric('Melhor lucro estimado', f"R$ {best['Lucro líquido estimado (R$)']:.2f}")
    y.metric('Melhor retorno estimado', f"{best['Retorno (%)']:.2f}%")
    shown = df if show_all else df[df['Lucro líquido estimado (R$)'] >= min_profit]
    if shown.empty:
        st.info('Nenhuma operação atende ao lucro mínimo informado.')
    else:
        st.dataframe(shown, hide_index=True, use_container_width=True)
else:
    st.info('Sem comparações diretas disponíveis: é necessário USDT/BRL com livro válido em pelo menos duas corretoras diferentes e liquidez suficiente para o capital escolhido.')

st.subheader('💵 Referência USDT/USDC')
reference = []
for name in selected:
    q = quotes.get((name, 'USDT/USDC'))
    if q:
        reference.append({'Corretora': name, 'Comprar USDT (USDC)': q['ask'], 'Vender USDT (USDC)': q['bid']})
if reference:
    st.dataframe(pd.DataFrame(reference), hide_index=True, use_container_width=True)
else:
    st.caption('Nenhum par USDT/USDC disponível nas consultas atuais.')

st.caption('Atualizado em UTC: ' + datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S'))
st.error('Não executa ordens, depósitos ou saques. Não verifica rede de transferência, depósitos habilitados, tempo de confirmação, taxas reais por usuário, tributação nem mudanças de preço durante o envio. Não há alertas Telegram ativos nesta versão.')
