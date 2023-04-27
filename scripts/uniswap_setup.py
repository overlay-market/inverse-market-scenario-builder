from brownie import (
    Contract, network, accounts, OverlayV1Token, USDC
)
from web3 import Web3
import json
import os
from pathlib import Path


def json_load(name):
    f = open(f'scripts/constants/{name}.json')
    return json.load(f)


def clear_contracts_file():
    path = 'scripts/constants/uniswap_setup_contracts.json'
    file = Path(path)
    if file.exists():
        os.remove('scripts/constants/uniswap_setup_contracts.json')


def to_dict(name, address, abi):
    new_dict = {"address": address, "abi": abi}
    path = 'scripts/constants/uniswap_setup_contracts.json'
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


def main():
    print('Network: ', network.show_active())
    clear_contracts_file()
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
    m_contracts = json_load('mainnet_contracts')
    uni_factory = Contract\
        .from_abi('uni_factory',
                  m_contracts['uni_factory']['address'],
                  m_contracts['uni_factory']['abi'])
    tx = uni_factory.createPool(ovl, usdc, 3000, {"from": alice})
    pool_add = tx.events['PoolCreated']['pool']
    pool_abi = json_load('pool_abi')
    pool = Contract.from_abi('pool', pool_add, pool_abi)
    to_dict('inv_pool', pool_add, pool_abi)
    pool.initialize(7.9220240490215315e28, {"from": alice})  # price ~= 1
    # If facing a timeout error at `increaseObservationCardinalityNext`,
    # consider changing `timeout` value to 600 here:
    # https://github.com/eth-brownie/brownie/blob/86258c7bdf194c800ae44e853b7c55fab60a23ce/brownie/network/main.py#L40
    # It doesn't seem like there is a better way to do this, since this issue
    # is still open:
    # https://github.com/eth-brownie/brownie/issues/600
    pool.increaseObservationCardinalityNext(610, {"from": alice})
    print('Complete!')
