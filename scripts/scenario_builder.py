from brownie import (
    Contract, network, accounts, OverlayV1Token, TestMintRouter,
    OverlayV1UniswapV3Factory, OverlayV1Factory
)
from web3 import Web3
from brownie_tokens import MintableForkToken
import json


def json_load(name):
    f = open(f'scripts/constants/{name}.json')
    return json.load(f)


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

    # Give Alice spot USDC tokens
    usdc = MintableForkToken('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48')
    usdc._mint_for_testing(alice, 1_000_000_000 * 1e18)

    # Deploy OVL/USDC Uniswap pool
    uni_factory = Contract\
        .from_explorer('0x1F98431c8aD98523631AE4a59f267346ea31F984')
    tx = uni_factory.createPool(ovl, usdc, 3000, {"from": alice})
    pool_add = tx.return_value
    pool_abi = json_load('pool_abi')
    pool = Contract.from_abi('pool', pool_add, pool_abi)
    pool.initialize(7.9220240490215315e28, {"from": alice})  # price ~= 1
    pool.increaseObservationCardinalityNext(610, {"from": alice})
    mint_router = alice.deploy(TestMintRouter)
    liquidity = 1e18
    lp(alice, pool, ovl, usdc, mint_router, liquidity, True)
    swap_amount = 1e17
    swap(alice, pool, mint_router, False, swap_amount)

    # Deploy Overlay Feed Factory, Feed, Factory
    feed_factory = gov_overlay.deploy(OverlayV1UniswapV3Factory, ovl,
                                      uni_factory, 600, 3600, 600, 12)

    market_base_token = ovl
    market_quote_token = usdc
    ovlX_base_token = usdc
    ovlX_quote_token = ovl
    market_fee = 3000
    market_base_amount = 1000000000000000000  # 1e18
    feed_factory.deployFeed(market_base_token, market_quote_token,
                            market_fee, market_base_amount, ovlX_base_token,
                            ovlX_quote_token, market_fee)

    factory = gov_overlay.deploy(OverlayV1Factory, ovl, gov_overlay)
    ovl.grantRole(ovl.DEFAULT_ADMIN_ROLE(), factory, {'from': gov_overlay})
    governor_role = Web3.solidityKeccak(['string'], ["GOVERNOR"])
    ovl.grantRole(governor_role, gov_overlay, {"from": gov_overlay})
    guardian_role = Web3.solidityKeccak(['string'], ["GUARDIAN"])
    ovl.grantRole(guardian_role, gov_overlay, {"from": gov_overlay})

    # Deploy Overlay inverse market
