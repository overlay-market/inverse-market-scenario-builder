from brownie import (
    Contract, network, accounts, TestMintRouter,
    OverlayV1UniswapV3Factory, OverlayV1Factory, OverlayV1UniswapV3Feed,
    OverlayV1Market, chain
)
from web3 import Web3
import json
import os
from pathlib import Path


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
    if ~file.exists():
        with open(path, 'w') as f:
            d = {}
            d[name] = new_dict
            json.dump(d, f)
    else:
        with open(path) as f:
            full_dict = json.load(f)
            full_dict[name] = new_dict
        with open(path, 'w') as f:
            json.dump(full_dict, f)


def lp(acc, pool, ovl, usdc, mint_router, amount, appr_reqd):

    if appr_reqd:
        ovl.approve(mint_router, ovl.balanceOf(acc), {'from': acc})
        usdc.approve(mint_router, usdc.balanceOf(acc), {'from': acc})

    mint_router.mint(pool.address, -887220, 887220, amount, {"from": acc})


def swap(acc, pool, mint_router, ovl_to_usdc, amount):
    mint_router.swap(pool, ovl_to_usdc, amount, {'from': acc})


def contract_obj(source, name):
    return Contract.from_abi(name,
                             source[name]['address'],
                             source[name]['abi'])


def main():
    print('Network: ', network.show_active())
    clear_contracts_file()

    # Get addresses
    gov_overlay = accounts[0]
    alice = accounts[1]

    # Get mainnet contract details
    m_contracts = json_load('mainnet_contracts')
    contracts = json_load('uniswap_setup_contracts')

    # Get contract objects
    uni_factory = contract_obj(m_contracts, 'uni_factory')
    ovl = contract_obj(contracts, 'OVL')
    usdc = contract_obj(contracts, 'USDC')
    pool = contract_obj(contracts, 'inv_pool')

    # Provide liquidity on spot pool
    mint_router = alice.deploy(TestMintRouter)
    liquidity = 1e17
    lp(alice, pool, ovl, usdc, mint_router, liquidity, True)
    swap_amount = 1e16
    swap(alice, pool, mint_router, False, swap_amount)
    chain.mine(timedelta=7210)  # Mine 2x the duration of longer TWAP

    # Deploy Overlay Feed Factory, Feed, Factory
    feed_factory = gov_overlay.deploy(OverlayV1UniswapV3Factory, ovl,
                                      uni_factory, 600, 3600, 600, 12)
    to_dict('feed_factory', feed_factory.address, feed_factory.abi)

    market_base_token = ovl
    market_quote_token = usdc
    ovlX_base_token = usdc
    ovlX_quote_token = ovl
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
    governor_role = Web3.solidityKeccak(['string'], ["GOVERNOR"])
    ovl.grantRole(governor_role, gov_overlay, {"from": gov_overlay})
    guardian_role = Web3.solidityKeccak(['string'], ["GUARDIAN"])
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
