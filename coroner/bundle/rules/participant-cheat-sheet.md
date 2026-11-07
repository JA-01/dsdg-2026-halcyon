# ***DSDG Hackathon 2026 Participant Cheat Sheet***

**Supply Chain Disruptor \| Nov 6 to 8, 2026 \| all times Central**

Keep this open all weekend. Everything you need to compete is on one page.

## **Links**

| What | Link |
| :---- | :---- |
| Join the competition (one account per person) | [Kaggle invite link](https://www.kaggle.com/t/8d5cc0ce805c4eda8db5d328011767c6) |
| Competition page, data, leaderboard | [Kaggle competition](https://www.kaggle.com/competitions/dsdg-hackathon-2026-supply-chain-disruptor) |
| Office hours, Saturday 10 AM to 5 PM | [Zoom room](https://illinois.zoom.us/j/82673013783?pwd=GrSvyx0yGXDx5AhFY9BtAzS1Od8DBA.1) |
| Databricks track opt in (closes Sat 6 PM) | [Opt in form](https://docs.google.com/forms/d/e/1FAIpQLSfst7f3Ay_CILsIJjm2fznPy41CplIDS_nBd-wCVVlPrsghow/viewform) |
| Your team's video folder | Shared with your team's Google email. Search Drive for your team name |

## **Schedule**

| When | What |
| :---- | :---- |
| Fri 6:30 PM | Opening ceremony and dinner. Phase 1 data (weeks 1 to 208\) goes live |
| Sat 10 AM to 5 PM | Office hours on Zoom, every hour |
| Sat 12 PM | Phase 2 data (weeks 1 to 221\) goes live. Rerun your notebook |
| Sat 5:30 PM | Guest speaker |
| Sat 6 PM | Databricks track opt in closes |
| Sat 6:30 PM | Dinner and Microsoft Copilot session |
| Sun 12 PM | Final submissions and 3 minute videos due |
| Sun 6:30 PM | Closing ceremony at DCL. Winners announced |

## **What you submit**

One CSV with 260 rows, one per material per week for weeks 209 to 234\. Start from `sample_submission.csv`, which is valid and scores 0\.

| Column | What to put in it |
| :---- | :---- |
| `id` | `w{week}_{material}`, like `w209_lithium` |
| `disruption_prob` | Probability from 0 to 1 that any supplier of that material is hit that week |
| `price_forecast` | That week's benchmark price (average spot price across the 3 suppliers). Above 0 |
| `order_units` | Units to order that week. 0 or more |
| `share_KES` to `share_AUR` | Fraction of the order from each country. Each row sums to 1, and a country that doesn't sell the material gets 0 |

## **How you're scored**

Score \= 100 x (0.30 Prediction \+ 0.40 Financial \+ 0.30 Resilience). A simulator plays out your orders against what really happened. Buying a little early and from more than one supplier before a shock is usually what moves the score, since a stockout costs 5 times what the material does.

The public leaderboard covers weeks 209 to 221 and the private leaderboard covers weeks 222 to 234\. After Saturday noon only the private one matters, and it decides 80% of your final placement. Judges score your video for the other 20%.

## **Rules that trip people up**

* Teams of 1 to 4\. Merge your team on Kaggle before your first submission  
* 5 submissions per team per day  
* Select up to 2 final submissions by Sunday noon, or Kaggle picks your 2 best public scores  
* Only the competition data. The world is fictional, so outside data won't help  
* AI coding assistants are fine. Sharing code privately with another team is not

## **The video**

About 3 minutes, uploaded to your team's folder by Sunday noon. Cover the signals you found, how your forecasts turn into orders, how your plan survives shocks, and what your approach would miss.

## **Stuck?**

Common fixes: data lives under `/kaggle/input/` on Kaggle (the starter notebook finds it for you), shares must sum to 1 on every row, and every one of the 260 ids has to be there. Anything else, come to office hours or find an organizer.