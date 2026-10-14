# Token listing pack — MDM1 (Polygon) and MD1usd (Polygon, Solana)

Status of what exists today (from the owner's own records):

| Token | Chain | Contract / Program | Needed for listing |
|---|---|---|---|
| MDM1 | Polygon | 0x0a4E17e4F9c179a310069711069c346CFCf13c3f | verified source on Polygonscan, logo, liquidity pool link |
| MD1usd | Polygon | 0x6bd6A380903Ae072A764A929C34779824c068BB1 | verified source, collateral/reserve proof page, logo |
| MD1usd | Solana | 3fN2LAt47q3oSgNq4dJZt4DuAh5yJw6mb6B3dRYJGHa8 (closed; fresh deployment planned) | new program id |
| MDM1 / MD1usd | Ethereum, BNB Chain | **none deployed** | a contract must exist on the chain before any submission |

A listing request is always for an EXISTING contract on that chain. Ethereum and BNB need new deployments
(or a bridge/wrapped version) first; nothing can honestly be submitted for them until then.

## Per-venue checklist (in the order that matters for visibility)
1. Block explorers (Polygonscan / Etherscan / BscScan): source verification -> "Update Token Info" form (logo 256px PNG, website, socials, description).
2. Trust Wallet Assets: PR to trustwallet/assets `blockchains/<chain>/assets/<checksum-address>/{info.json,logo.png}` (templates in this folder). Requires a live liquidity pool and a working website.
3. CoinGecko ("Request new listing"), CoinMarketCap (application form): need >= 1 DEX pool with real volume, audit or verified source, whitepaper, team page, no misleading claims.
4. DefiLlama (TVL/stablecoin listing): PR to DefiLlama-Adapters / stablecoin adapter, needs on-chain reserve data.
5. Token lists: Uniswap default list is closed to new tokens; use the CoinGecko list or the QuickSwap/PancakeSwap token-list PRs.

## Website readiness (what reviewers reject on) — status of mdm1.org / md1usd.com
- Clear whitepaper, tokenomics, team/contact, contract addresses with explorer links, security/audit page, risk disclosure, terms.
- No guaranteed-returns language ("investment platform" wording is a common rejection reason; use "community token" + disclosures).
- Transfer tax (5%, auto-burn) must be stated plainly: wallets and listing sites flag taxed tokens.

## Information needed from the owner (blank = missing)
- Reason / venue of the previous rejection (the exact message).
- Token decimals, total/circulating supply, launch date.
- Liquidity pool links (QuickSwap pair address) and current liquidity/volume.
- Logo files (256x256 PNG, transparent), project one-liner (<= 100 chars), long description.
- Official social links, contact email on the site's domain.
- Whether Ethereum / BNB deployment (or a bridged version) is wanted, and from which deployer wallet.
