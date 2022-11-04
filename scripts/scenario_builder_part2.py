from brownie import (
    Contract, network, accounts, chain, OverlayV1Token, TestMintRouter,
    OverlayV1UniswapV3Factory, OverlayV1Factory
)
from web3 import Web3
from brownie_tokens import MintableForkToken
import json


def json_load(name):
    f = open(f'scripts/constants/{name}.json')
    return json.load(f)


def main():
    print('Network: ', network.show_active())