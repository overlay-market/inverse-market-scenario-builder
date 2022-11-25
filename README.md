# inverse-market-scenario-builder

Research inverse market attack and attack mitigation solutions by simulating scenarios on the protocol


## Requirements

To run the project you need:

- Set env variables for [Etherscan API](https://etherscan.io/apis) and [Infura](https://eth-brownie.readthedocs.io/en/stable/network-management.html?highlight=infura%20environment#using-infura): `ETHERSCAN_TOKEN` and `WEB3_INFURA_PROJECT_ID`
- Local Ganache environment installed


## Installation

Using [Poetry](https://github.com/python-poetry/poetry) for dependencies. Install with `pipx`

```
pipx install poetry
```

Clone the repo, then

```
poetry install
```

within the local dir.

Set up Uniswap pool before running scenarios (this is done separately because it's a one time process and is time consuming):

- Open a terminal and run:
```
ganache-cli --accounts 10 --hardfork istanbul --fork https://mainnet.infura.io/v3/INFURA_KEY --gasLimit 9007199254740991 --mnemonic brownie --port 8545 --chainId 1 --db ganache-db/uniswap-setup
```
- Open another terminal and run:
```
brownie run scripts/uniswap_setup.py
```
- Close both terminals

To run scenarios:
- Create a copy of `uniswap-setup` (in `ganache-db` directory) and rename it to `overlay`
- Open a terminal and run:
```
ganache-cli --accounts 10 --gasLimit 9007199254740991 --mnemonic brownie --db ganache-db/overlay
```
- Open another terminal and run:
```
brownie run scripts/scenario_builder.py
```