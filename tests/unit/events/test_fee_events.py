from helpers.time import days
from helpers.utils import approx


def test_withdrawal_fee_event(vault, want, deployer, governance):
    depositAmount = int(want.balanceOf(deployer) * 0.1)
    want.approve(vault.address, depositAmount, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})
    vault.earn({"from": governance})

    # internally will trigger _withdraw which contains target event
    withdraw_amount = depositAmount // 10
    tx = vault.withdraw(withdraw_amount, {"from": deployer})

    wd_fee_event = tx.events["WithdrawalFee"]

    # only one should be emitted
    assert len(wd_fee_event) == 1
    # check event fields are expected values (except ts and block)
    assert wd_fee_event["destination"] == governance
    assert wd_fee_event["token"] == vault.address
    assert (
        wd_fee_event["amount"]
        == vault.withdrawalFee() * withdraw_amount / vault.MAX_BPS()
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
            amount_harvested * vault.performanceFeeGovernance() / vault.MAX_BPS()
            + management_fee,
            1,
        )
        and perf_fee_strategist_event["amount"]
        == amount_harvested * vault.performanceFeeStrategist() / vault.MAX_BPS()
    )

    # chec 2nd `reportAdditionalToken` route of events emitted in harvest
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
