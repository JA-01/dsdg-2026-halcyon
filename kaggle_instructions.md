Overview
Halcyon Industries buys 10 raw materials from 6 countries, and the world keeps breaking its supply chain. Read the warning signs in news and market data, forecast which materials will be disrupted and what they will cost, and set a weekly ordering policy that keeps the factory running without overpaying. A supply chain simulator scores every submission on prediction accuracy, money saved, and resilience.

Part of the DSDG Hackathon 2026 at the University of Illinois Urbana-Champaign, Nov 6 to 8.

Start

5 minutes ago
Close

2 days to go
Description
You are the supply chain strategy team at Halcyon Industries, a manufacturer in the fictional country of Aurelia. Halcyon buys 10 raw materials, from lithium to semiconductors, from 6 countries spread across 5 shipping lanes. Every few months something breaks: a tariff hike, an export ban, a closed strait, a drought, a dock strike. Some of these show up in the news and the markets weeks ahead of time. Some are rumors that never happen. A few arrive with no warning at all.

Your job has two halves. First, read the signals in news, prices, tariffs, shipping and macro data and forecast which materials will be disrupted and what they will cost. Second, turn those forecasts into a weekly ordering policy: how much to buy, and from which countries, so the factory keeps running without overpaying.

Your submission is scored by a supply chain simulator that plays out your orders against what actually happens, so a good forecast only pays off if your policy acts on it.

Schedule (all times Central)
When	What
Fri Nov 6, 6:30 PM	Opening ceremony. Phase 1 data (weeks 1 to 208) goes live
Sat Nov 7, 12 PM	Phase 2 data (weeks 1 to 221) goes live
Sat Nov 7, 6 PM	Databricks track opt in closes
Sun Nov 8, 12 PM	Final submission deadline. Select your 2 final submissions and upload your 3 minute video
Sun Nov 8, 6:30 PM	Closing ceremony. Private leaderboard revealed
About the leaderboards
The public leaderboard scores weeks 209 to 221 and the private leaderboard scores weeks 222 to 234. After the Saturday release the public weeks are in the data, so the public leaderboard stops meaning much. Final standings come from the private leaderboard.

Databricks track
Same data, same leaderboard. Build your pipeline in Databricks Free Edition and opt in on the form your organizers share. A Databricks starter notebook is in the Code tab.

Evaluation
Every submission gets a score from 0 to 100.

Score = 100 x (0.30 x P + 0.40 x F + 0.30 x R)

Each part is clipped to the range 0 to 1, and each is scaled so the naive sample submission scores 0.

P, prediction accuracy (30%)

60% Brier skill on disruption_prob: 1 minus your Brier score divided by the Brier score of always predicting each material's historical disruption rate.
40% price skill on price_forecast: 1 minus your mean absolute percentage error divided by the error of carrying the last known benchmark price forward.
F, financial impact (40%)

F = (naive cost minus your cost) / (naive cost minus hindsight cost). The naive cost comes from the sample submission's policy. The hindsight cost comes from a plan that knew the future.

R, supply chain resilience (30%)

70% fill rate skill: how much more of Halcyon's demand you met during shock weeks than the naive policy did. Shock weeks are weeks a material is disrupted plus 4 recovery weeks.
30% diversification: 1 minus the concentration (Herfindahl index) of your shares, rescaled so single sourcing is 0 and an even split across a material's 3 suppliers is 1.
How the simulator works

Each test window (public and private) is simulated on its own and starts with 5 weeks of demand in stock and nothing in transit.
An order placed in week t is split by your shares. Each country's slice is filled only up to that country's capacity that week, is paid at that week's landed cost (spot price plus tariff plus shipping), and arrives after that week's lead time. Units a supplier cannot fill are cancelled and not charged.
Each week, arrivals go into stock and Halcyon uses up to that week's demand.
Holding stock costs 2% of the material's average landed cost per unit per week.
Each unit of unmet demand costs 5 times the average landed cost.
At the end of the window, units in stock or still in transit are sold back at 70% of the average landed cost.
Submission File
One CSV with a header and exactly 260 rows: one row per material per week for weeks 209 to 234. Every row is a forecast and a decision at the same time.

Column	Meaning
id	w{week}_{material}, for example w209_lithium
disruption_prob	Probability, 0 to 1, that any supplier of this material is hit by an active shock that week
price_forecast	Your forecast of that week's benchmark price (average spot price across the material's 3 suppliers). Must be above 0
order_units	Units to order that week. 0 or more
share_KES … share_AUR (6 columns)	How the order is split across countries. Each 0 to 1, summing to 1. Must be 0 for any country that does not sell the material (see suppliers.csv)
id,disruption_prob,price_forecast,order_units,share_KES,share_VAL,share_SUN,share_ORI,share_HAL,share_AUR
w209_lithium,0.12,41.80,1250,0.6,0.15,0,0.25,0,0
w209_rare_earths,0.65,88.10,450,0.3,0.4,0,0,0.3,0
w209_semiconductors,0.08,512.40,95,0.5,0,0.3,0,0.2,0
A file with missing or duplicate ids, blank values, probabilities outside 0 to 1, shares that do not sum to 1, or a share for a country that does not sell that material is rejected with a message naming the first bad row.

Dataset Description
The world
Halcyon Industries, a manufacturer in the fictional country of Aurelia, buys 10 raw materials from 6 fictional countries. Every material has exactly 3 supplier countries. The data covers 234 weekly periods starting Monday Jan 3, 2022 (week 1). Everything is synthetic, so real world knowledge will not help you, and the signals you need are all in these files.

Code	Country	Shipping lane
KES	Kestria	MERROW (Merrow Strait)
VAL	Valdmar	NORTH (Northern Sea route)
SUN	Sunda Coast	MERROW (Merrow Strait)
ORI	Orinoque	SOUTH (Southern route)
HAL	Halvard	ATLANTIC (Atlantic route)
AUR	Aurelia (domestic)	RAIL (domestic rail)
Materials: lithium, cobalt, copper, aluminum, steel, rare_earths, semiconductors, polymer_resin, specialty_glass, natural_gas.

Releases
Release	When	Weeks included
Phase 1	Friday Nov 6, 6:30 PM	1 to 208 (demand.csv covers all 234 weeks)
Phase 2	Saturday Nov 7, 12 PM	1 to 221
Your submission always covers weeks 209 to 234. Weeks 209 to 221 are the public leaderboard and weeks 222 to 234 are the private leaderboard. Once Phase 2 lands, the public window is history, so treat the public leaderboard as a warm up after Saturday noon.

Files
news.csv One row per news article, about 21 per week. Columns: article_id, week, date, source, headline, body. Some stories are early warnings of real shocks, most are routine, and some are rumors that never happen.

prices.csv One row per week, material and supplier country. spot_price is the price that week in Aurelian dollars per unit. futures_4w is the market price for delivery in 4 weeks.

tariffs.csv One row per week, material and supplier country. tariff_rate is the duty in force that week (0.10 means 10%). announced_rate and announced_effective_week are filled in when a future change has been announced, and blank otherwise.

shipping.csv One row per week and lane. container_rate (freight index), transit_days, and congestion_index (0 to 100).

macro.csv One row per week and country. pmi, fx_rate (country currency per Aurelian dollar, indexed), cpi_yoy, policy_rate, and tension_index (0 to 100, a noisy measure of political tension with Aurelia).

suppliers.csv Static table of who sells what. material, country, country_name, lane, base_lead_weeks, normal_capacity_units (how many units per week the country can usually supply to Halcyon), base_tariff.

demand.csv Halcyon's production plan: demand_units per week and material, for all 234 weeks including the test windows.

outcomes.csv Labels for released weeks only. One row per week and material. benchmark_price is the simple average of spot_price across the material's 3 supplier countries. disrupted is 1 when at least one of the material's suppliers was hit by an active shock that week.

supply_history.csv What actually happened for released weeks. One row per week, material and supplier country. capacity_units (units that supplier could deliver for orders placed that week), lead_time_weeks (weeks until an order placed that week arrives), landed_cost (price per unit including tariff and shipping).

sample_submission.csv A valid submission in the right format. It is the naive baseline and scores 0. See the Evaluation tab for every column.

Kinds of shocks in this world
Tariff hikes, export bans, strait closures, resource shortages, sanctions, port strikes, and sudden policy reversals. Most give some warning in the news and the market data before they hit. Policy reversals give none. Closures and strikes hit every country on a lane at once.

