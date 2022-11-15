from brownie import (
    Contract, network, accounts, TestMintRouter,
    OverlayV1UniswapV3Factory, OverlayV1Factory, OverlayV1UniswapV3Feed,
    OverlayV1Market, OverlayV1State, chain, web3
)
import json
import os
from pathlib import Path
from math import ceil
import pandas as pd


def json_load(name):
    f = open(f'scripts/constants/{name}.json')
    return json.load(f)


def clear_contracts_file():
    path = 'scripts/constants/overlay_contracts.json'
    file = Path(path)
    if file.exists():
        os.remove('scripts/constants/overlay_contracts.json')


def to_dict(name, address, abi):
    new_dict = {"address": address, "abi": abi}
    path = 'scripts/constants/overlay_contracts.json'
    file = Path(path)
    if not file.exists():
        with open(path, 'w+') as f:
            d = {}
            d[name] = new_dict
            json.dump(d, f)
            f.flush()
            os.fsync(f.fileno())
    else:
        with open(path) as f:
            full_dict = json.load(f)
            full_dict[name] = new_dict
        with open(path, 'w') as f:
            json.dump(full_dict, f)
            f.flush()
            os.fsync(f.fileno())


def lp(acc, pool, ovl, usdc, mint_router, amount, appr_reqd):

    if appr_reqd:
        ovl.approve(mint_router, ovl.balanceOf(acc), {'from': acc})
        usdc.approve(mint_router, usdc.balanceOf(acc), {'from': acc})

    mint_router.mint(pool.address, -887220, 887220, amount, {"from": acc})


def swap(acc, pool, mint_router, usdc_to_ovl, amount):
    tx = mint_router.swap(pool, usdc_to_ovl, amount, {'from': acc})
    vals = tx.return_value
    if tx.events['Swap']['amount0'] > 0:
        return tx.events['Swap']['amount0']
    else:
        return tx.events['Swap']['amount1']


def contract_obj(source, name):
    return Contract.from_abi(name,
                             source[name]['address'],
                             source[name]['abi'])


def approve_spending(token, amount, spender, acc):
    token.approve(spender, amount, {'from': acc})


def build_overlay_pos(market, ovl, col, is_long, acc):
    fee = ceil((col * market.params(11))/1e18)
    approve_spending(ovl, ceil((col + fee)/1e18) * 1e18, market, acc)
    if is_long:
        price = (2**256)-1
    else:
        price = 0
    tx = market.build(col, 1e18, is_long, price, {'from': acc})
    return tx.events['Build']['positionId']


def main():
    print('Network: ', network.show_active())
    clear_contracts_file()

    # Get addresses
    gov_overlay = accounts[0]
    alice = accounts[1]

    # Get mainnet contract details
    m_contracts = json_load('mainnet_contracts')
    us_contracts = json_load('uniswap_setup_contracts')

    # Get contract objects
    uni_factory = contract_obj(m_contracts, 'uni_factory')
    ovl = contract_obj(us_contracts, 'OVL')
    usdc = contract_obj(us_contracts, 'USDC')
    pool = contract_obj(us_contracts, 'inv_pool')

    # Provide liquidity on spot pool
    mint_router = alice.deploy(TestMintRouter)
    to_dict('mint_router', mint_router.address, mint_router.abi)
    o_contracts = json_load('overlay_contracts')
    mint_router = contract_obj(o_contracts, 'mint_router')

    # Add liquidity
    liquidity = 3_000_000 * 1e18
    lp(alice, pool, ovl, usdc, mint_router, liquidity, True)
    # Small init swap
    swap_amount = 1e12
    swap(alice, pool, mint_router, False, swap_amount)
    # Mine 2x the duration of longer TWAP
    chain.mine(timedelta=7210)

    # Deploy Overlay Feed Factory, Feed, Factory
    feed_factory = gov_overlay.deploy(OverlayV1UniswapV3Factory, ovl,
                                      uni_factory, 600, 3600, 600, 12)
    to_dict('feed_factory', feed_factory.address, feed_factory.abi)

    market_base_token = usdc
    market_quote_token = ovl
    ovlX_base_token = ovl
    ovlX_quote_token = usdc
    market_fee = 3000
    market_base_amount = 1000000000000000000  # 1e18
    tx = feed_factory.deployFeed(market_base_token, market_quote_token,
                                 market_fee, market_base_amount,
                                 ovlX_base_token, ovlX_quote_token,
                                 market_fee)
    feed_addr = tx.events['FeedDeployed']['feed']
    feed = OverlayV1UniswapV3Feed.at(feed_addr)
    to_dict('feed', feed.address, feed.abi)

    factory = gov_overlay.deploy(OverlayV1Factory, ovl, gov_overlay)
    to_dict('factory', factory.address, factory.abi)

    # Deploy Overlay inverse market
    ovl.grantRole(ovl.DEFAULT_ADMIN_ROLE(), factory, {'from': gov_overlay})
    governor_role = web3.solidityKeccak(['string'], ["GOVERNOR"])
    ovl.grantRole(governor_role, gov_overlay, {"from": gov_overlay})
    guardian_role = web3.solidityKeccak(['string'], ["GOVERNOR"])
    ovl.grantRole(guardian_role, gov_overlay, {"from": gov_overlay})

    factory.addFeedFactory(feed_factory, {'from': gov_overlay})
    params = (
        122000000000,  # k
        500000000000000000,  # lmbda
        2500000000000000,  # delta
        5000000000000000000,  # capPayoff
        800000000000000000000000,  # capNotional
        1000000000000000000,  # capLeverage
        2592000,  # circuitBreakerWindow
        66670000000000000000000,  # circuitBreakerMintTarget
        100000000000000000,  # maintenanceMargin
        100000000000000000,  # maintenanceMarginBurnRate
        50000000000000000,  # liquidationFeeRate
        750000000000000,  # tradingFeeRate
        100000000000000,  # minCollateral
        25000000000000,  # priceDriftUpperLimit
        12,  # averageBlockTime
    )
    tx = factory.deployMarket(feed_factory, feed, params,
                              {'from': gov_overlay})
    market = OverlayV1Market.at(tx.events['MarketDeployed']['market'])
    to_dict('market', market.address, market.abi)

    # Deploy state contract
    state = gov_overlay.deploy(OverlayV1State, factory)
    to_dict('state', state.address, state.abi)

    # Simulate attack
    # Open short on inverse market
    df = pd.DataFrame(columns=['ovl_amount',
                               'usdc_amount',
                               'seconds'])
    chain.snapshot()
    for ovl_in in range(50_000, 300_000, 50_000):
        for usdc_in in range(100_000, 1_000_000, 100_000):

            pos_id = build_overlay_pos(market, ovl, ovl_in*1e18, False, alice)

            # Swap ETH to OVL to pump spot OVL price
            ovl_uni = swap(alice, pool, mint_router, True, usdc_in*1e18)

            # Wait for TWAP to catch up
            for i in range(12, 7200, 12):
                o_contracts = json_load('overlay_contracts')
                state = contract_obj(o_contracts, 'state')
                curr_val =\
                    (state.value(market, alice, pos_id)/1e18
                        + state.tradingFee(market, alice, pos_id)/1e18)
                print(f'Input USDC: {usdc_in}')
                print(f'Input OVL: {ovl_in}')
                print(f'Current Value: {curr_val}')
                print(f'Price: {(pool.slot0()[0]**2)/(2**(96*2))}')
                print(f'Inverse price: {1/((pool.slot0()[0]**2)/(2**(96*2)))}')
                print(f'Time: {i} secs')
                if curr_val >= ovl_in:
                    # tx = market.unwind(pos_id, 1e18,
                    #                    (2**256)-1, {"from": alice})
                    df.loc[len(df)] = [ovl_in, usdc_in, i]
                    print('Exit loop!')
                    break
                    # ovl_ovl = tx.events['Transfer'][1]['value']/1e18
                    # usdc_out = swap(alice, pool, mint_router, False, ovl_ovl)
                else:
                    chain.mine(timedelta=i)  # 12 secs per block on ETH2.0
            chain.revert()
    asdf



            


    # Unwind long and swap out OVL for ETH