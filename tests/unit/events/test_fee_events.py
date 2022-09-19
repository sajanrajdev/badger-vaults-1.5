from helpers.time import days
from helpers.utils import approx


def test_withdrawal_fee_event(vault, want, deployer, governance):
    depositAmount = int(want.balanceOf(deployer) * 0.1)
    want.approve(vault.address, depositAmount, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})

    # Transfer want tokens to vault to increase ppfs
    assert vault.getPricePerFullShare() == 1e18
    want.transfer(vault.address, depositAmount // 2)
    assert vault.getPricePerFullShare() != 1e18

    vault.earn({"from": governance})

    # internally will trigger _withdraw which contains target event
    withdraw_amount = depositAmount // 10 # Expected underlying
    withdraw_amount_shares = (withdraw_amount * vault.balance()) / vault.totalSupply()
    assert withdraw_amount != withdraw_amount_shares
    tx = vault.withdraw(withdraw_amount_shares, {"from": deployer})

    wd_fee_event = tx.events["WithdrawalFee"]

    # only one should be emitted
    assert len(wd_fee_event) == 1
    # check event fields are expected values (except ts and block)
    assert wd_fee_event["destination"] == governance
    assert wd_fee_event["token"] == vault.address
    assert (
        wd_fee_event["amount"]
        == vault.withdrawalFee() * withdraw_amount_shares / vault.MAX_BPS()
    )


def test_perf_fee_gov_event(
    deployer,
    vault,
    strategy,
    want,
    token_not_want,
    governance,
    strategist,
    keeper,
    chain,
):
    # include one `deposit`
    depositAmount = int(want.balanceOf(deployer) * 0.1)
    want.approve(vault, depositAmount, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})

    chain.sleep(days(1))
    chain.mine()

    vault.earn({"from": keeper})

    chain.sleep(days(1))
    chain.mine()

    # needs to leverage these methods from DemoStrategy to trigger events as will do a real strat
    # check 1st `reportHarvest` route of events emitted in harvest
    amount_harvested = 1e18
    total_supply_before = vault.totalSupply()

    prev_harvest_ts = vault.lastHarvestedAt()

    tx = strategy.test_harvest(amount_harvested, {"from": keeper})

    last_harvest_ts = vault.lastHarvestedAt()
    harvest_duration = last_harvest_ts - prev_harvest_ts

    perf_fee_gov_event = tx.events["PerformanceFeeGovernance"]
    perf_fee_strategist_event = tx.events["PerformanceFeeStrategist"]

    # since `managementFee` > 0, needs to take into consideration the surplus in the gov fee
    management_fee = (
        vault.managementFee()
        * (vault.balance() - amount_harvested)
        * harvest_duration
        / vault.SECS_PER_YEAR()
        / vault.MAX_BPS()
    )
    governance_fee_want = amount_harvested * vault.performanceFeeGovernance() / vault.MAX_BPS() + management_fee
    strategist_fee_want = amount_harvested * vault.performanceFeeStrategist() / vault.MAX_BPS()
    pool = vault.balance() - governance_fee_want - strategist_fee_want

    governance_fee_shares = governance_fee_want * total_supply_before / pool
    strategist_fee_shares = strategist_fee_want * (total_supply_before + governance_fee_shares) / (pool + governance_fee_want)
    # Total supply incremented by the minted fee shares
    assert approx(
        vault.totalSupply(),
        total_supply_before + governance_fee_shares + strategist_fee_shares,
        1
    )

    assert len(perf_fee_gov_event) == 1 and len(perf_fee_strategist_event) == 1
    assert (
        perf_fee_gov_event["destination"] == governance
        and perf_fee_strategist_event["destination"] == strategist
    )
    assert (
        perf_fee_gov_event["token"] == vault.address
        and perf_fee_strategist_event["token"] == vault.address
    )
    assert (
        approx(
            perf_fee_gov_event["amount"],
            governance_fee_shares,
            1,
        )
        and approx(
            perf_fee_strategist_event["amount"],
            strategist_fee_shares,
            1,
        )
    )

    # Chek 2nd `reportAdditionalToken` route of events emitted in harvest
    token_not_want.transfer(strategy, amount_harvested, {"from": deployer})
    tx = strategy.test_harvest_only_emit(
        token_not_want, amount_harvested, {"from": keeper}
    )

    perf_fee_gov_event = tx.events["PerformanceFeeGovernance"]
    perf_fee_strategist_event = tx.events["PerformanceFeeStrategist"]

    assert len(perf_fee_gov_event) == 1 and len(perf_fee_strategist_event) == 1
    assert (
        perf_fee_gov_event["destination"] == governance
        and perf_fee_strategist_event["destination"] == strategist
    )
    assert (
        perf_fee_gov_event["token"] == token_not_want.address
        and perf_fee_strategist_event["token"] == token_not_want.address
    )
    assert (
        perf_fee_gov_event["amount"]
        == amount_harvested * vault.performanceFeeGovernance() / vault.MAX_BPS()
        and perf_fee_strategist_event["amount"]
        == amount_harvested * vault.performanceFeeStrategist() / vault.MAX_BPS()
    )
