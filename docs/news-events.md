# News events and signals (#14)

Deterministic, with no network, key or LLM. The supplied corpus uses 66 headline templates, so
`halcyon.news.extract_events` maps each to a shock category and stage by exact lookup. A template it
has not seen becomes `unmapped` rather than a guess, so check that count after each new release.

```python
from halcyon.news import extract_events, news_signals

events = extract_events(view["news"])            # article_id, week, date, category, stage, entities, evidence
signals = news_signals(view["news"], view["suppliers"], last_week=view.cutoff)
# (week, material): news_early, news_imminent, news_active, news_recovery, news_averted, news_open
```

A signal row for week W reads only articles dated up to W, over a trailing 4 weeks. A test pins this
against future rows. Repeated text stays separate per article, with its own week. A lane event reaches
every supplier on that lane, including both KES and SUN on MERROW.

## Does it help?

`python -m halcyon.compare --config configs/compare_news.json` compares one estimator with news on and
off (`halcyon.news.forecaster.DisruptionModel`), on development origins 130 and 156. Holdout 182 is
untouched. Only horizons up to 13 use the state lift, so the two versions differ only there.

| Window | Rate baseline Brier | No news | With news |
| --- | ---: | ---: | ---: |
| Origin 130, h1-13 | 0.189 | 0.417 | 0.375 |
| Origin 130, h14-26 | 0.088 | 0.081 | 0.081 |
| Origin 156, h1-13 | 0.128 | 0.103 | 0.077 |
| Origin 156, h14-26 | 0.317 | 0.320 | 0.320 |

News improved near-term Brier over the same model without it on both origins. Against the plain rate
the result is mixed: it loses badly at origin 130 h1-13, which starts inside a 35-week shock that ended
three weeks later. Proxy costs barely move. Two origins are too few to call this proven, so it is
a signal for the real forecaster, not a selected candidate.

The first attempt, a pooled logistic model, predicted 0.87 at horizon 26 after that same long shock. It
was replaced by shrunk state lifts; a regression test keeps long horizons near the rate.

## Limitations

Policy reversals give no warning by design, so no news signal can catch them. Stage labels are my reading
of the templates, not organizer labels. Lifts rest on few distinct shocks, and overlapping training
pairs are not independent.
