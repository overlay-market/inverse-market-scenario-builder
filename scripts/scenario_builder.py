from sqlite3 import paramstyle
from brownie import (
    Contract, network, accounts, OverlayV1Token, TestMintRouter,
    OverlayV1UniswapV3Factory, OverlayV1Factory, OverlayV1UniswapV3Feed, USDC,
    OverlayV1Market, chain
)
from web3 import Web3
import json


def json_load(name):
    f = open(f'scripts/constants/{name}.json')
    return json.load(f)


def to_dict(name, address, abi):
    new_dict = {"address": address, "abi": abi}
    with open('scripts/constants/contracts.json') as f:
        full_dict = json.load(f)
        full_dict[name] = new_dict
    with open('scripts/constants/contracts.json', 'w') as f:
        json.dump(full_dict, f)


def create_ovl(gov, alice):
    supply = 8000000
    minter_role = Web3.solidityKeccak(['string'], ["MINTER"])
    tok = gov.deploy(OverlayV1Token)
    # mint the token then renounce minter role
    tok.grantRole(minter_role, gov, {"from": gov})
    tok.mint(gov, supply * 10 ** tok.decimals(), {"from": gov})
    tok.renounceRole(minter_role, gov, {"from": gov})

    tok.transfer(alice, (supply/2) * 10 ** tok.decimals(), {"from": gov})
    return tok


def lp(acc, pool, ovl, usdc, mint_router, amount, appr_reqd):

    if appr_reqd:
        ovl.approve(mint_router, ovl.balanceOf(acc), {'from': acc})
        usdc.approve(mint_router, usdc.balanceOf(acc), {'from': acc})

    mint_router.mint(pool.address, -887220, 887220, amount, {"from": acc})


def swap(acc, pool, mint_router, ovl_to_usdc, amount):
    mint_router.swap(pool, ovl_to_usdc, amount, {'from': acc})


def main():
    print('Network: ', network.show_active())
    gov_overlay = accounts[0]
    alice = accounts[1]

    # Deploy OVL token
    ovl = create_ovl(gov_overlay, alice)
    to_dict('OVL', ovl.address, ovl.abi)
    # Give Alice spot USDC tokens
    usdc = USDC.deploy({'from': gov_overlay})
    print(f'USDC created at {usdc.address}')
    to_dict('USDC', usdc.address, usdc.abi)
    usdc.grantRole(Web3.solidityKeccak(['string'], ["MINTER"]),
                   gov_overlay.address, {'from': gov_overlay})
    usdc.mint(alice, 1e9 * 1e18, {'from': gov_overlay})
    print('Minted 1e9 tokens to input account')

    # Deploy OVL/USDC Uniswap pool
    contracts = json_load('contracts')
    uni_factory = Contract\
        .from_abi('uni_factory',
                  contracts['uni_factory']['address'],
                  contracts['uni_factory']['abi'])
    tx = uni_factory.createPool(ovl, usdc, 3000, {"from": alice})
    pool_add = tx.events['PoolCreated']['pool']
    pool_abi = json_load('pool_abi')
    pool = Contract.from_abi('pool', pool_add, pool_abi)
    to_dict('inv_pool', pool_add, pool_abi)
    pool.initialize(7.9220240490215315e28, {"from": alice})  # price ~= 1
    pool.increaseObservationCardinalityNext(610, {"from": alice})

    mint_router = alice.deploy(TestMintRouter)
    liquidity = 1e17
    lp(alice, pool, ovl, usdc, mint_router, liquidity, True)
    swap_amount = 1e16
    swap(alice, pool, mint_router, False, swap_amount)
    chain.mine(timedelta=7210)  # Mine 2x the duration of longer TWAP

    # Deploy Overlay Feed Factory, Feed, Factory
    feed_factory = gov_overlay.deploy(OverlayV1UniswapV3Factory, ovl,
                                      uni_factory, 600, 3600, 600, 12)

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

    factory = gov_overlay.deploy(OverlayV1Factory, ovl, gov_overlay)

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
    market_addr = factory.deployMarket(feed_factory, feed, params,
                                       {'from': gov_overlay})
    market = OverlayV1Market.at(market_addr)
    asdf
k