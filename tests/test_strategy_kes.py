import pandas as pd
from halcyon import disruption_news, submit
from halcyon import strategy_kes as kes
from halcyon.data import as_of, read_all


def test_escalation_plan_ignores_future_information():
    tables = read_all("data")
    cutoff, weeks = 221, list(range(222, 235))
    expected = submit.plan_window(tables, cutoff, weeks, models=kes.MODELS)
    poisoned = {}
    for name, frame in tables.items():
        if "week" not in frame or name == "demand":
            poisoned[name] = frame.copy()
            continue
        future = frame.loc[frame.week == cutoff].copy()
        future["week"] = cutoff + 1
        for column in future.select_dtypes("number").columns.difference(["week"]):
            future[column] = 999999
        if name == "news":
            future["headline"] = "Kestria officials rule out new restrictions"
        poisoned[name] = pd.concat([frame, future], ignore_index=True)
    actual = submit.plan_window(poisoned, cutoff, weeks, models=kes.MODELS)
    pd.testing.assert_frame_equal(expected, actual)
    base = disruption_news.predict(as_of(tables, cutoff), cutoff, weeks)
    merged = expected.merge(base, on=["week", "material"], suffixes=("_kes", "_base"))
    assert (merged.disruption_prob_kes > merged.disruption_prob_base + 0.01).any()


def test_country_cancellation_removes_declared_merrow_escalation():
    tables = as_of(read_all("data"), 221)
    weeks = list(range(222, 235))
    forecast = kes.predict_disruption(tables, 221, weeks)
    base = disruption_news.predict(tables, 221, weeks)
    unexposed = set(tables["suppliers"].material) - set(
        tables["suppliers"].loc[lambda f: f.lane == "MERROW", "material"])
    pd.testing.assert_frame_equal(forecast.loc[forecast.material.isin(unexposed)],
                                  base.loc[base.material.isin(unexposed)])
    news = tables["news"].iloc[-1:].copy()
    news["week"] = 221
    news["article_id"] = "test-cancel"
    news["headline"] = "Tensions ease after talks with Kestria"
    news["body"] = "Merrow Strait shippers welcome the talks."
    cancelled = dict(tables, news=pd.concat([tables["news"], news], ignore_index=True))
    pd.testing.assert_frame_equal(kes.predict_disruption(cancelled, 221, weeks),
                                  disruption_news.predict(cancelled, 221, weeks))
