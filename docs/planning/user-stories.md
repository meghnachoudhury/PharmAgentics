<!-- Markdown copy of the Google Doc "User stories" (Consolidated 10/22 folder), taken 2026-10-23, refreshed 2026-11-20 (P1-Q2, P3-Q6: projected national). The Google Doc is the master; update it first. -->

# **PharmAgentics User Stories: Briefing and Forecast Personas**
Oct 22, 2026 · @Michael
This doc has one user story per persona question: 24 for the Briefing Agent (P1 to P4) and 18 for the Forecast-Explanation Agent (CA, BM, FM). Each story is anchored on a real week in Meghna's data release and says what the agent should answer, in Given / When / Then form, and what the persona does next.
## **How to read a story**
Every story has the same six parts.
| Part | What it holds |
| :- | :- |
| Story | "As [persona], I want … so that …", taken from the persona's question |
| Answer from the data | What a correct agent would report for the anchor week, with figures computed from the agent-visible tables |
| Given / When / Then | The seeded condition, the run, and what the output must show; pastes into a spec's acceptance scenarios |
| Must not say | The claim that fails the story |
| Action | What the persona does with the output, and what the output tells them to do |
| Eval items | The Evaluation Pack items (EV-x.y) or Forecast items (FE-xx) the story exercises |

**Where the numbers come from.** I loaded the repo's release (day1-v1, seed 7) into DuckDB with Meghna's loader and queried the raw and reporting schemas. Every Rx figure uses the gated view reporting.v_reportable_rx, so cuts that fail the feed gate are left out. Weeks are named by their Monday start date. No answer key was used; the hidden answer key is not in the repo.
**These are illustrations, not agent output.** The attribution figures use one simple method: the change in the affected territory minus the change in the other seven over the same weeks (a difference-in-differences). The agent's own tools will set the real figures. Where the data shows no driver, the story says so instead of guessing.
**Personas are not merged.** Part A uses the Briefing Agent Personas; Part B uses Sienna's Forecast-Explanation personas. Where titles look alike (P1 and CA, P3 and BM), the stories differ because the outputs differ: a weekly brief versus a forecast-miss explanation.
## **What the data shows**
The stories draw on ten kinds of moment in the release: five business events with a visible driver, one gap with none, three feed artifacts and the holiday weeks. Hover a mark for its detail.
*(Chart in the Google Doc; not reproduced here.)*
From access_status_monthly, market_basket, promo_activity, inventory_weekly, v_feed_health and calendar · 104 weeks
Metacora is the only event that touches every territory, which is why most 2026 forecast misses are broad. The others are local and end within three months.
# **Part A. Briefing Agent personas**
## **P1 · Commercial Analyst (Ace)**
Ace produces the brief and reviews the agent's draft first. Ace's stories test whether review can replace rebuilding.
### **P1-Q1 · Do the numbers tie out to the source tables?**
*As Ace, I want every figure in the draft to match the pinned data, so that I review the brief instead of rebuilding it.*
  - **Answer from the data (week of 2026-07-06).** The Great Lakes feed has 143 rows against 128 expected: 15 duplicate keys. Summed raw, Great Lakes BXA TRx is 670; with duplicates removed it is 624, so a naive sum overstates it by 46 TRx (7.4%). The gate withholds the whole Great Lakes cut, so national BXA TRx from reportable cuts is 3,665 across 7 of 8 territories.
  - **Given** the snapshot pinned for 2026-07-06 holds 15 duplicate Rx keys in Great Lakes. **When** the brief runs. **Then** every KPI figure matches the gated view on that snapshot, Great Lakes shows as withheld, and national figures carry the label "7 of 8 territories."
  - **Must not say** "Great Lakes BXA TRx was 670," or quote 3,665 as a full national total.
  - **Action.** Ace opens two claim links at random, confirms the withheld cut, and asks P2 to request a clean reload. No table is rebuilt.
  - **Eval items** EV-1.1, EV-2.1, EV-2.3.
### **P1-Q2 · Is this week's data complete, and which cuts can't I report?**
*As Ace, I want feed problems found before drafting, so that I never write commentary on numbers that are wrong.*
  - **Answer from the data (week of 2026-05-04).** New England delivered 84 of 128 rows (44 missing keys), panel coverage 0.656 against a 0.98 floor, 10.29 days after week end against a 7-day target; status INCOMPLETE. Its observed BXA TRx of 267 compares with 397 to 422 in the four weeks before. Projected from its panel coverage, New England is about 407 (267 divided by 0.656), an assumption the brief labels as projected, and projected national BXA TRx is 4,491. The other seven territories pass.
  - **Given** New England fails the feed gate for 2026-05-04. **When** the brief runs. **Then** the Bottom line says first that New England's feed is incomplete; The numbers gives a projected national with New England labelled as projected, an assumption from its panel coverage; What the data can't tell us names New England as not reportable with its reasons; every like-for-like figure states how many territories it covers; and no story is opened for New England.
  - **Must not say** "New England BXA fell 34%."
  - **Action.** Ace leaves New England out of the commentary and adds it to next week's re-check list. The brief tells Ace to re-run New England when the reload lands and to disclose the restated week.
  - **Eval items** EV-2.1, EV-2.3, EV-1.1.
### **P1-Q3 · Which changes are big enough to make the brief?**
*As Ace, I want normal territory swings left out, so that the brief is consistent week to week and nobody chases noise.*
  - **Answer from the data (week of 2025-04-21).** National BXA TRx was 4,822, 0.2% below its 4-week average. Territories swung widely: Pacific +24.8% week over week, New England +15.1%, South Central +14.7%, Southeast −10.8%, Mid-Atlantic −10.5%. Those swings are normal here: outside holiday weeks, 1 week in 10 moves more than 15% to 22% in every territory. No access, promotion or inventory change sits in that week.
  - **Given** a week with no injected event and normal territory noise. **When** the brief runs. **Then** it is a routine brief: KPI table, no stories, at most one line that territory swings stayed in their normal range.
  - **Must not say** "Pacific surged 25%."
  - **Action.** Ace ships the routine brief in minutes. The brief tells Ace nothing needs investigating.
  - **Eval items** EV-3.2, EV-3.3.
### **P1-Q4 · Where did this number come from?**
*As Ace, I want one click from any figure to the query behind it, so that tracing takes seconds, not an afternoon.*
  - **Answer from the data (weeks of 2025-08-04 to 2025-10-27).** Take the claim "BXA new-to-brand prescriptions on one Mid-Atlantic Medicare Part D plan fell 37%." It comes from the gated Rx view for plan SYN_MID_ATLANTIC_MEDICARE_PART_D_1: 15.0 NBRx a week over 13 weeks, against 23.8 a week over the 9 weeks before. The cause cited beside it comes from access_status_monthly: that plan moved BXA from tier 2 to tier 3 and added prior authorization and step therapy, effective 2025-08-01.
  - **Given** a story that cites a plan-level NBRx change and an access change. **When** Ace clicks either number. **Then** it opens an evidence item naming the tool, its parameters (plan, product, weeks), the pinned snapshot and the trace span.
  - **Must not say** a figure with no evidence link.
  - **Action.** Ace checks the link instead of re-querying. Reviewer minutes to trace are logged against the manual baseline.
  - **Eval items** EV-6.1, EV-6.2, EV-6.3.
### **P1-Q5 · Am I confident nothing material was left out?**
*As Ace, I want every material change surfaced and ranked, so that the brief is not judged on what it missed.*
  - **Answer from the data (week of 2026-06-08).** National BXA TRx was 3,860, about 513 below its 4-week average (−11.7%). Two stories were live. First, Pacific BXA TRx fell to 464 against 709 a week in May, while BXA inventory fill there dropped to 0.687 with 22.5% of orders backordered (normal is 0.97 to 1.0); Pacific alone is about half of the national gap. Second, competitor Metacora (BXE), launched 2026-03-02, held about 12% of the basket and was still climbing.
  - **Given** a week with a regional supply shortfall on top of an ongoing competitor launch. **When** the brief runs. **Then** both stories appear, ranked by business impact, and the "considered and dropped" list shows what else was checked.
  - **Must not say** "BXA fell 12% nationally" with no regional split.
  - **Action.** Ace scans the dropped list to confirm nothing large is missing, then signs off the draft for P2.
  - **Eval items** EV-3.1, EV-3.3.
### **P1-Q6 · How much do I have to rewrite before this goes to my manager?**
*As Ace, I want a draft in our Monday format that needs only wording fixes, so that the agent saves real time.*
  - **Answer from the data.** The data cannot measure rewriting; review does. What the data fixes is the content: for the week of 2026-08-24, a correct draft carries a Southeast story (rep coverage gap, below) and a continuing Metacora line, and nothing about a national "collapse."
  - **Given** the 2026-08-24 snapshot. **When** the draft reaches Ace. **Then** it follows the team template, every figure is a filled claim token, and "new patients" appears only for NBRx.
  - **Must not say** "new patients" for NRx, or any figure typed outside a claim token.
  - **Action.** Ace edits wording only. Each edit gets a failure tag; a fix repeated in two weeks becomes a new eval case.
  - **Eval items** EV-8.1, EV-7.4, EV-9.2.
## **P2 · Insights Manager (Marcus)**
Marcus signs off the brief and defends it to leadership. His stories test whether the story is real and whether he can stand behind it.
### **P2-Q1 · Is this change real, or a data or calendar artifact?**
*As Marcus, I want data artifacts separated from business change before any explanation, so that I never send leadership a story that unravels.*
  - **Answer from the data (week of 2026-04-06, today's snapshot).** Summed over reportable cuts, national BXA TRx is 3,860, down 18.4% from 4,729 the week before. But Mid-Atlantic is withheld: all 32 of its BXA cells for that week were restated on 2026-07-13. On the 7 territories that report both weeks, BXA went from 4,005 to 3,860, a 3.6% dip.
  - **Given** a week where one territory's cut is withheld for restatement review. **When** the brief re-runs on the current snapshot. **Then** the national dip is labelled a data artifact, the like-for-like change on 7 territories is stated, and no business story opens unless that like-for-like change clears the materiality thresholds.
  - **Must not say** "BXA fell 18% nationally."
  - **Action.** Marcus approves the "data artifact" label and raises the restatement with the data vendor. The brief tells him which cut to re-check.
  - **Eval items** EV-2.2, EV-2.1, EV-3.2.
### **P2-Q2 · What explanations were considered, and why were the others ruled out?**
*As Marcus, I want competing explanations tested and recorded, so that "what about the competitor?" has an answer on the spot.*
  - **Answer from the data (weeks of 2025-08-04 to 2025-10-27, Mid-Atlantic).**
  - **Access, supported.** Plan SYN_MID_ATLANTIC_MEDICARE_PART_D_1 moved BXA to tier 3 with prior authorization and step therapy from 2025-08-01 to 2025-10-31. On that plan BXA TRx fell 22.5% (183 to 142 a week) while competitors Lipidara and Vascriva each gained about 20%.
  - **Promotion, ruled out.** Mid-Atlantic BXA rep calls held at 50 a week against 53 before.
  - **Supply, ruled out.** BXA inventory fill in Mid-Atlantic averaged 0.98.
  - **Competitor launch, ruled out.** Metacora did not launch until 2026-03-02.
  - **Data artifact, ruled out.** Every Mid-Atlantic cut in those weeks passes the feed gate.
  - **Given** a regional weakness with one access change and stable promotion, supply and feeds. **When** the brief investigates. **Then** the story names access as the leading driver and lists each alternative with its verdict and evidence link.
  - **Must not say** a single cause with no alternatives on record.
  - **Action.** Marcus walks into the brand meeting with the ruled-out list. The brief tells him to involve market access.
  - **Eval items** EV-4.1, EV-4.2, EV-5.1.
### **P2-Q3 · How confident are we, and where should we say we don't know yet?**
*As Marcus, I want an honest "not enough evidence yet," so that I never overclaim in front of leadership.*
  - **Answer from the data (weeks of 2026-08-31 to 2026-09-28, South Central).** South Central BXA TRx slipped 4.2% from July while the other territories rose 11.1%, a gap of about 15 points. Nothing in the context tables explains it: rep calls averaged 47 a week (normal is about 46) with no vacancy, no South Central plan put BXA or its older competitors under prior authorization or step therapy, inventory fill stayed at or above 0.968, and every feed passed. Metacora's share there (16.0%) is only slightly above other territories (13.8% to 15.8%).
  - **Given** a sustained regional gap with no driver visible in access, promotion, supply, competitor or feed data. **When** the brief investigates. **Then** the story closes at Low confidence as "unresolved, investigate next," lists the checks run, and names no driver.
  - **Must not say** "South Central is down because of Metacora."
  - **Action.** Marcus presents it as "still investigating." The brief tells him what to check next: plan and specialty splits, and local context from sales leadership.
  - **Eval items** EV-5.1, EV-5.2, EV-5.3.
### **P2-Q4 · Where is the change concentrated?**
*As Marcus, I want a national number broken down to where it actually happens, so that the right team acts.*
  - **Answer from the data (weeks of 2025-08-04 to 2025-10-27).** Nationally the dip is invisible: BXA TRx rose 9.0% against June and July. Mid-Atlantic rose only 3.2%. Inside Mid-Atlantic, one Medicare Part D plan with 26% of the territory's covered lives fell 22.5% (about 41 TRx a week), while the territory's other channels rose 15.1%. The largest NBRx loss on that plan is in primary care, 12.1 to 7.3 a week.
  - **Given** a plan-level access change hidden inside a rising national trend. **When** the brief runs. **Then** concentration names territory, channel, plan and specialty, and the segment contributions sum to the territory change.
  - **Must not say** "Mid-Atlantic Medicare is down" without the plan, or "BXA is growing nationally, no issues."
  - **Action.** Marcus routes the story to market access with the plan named.
  - **Eval items** EV-4.3, EV-3.1.
### **P2-Q5 · If someone challenges a claim, can I show the evidence behind it?**
*As Marcus, I want every claim answered against the numbers as they stood at sign-off, so that a challenge does not mean rebuilding the analyst's work.*
  - **Answer from the data (week of 2026-04-06, Mid-Atlantic).** The brief signed off in April reported Mid-Atlantic BXA TRx of 692 for that week. On 2026-07-13 the vendor restated all 32 cells (reason: late claims adjustment) to 742, up 50 (7.2%). NBRx moved from 97 to 98.
  - **Given** a figure restated after sign-off. **When** someone challenges the April number. **Then** its evidence link opens the value on the snapshot pinned at sign-off (692) and the restatement record beside it.
  - **Must not say** "742" as if it were the figure signed off in April.
  - **Action.** Marcus answers on the spot: the April figure was right for the data of the day and was later restated.
  - **Eval items** EV-6.2, EV-1.2.
### **P2-Q6 · Is this freeing my team's time without risking our credibility?**
*As Marcus, I want time saved and errors counted side by side, so that I adopt the agent on evidence.*
  - **Answer from the data.** Time cannot be read from the data; the run measures it. What the data sets is the risk test: the release has three feed artifacts and holiday weeks that drop national TRx by 16% to 21% against the 4-week average. Reading any of them as a business event is a critical error.
  - **Given** a held-out stretch of weeks that includes artifacts and holidays. **When** every version of the brief runs on it. **Then** the scorecard reports run time, reviewer minutes, cost, critical errors and run-to-run spread for each version against the manual baseline.
  - **Must not say** "saves X hours" without the critical-error rate beside it.
  - **Action.** Marcus decides on adoption from the scorecard.
  - **Eval items** EV-8.2, EV-8.3, EV-8.4, EV-8.5.
## **P3 · Brand Director (Diana)**
Diana reads only the brief P2 approved and carries it to leadership. Her stories test the "so what" and whether she can repeat it safely.
### **P3-Q1 · What changed this week that I need to know about?**
*As Diana, I want the two or three changes that matter at the top, so that I don't dig through a long report.*
  - **Answer from the data (week of 2026-04-27).** Eight weeks after launch, competitor Metacora (BXE) held 9.3% of the four-brand basket. BXA's share was 33.2%, down 2.6 points from 35.8% in the last week before launch (2026-02-23). No access, promotion or supply table shows a new event that week.
  - **Given** a competitor launch eight weeks old and still gaining. **When** the brief runs. **Then** the first story is Metacora's share gain and BXA's share loss, with both figures and the launch date.
  - **Must not say** a list of territory moves with the competitor story buried below them.
  - **Action.** Diana raises competitive response at the leadership meeting. The brief tells her to loop in sales and marketing.
  - **Eval items** EV-3.1, EV-3.3.
### **P3-Q2 · Does this matter for the brand, or can I ignore it?**
*As Diana, I want expected seasonal dips labelled, so that I am not pulled into false alarms.*
  - **Answer from the data (weeks of 2025-12-22 and 2025-12-29).** National BXA TRx was 4,309 and 4,188, 16.1% and 19.0% below the 4-week average. Both weeks had 4 business days, and the second was the plan-year reset. The same two weeks a year earlier fell 18.9% and 18.2%. The next week rebounded to 4,861, up 16.1%.
  - **Given** two holiday weeks with lower business days. **When** the brief runs. **Then** it labels the drop a calendar effect, cites last year's same weeks, and opens no story.
  - **Must not say** "BXA fell 19%."
  - **Action.** Diana ignores it. The brief tells her to expect the rebound the next week.
  - **Eval items** EV-3.4, EV-3.2.
### **P3-Q3 · Why did it happen, in terms I can explain to my leadership?**
*As Diana, I want the explanation in plain words with one number each, so that I can repeat it upward.*
  - **Answer from the data (weeks of 2026-06-01 to 2026-06-29, Pacific).** A plain-language version: "For five weeks in June, Pacific pharmacies could fill only about 7 in 10 BXA orders. Pacific BXA prescriptions fell 34% while other territories fell 1%. Supply returned to normal on July 6, and prescriptions recovered."
  - **Given** a regional supply shortfall with a clean recovery. **When** the brief writes the story. **Then** it uses short sentences, one idea and one number per sentence, and calls it a supply problem, not a demand problem.
  - **Must not say** "difference-in-differences," "fill-rate elasticity," or any term Diana would have to translate.
  - **Action.** Diana tells leadership it was supply, not demand. The brief tells her to ask supply chain and trade for the root cause.
  - **Eval items** EV-7.1.
### **P3-Q4 · Is this new or the same issue as last week, and is it getting better or worse?**
*As Diana, I want continuing stories marked with their trend, so that repeated alarms don't erode attention.*
  - **Answer from the data (week of 2026-09-28).** The Metacora story is in its 31st week. Its share of the basket, averaged over 4-week blocks, went 2.2%, 6.7%, 9.8%, 12.1%, 13.1%, 13.8%, 15.3% and 15.2%. It is worse than at launch but has flattened for the last 8 weeks. That week BXA held 32.1% and Metacora 15.2%.
  - **Given** a story that has run for months. **When** the brief runs. **Then** it is marked "continuing," states the direction (worse, now flat), and is not rediscovered as new.
  - **Must not say** "New: competitor gaining share."
  - **Action.** Diana moves from alarm to monitoring. The brief tells her to ask marketing for its defense plan.
  - **Eval items** EV-7.2.
### **P3-Q5 · What should I do, and who should I loop in?**
*As Diana, I want next steps and the right function named, so that implications for sales, access and finance are not left implicit.*
  - **Answer from the data (weeks of 2026-08-03 to 2026-08-31, Southeast).** Southeast BXA TRx fell 24.8% (639 to 481 a week) while other territories rose 6.5%. Over the same five weeks aggregated rep calls there fell to 19 a week from about 50, digital impressions halved, and the aggregated vacancy count was 1. When calls returned in September, the gap narrowed to about 8 points.
  - **Given** a territory coverage gap shown only at aggregate level. **When** the brief writes next steps. **Then** it says "involve sales leadership on Southeast coverage" and stays at territory level.
  - **Must not say** any line that points to one rep.
  - **Action.** Diana asks sales leadership for a coverage plan and takes the finding into budget talks with P4.
  - **Eval items** EV-7.3, EV-9.1.
### **P3-Q6 · Can I quote these numbers in my leadership meeting?**
*As Diana, I want numbers that will not be corrected later, so that my credibility holds upward.*
  - **Answer from the data (brief of 2026-07-13).** The vendor restated Mid-Atlantic BXA TRx for the week of 2026-04-06 from 692 to 742 that day. Projected national BXA TRx for the week of 2026-07-13 is 4,240, with every territory observed. The like-for-like change against the four weeks before covers 7 of 8 territories, because Great Lakes failed its checks for 2026-07-06. Three weeks in the release have one failed territory cut (2026-04-06, 2026-05-04, 2026-07-06); their projected national labels that territory as projected or estimated, an assumption, instead of leaving it out.
  - **Given** a restatement of a number already reported. **When** the next brief runs. **Then** it states the old and new values with the reason where leaders see them, any like-for-like figure built on 7 territories says so, and the projected national labels a projected or estimated territory as an assumption instead of leaving it out.
  - **Must not say** a corrected number with no note that it changed.
  - **Action.** Diana quotes only from the KPI table and corrects her April deck. The brief tells her which earlier figure changed.
  - **Eval items** EV-1.1, EV-1.2.
## **P4 · Marketer (Magdalena)**
Magdalena runs promotion with the budget P3 sets and reads the brief after P2 signs off. Her stories test promotion as one driver among several, never assumed.
### **P4-Q1 · Did my campaign move brand sales, and by how much?**
*As Magdalena, I want promotion tested with a verdict either way, so that sales gains are not credited to whichever campaign launched last.*
  - **Answer from the data (weeks of 2026-02-02 to 2026-04-06, Great Lakes).** The release has no sustained BXA campaign push: rep calls and digital impressions never exceed 1.5 times their territory median, and sample spikes last a single week. The clearest read on promotion is its absence. In Great Lakes, aggregated rep calls fell from about 48 a week to about 20, and digital impressions averaged 915 against a median of 1,652. In the four weeks before Metacora launched, Great Lakes BXA TRx fell 16.5% while other territories rose 1.1%, about 120 TRx a week below trend. When calls returned on 2026-04-13, Great Lakes TRx jumped from 503 to 730 in one week.
  - **Given** a territory where promotion lapses and then returns. **When** the brief tests promotion. **Then** promotion gets a "supported" verdict for the Great Lakes drop, with the size stated as an association and the method named.
  - **Must not say** "promotion caused a 120 TRx lift," or credit promotion in any week where its activity did not change.
  - **Action.** Magdalena uses the lapse as evidence that field and digital presence holds BXA volume in Great Lakes.
  - **Eval items** EV-4.5, EV-4.1.
### **P4-Q2 · Which geographies, segments and channels responded, and which did not?**
*As Magdalena, I want the effect broken down by geography and channel, so that I can compare a campaign's area with the rest.*
  - **Answer from the data.** Both coverage gaps hit broadly rather than in one channel.
  - **Great Lakes (2026-02-02 to 2026-02-23, against January):** cash −31%, Medicaid −25%, commercial −14%, Medicare Part D −12%; cardiology and internal medicine −20%, primary care −17%, endocrinology +3%. Other territories rose 1.1%.
  - **Southeast (2026-08-03 to 2026-08-31, against July):** commercial −30%, cash −26%, Medicaid and Medicare Part D −21%; endocrinology −30%, internal medicine −29%, cardiology −26%, primary care −20%. Other territories rose 6.5%.
  - **Given** two territories with promotion lapses. **When** the brief reports them. **Then** it shows each territory by channel and specialty against the rest of the country, and flags small cells (cash is 36 to 49 TRx a week) as noisy.
  - **Must not say** "cash patients respond most to promotion" from a 49-prescription base.
  - **Action.** Magdalena notes that responses are broad, so she plans by territory, not by channel.
  - **Eval items** EV-4.3, EV-7.5.
### **P4-Q3 · Did the campaign reach the people it was meant to reach?**
*As Magdalena, I want reach shown next to results, so that high impressions cannot hide low engagement.*
  - **Answer from the data.** Partly. The data has digital impressions and rep calls by territory, product and week: in Southeast's gap, impressions averaged 870 against a median of about 1,774. It has no reach by target segment, no channel spend and no consumer campaigns.
  - **Given** promotion data at territory level only. **When** the brief shows a promotion story. **Then** it puts calls and impressions beside TRx for the same cut and weeks, and says that reach in the target segment cannot be shown yet.
  - **Must not say** "the campaign reached its target HCPs."
  - **Action.** Magdalena asks for channel spend and reach data. The brief tells her this is open (Architecture A16).
  - **Eval items** EV-7.5.
### **P4-Q4 · Is the lift real, or was it access, a competitor or the season?**
*As Magdalena, I want lifts tested against access, competitors and season, so that I never claim credit for a formulary win.*
  - **Answer from the data (weeks of 2025-11-03 to 2025-12-15, Mid-Atlantic).** BXA on the Mid-Atlantic Medicare Part D plan rose 19% (183 to 218 TRx a week) and NBRx 42% against the summer, right after the plan removed prior authorization and step therapy on 2025-11-01. Mid-Atlantic rep calls stayed near 50 a week. National BXA rose 14.4% over the same weeks, so part of the lift is seasonal.
  - **Given** a lift that follows an access restoration and a seasonal rise, with steady promotion. **When** the brief tests promotion. **Then** promotion is "ruled out," access is the leading driver, and the seasonal share is noted.
  - **Must not say** "Q4 promotion lifted Mid-Atlantic."
  - **Action.** Magdalena leaves this lift out of her campaign review.
  - **Eval items** EV-4.5, EV-4.2, EV-3.4.
### **P4-Q5 · How confident is the estimate, and when will we know more?**
*As Magdalena, I want confidence and timing stated plainly, so that early reads don't mislead the budget.*
  - **Answer from the data.** Medium. The Great Lakes estimate rests on one territory and aggregated activity, and is an association. Two things raise it. The second half of that gap overlaps Metacora's launch, but Metacora reached 8.8% to 10.0% of the basket in every territory, so the other territories remain a fair comparison. And the Southeast gap six months later shows the same pattern, about 31 points below other territories. In this data the effect shows in the first week activity changes and fades within one to two weeks after it returns, so a re-read four weeks after any change is enough.
  - **Given** two coverage gaps in different territories and months. **When** the brief reports confidence. **Then** it says Medium, names both cases, and states when the next read is due.
  - **Must not say** "High confidence" from one territory.
  - **Action.** Magdalena waits for the four-week re-read before moving budget.
  - **Eval items** EV-5.1, EV-4.4, EV-7.2.
### **P4-Q6 · Where should the next dollar go?**
*As Magdalena, I want budget arguments grounded in evidence, so that shifts are not argued from anecdote.*
  - **Answer from the data.** The data supports one conclusion: keep promotion running in a territory when coverage lapses. Both gaps cost about 120 to 200 BXA TRx a week relative to other territories and largely recovered when coverage returned. It cannot rank channels or price a dollar, because digital impressions fell along with calls and there is no spend data.
  - **Given** two lapses where calls and digital fell together. **When** the brief writes next steps. **Then** it recommends discussing backfill for open coverage with sales operations, at territory level, and says the rep and digital effects cannot be separated.
  - **Must not say** a cost per incremental prescription, or any rep-level line.
  - **Action.** Magdalena takes the coverage finding into the budget talk with P3 and asks for a digital-only test during the next gap.
  - **Eval items** EV-7.3, EV-9.1.
# **Part B. Forecast-Explanation Agent personas**
The Forecast agent starts from a flagged miss: signed variance V = A − F, actual TRx minus the locked 4-week-ahead forecast, for BXA by territory or NATIONAL. Before Metacora launched, the national forecast ran close to actuals (−0.6% over 72 weeks). From March 2026 it ran 5% to 14% high, so most stories below sit in that stretch.
## **CA · Commercial Analytics Analyst**
The analyst runs and validates the investigation and reviews it before anyone else sees it. These stories test whether the miss is real, where it is, and whether every figure can be checked.
### **CA-Q1 · Is the deviation reliable, or a data issue?**
*As the analyst, I want invalid actuals caught before any driver is named, so that I never explain a miss the data invented.*
  - **Answer from the data (week of 2026-05-04, New England).** The forecast was 440 and the actual 267: V = −173, or −39.3%. But the forecast table marks the actual provisional, and the feed shows why: 44 missing keys, coverage 0.656, late delivery. The national miss that week (−608, −12.3%) is provisional too. A second case: Great Lakes on 2026-07-06 shows an actual of 670 that includes 46 duplicated TRx; without them it is 624.
  - **Given** an InvestigationRequest for a week whose actual is provisional. **When** the agent validates input. **Then** it pauses or qualifies the case, names the feed reasons, and makes no driver claim.
  - **Must not say** "New England missed forecast by 39%."
  - **Action.** The analyst re-queues the case for after the reload. The report tells the analyst which feed to wait for.
  - **Eval items** FE-01, FE-03, FE-02.
### **CA-Q2 · Which regions or segments drive the miss?**
*As the analyst, I want the national miss split by territory, so that a local effect is not hidden in the aggregate.*
  - **Answer from the data (week of 2026-08-24).** National BXA was 4,105 against a forecast of 5,141: V = −1,036 (−20.2%). Every territory missed. Southeast missed most, −343 (−42.2%): a third of the national miss from 16% of the forecast. Then Great Lakes −177, Pacific −127, New England −92, Mid-Atlantic −90, Northwest −88, South Central −70, Mountain −49. The eight sum exactly to the national figure.
  - **Given** a national miss with one territory far worse than the rest. **When** the agent localizes it. **Then** the territory table ties out to the national variance and Southeast leads.
  - **Must not say** "a broad national miss" with no territory split.
  - **Action.** The analyst points the investigation at Southeast first and treats the rest as a broad effect.
  - **Eval items** FE-04, FE-05, FE-06.
### **CA-Q3 · Which candidate drivers merit investigation first?**
*As the analyst, I want candidate events ranked, so that coinciding events are not all treated as causes.*
  - **Answer from the data (within two weeks of 2026-08-24).** Two events are live: a Southeast coverage gap (aggregated rep calls about 19 a week from 2026-08-03 to 2026-08-31, against about 50) and Metacora at 15% of the basket. Three are absent: no BXA access change anywhere, no territory with BXA inventory fill below 0.956, and Labor Day falls two weeks later.
  - **Given** two live events and three absent ones. **When** the agent lists candidates. **Then** it ranks the coverage gap first for Southeast and Metacora first for the broad miss, and lists the absent ones as checked.
  - **Must not say** "access and inventory may also have contributed."
  - **Action.** The analyst approves the order. The report tells the analyst which comparison runs next.
  - **Eval items** FE-07, FE-09, FE-08.
### **CA-Q4 · What supports or contradicts each hypothesis?**
*As the analyst, I want evidence for and against each driver, so that timing alone never decides attribution.*
  - **Answer from the data (weeks of 2026-06-01 to 2026-06-29, Pacific).**
  - **Supports supply.** BXA inventory fill in Pacific ran 0.69 to 0.72 with about 23% backordered. Pacific missed by −1,526 over the five weeks (−39.5%) against −10.2% in other territories. The miss shrank to −8.9% the week supply returned to 1.0.
  - **Contradicts competitor.** Metacora's Pacific share before June (9.2%) was in line with other territories (8.8% to 10.0%).
  - **Contradicts promotion.** Pacific rep calls averaged 54 a week with no vacancy.
  - **Given** a supply drop that starts and ends with the miss. **When** the agent tests hypotheses. **Then** it supports supply, records the competitor and promotion checks that cut against them, and names its comparison group.
  - **Must not say** "Pacific missed because of Metacora."
  - **Action.** The analyst signs off the supply finding.
  - **Eval items** FE-10, FE-11, FE-12.
### **CA-Q5 · How much can credibly be attributed to each driver?**
*As the analyst, I want contributions estimated only where the data can identify them, so that point estimates do not mislead.*
  - **Answer from the data (weeks of 2025-08-04 to 2025-10-27, Mid-Atlantic).** Mid-Atlantic missed by −730 over 13 weeks (−7.4%) while other territories ran −0.4%. Comparing Mid-Atlantic (exposed) with the other seven (control, no access change in that window), about −693 TRx is specific to Mid-Atlantic. Plan-level Rx places it on the one Medicare Part D plan that restricted BXA. The remaining −37 is what the control rate predicts.
  - **Given** an access change on one plan in one territory, with clean controls. **When** the agent attributes. **Then** it reports about −693 for access, the residual, the method and its assumption: no other Mid-Atlantic-only shock in those weeks.
  - **Must not say** "access explains the full −730."
  - **Action.** The analyst includes the estimate with its assumption stated.
  - **Eval items** FE-13, FE-14, FE-16, FE-18.
### **CA-Q6 · Can every finding be verified and reproduced?**
*As the analyst, I want every figure to trace to a tool output on pinned versions, so that I can sign off.*
  - **Answer from the data.** The forecast for 2026-08-24 was issued 2026-07-27 (4-week horizon); that issue week is the version key. In all 104 weeks, territory forecasts and actuals sum exactly to NATIONAL, so any territory split can be checked against the total.
  - **Given** a report on pinned forecast and actual versions. **When** the analyst re-runs the same request. **Then** every figure and its tool record come back identical.
  - **Must not say** a number that comes from the model rather than a tool record.
  - **Action.** The analyst signs off and marks the report reviewed.
  - **Eval items** FE-19, FE-20, FE-21.
## **BM · Brand Manager**
The Brand Manager reads analyst-reviewed explanations and decides what to follow up. These stories test the headline, the ranking of drivers and whether the story can be repeated safely.
### **BM-Q1 · How significant is the miss, and where is it concentrated?**
*As the Brand Manager, I want the size of the miss and where it sits, so that I know which markets matter.*
  - **Answer from the data (weeks of 2026-07-06 to 2026-08-31).** BXA ran 6,090 TRx below forecast over nine weeks, 13.7%. Every territory missed, from −8.4% (Mountain) to −27.2% (Southeast). Southeast holds 30% of the miss with 15% of the forecast; Pacific holds 18%.
  - **Given** a broad miss with one territory far worse. **When** the report's headline is written. **Then** it gives the size in TRx and percent, says the miss is broad, and names Southeast as the concentration.
  - **Must not say** "Southeast drove the miss" as if the rest were on plan.
  - **Action.** The Brand Manager treats it as a national issue with one local hotspot.
  - **Eval items** FE-04, FE-05, FE-24.
### **BM-Q2 · What are the most plausible commercial drivers?**
*As the Brand Manager, I want drivers ranked, so that a list of events turns into priorities.*
  - **Answer from the data.**
1.  **Metacora launch, broad.** BXA's share of the basket fell from 35.4% (February) to 30.9% (Aug 17 to Sep 7), a 12.7% relative loss. That matches the broad miss: the national forecast, built before launch, ran 12.7% to 13.7% high in May to August.
2.  **Southeast coverage gap, local.** Southeast missed 27.2% over the nine weeks while its aggregated rep calls fell by about 60% in August.
3.  **Ruled out for this period:** access (no BXA change since 2025) and supply (all BXA fill above 0.95 in August).
  - **Given** one broad and one local driver plus two ruled-out ones. **When** the report ranks drivers. **Then** each is labelled supported, plausible or insufficient evidence, with its scope.
  - **Must not say** "Metacora caused the miss" without the share evidence and its assumption.
  - **Action.** The Brand Manager sets the competitive response as the first priority.
  - **Eval items** FE-07, FE-09, FE-25.
### **BM-Q3 · How much of the miss does each driver explain?**
*As the Brand Manager, I want a defensible split of the miss, so that resources follow the size of each cause.*
*(Chart in the Google Doc; not reproduced here.)*
Computed from forecast_vs_actual_weekly and v_reportable_rx · week of 2026-08-24
  - **Answer from the data (week of 2026-08-24).** Forecast 5,141, actual 4,105, miss −1,036. Each step uses its own comparison:
  - **Usual bias, −32.** Before launch the national forecast ran 0.6% high on average.
  - **Metacora share gain, −655.** BXA's 12.7% relative share loss since February, applied to the forecast. Assumes the basket would otherwise have matched the forecast.
  - **Southeast coverage gap, −204.** Southeast's miss beyond the rate seen in the six territories with no other event that week.
  - **Unexplained residual, −145,** about 14% of the miss.
  - **Given** a miss with one broad and one local driver. **When** the report attributes. **Then** contributions plus the residual equal the miss, each step names its method, and the residual is shown, not spread across drivers.
  - **Must not say** a split with no residual.
  - **Action.** The Brand Manager sizes the response: competitive defense first, Southeast coverage second.
  - **Eval items** FE-13, FE-16, FE-18.
### **BM-Q4 · How confident are we, and what remains unknown?**
*As the Brand Manager, I want findings separated from hypotheses, so that leadership hears the right level of certainty.*
  - **Answer from the data.** Metacora: medium. The share loss is measured, but turning it into TRx assumes basket volume held to forecast. Southeast: medium to high. The comparison territories are clean, and the gap narrowed sharply when coverage returned in September. Unknown: the −145 residual, and a separate South Central gap in September (−249 TRx beyond other territories) with no visible driver.
  - **Given** drivers of different strength. **When** the report states confidence. **Then** it labels each driver's confidence and lists the open unknowns.
  - **Must not say** one confidence level for the whole explanation.
  - **Action.** The Brand Manager reports two findings and one open question.
  - **Eval items** FE-17, FE-18, FE-25.
### **BM-Q5 · What should be checked next, and by which team?**
*As the Brand Manager, I want each follow-up tied to an owner, so that the diagnosis turns into action.*
  - **Answer from the data.**
  - **Forecasting:** review the competitor assumption; the post-launch gap has lasted since March.
  - **Sales leadership:** confirm Southeast coverage is restored; calls returned to about 60 a week on 2026-09-07.
  - **Commercial analytics:** split the residual and the South Central gap by plan and specialty.
  - **Market access:** none; no BXA access change in this period.
  - **Given** two drivers and a residual. **When** the report writes follow-ups. **Then** each has a concrete check, an owner and the evidence behind it.
  - **Must not say** "monitor the situation."
  - **Action.** The Brand Manager sends each check to its owner.
  - **Eval items** FE-22.
### **BM-Q6 · Can the explanation be communicated defensibly?**
*As the Brand Manager, I want wording I can repeat without overclaiming, so that the business is not exposed.*
  - **Answer from the data.** A defensible version: "BXA was 20% below forecast in the week of August 24. About two-thirds of the gap matches Metacora's share gain since launch. The Southeast coverage gap explains about one-fifth. About one-seventh is not explained yet."
  - **Given** the split above. **When** the report writes its summary. **Then** it uses "matches" and "explains about," never "caused," and keeps the unexplained part in the sentence.
  - **Must not say** "Metacora caused a 655-prescription loss."
  - **Action.** The Brand Manager uses the summary in the leadership update.
  - **Eval items** FE-24, FE-25.
## **FM · Forecasting Manager**
The Forecasting Manager reviews misses with analytics, brand and Finance and decides whether forecast assumptions deserve review. These stories test arithmetic, residuals and restraint.
### **FM-Q1 · What is the absolute and percentage forecast miss?**
*As the Forecasting Manager, I want the miss stated against the locked version with one denominator, so that performance is not obscured.*
  - **Answer from the data (week of 2026-08-24, NATIONAL).** The forecast issued 2026-07-27 (4 weeks ahead) was 5,141. The actual was 4,105. V = −1,036, or −20.2% of forecast. Every row in the release uses the same 4-week horizon.
  - **Given** a locked forecast and a final actual. **When** the report states the miss. **Then** it gives V in TRx and as a percent of forecast, names the issue week, and keeps the sign.
  - **Must not say** "a 25% shortfall" (the miss divided by the actual instead of the forecast).
  - **Action.** The Forecasting Manager logs the miss against forecast version 2026-07-27.
  - **Eval items** FE-04, FE-02.
### **FM-Q2 · Which commercial drivers plausibly contributed?**
*As the Forecasting Manager, I want the competing explanations for the 2026 misses laid out, so that one forecast error is not pinned on one cause.*
  - **Answer from the data (March to October 2026).** One broad driver and three local ones. Broad: Metacora's launch on 2026-03-02, which the forecast leaves out by design (the data README says it excludes unplanned launch, payer, promotion and inventory shocks). Local: the Great Lakes coverage gap (February to April), the Pacific supply shortfall (June) and the Southeast coverage gap (August).
  - **Given** a period with overlapping broad and local events. **When** the report lists drivers. **Then** each has a scope (national or territory), dates and a verdict.
  - **Must not say** "the forecast was wrong" without separating planned assumptions from unplanned shocks.
  - **Action.** The Forecasting Manager separates the broad driver (an assumption question) from local shocks (not forecastable).
  - **Eval items** FE-07, FE-10.
### **FM-Q3 · What portion remains unexplained?**
*As the Forecasting Manager, I want the unexplained part kept visible, so that a fully allocated miss does not imply false certainty.*
  - **Answer from the data (weeks of 2026-08-31 to 2026-09-28, South Central).** South Central missed by −701 over five weeks (−19.8%) while other territories missed by 12.8%: about −249 TRx beyond the broad rate. No context table offers a driver: rep calls normal, no vacancy, no access restriction, inventory fill at or above 0.968, feeds clean.
  - **Given** a territory gap with no visible driver. **When** the report attributes. **Then** the −249 stays an unexplained residual and the report says so.
  - **Must not say** a split that allocates the −249 to Metacora or anything else.
  - **Action.** The Forecasting Manager carries the residual into the monthly review as an open item.
  - **Eval items** FE-16, FE-17, FE-18.
### **FM-Q4 · Are contributions supported by suitable comparisons?**
*As the Forecasting Manager, I want every estimate to name its comparison group and why it is valid, so that weak controls don't produce spurious numbers.*
  - **Answer from the data.**
  - **A valid control despite overlap.** The Great Lakes coverage gap overlaps Metacora's launch from 2026-03-02. Because Metacora reached 8.8% to 10.0% of the basket in every territory, the other seven still make a fair control. Great Lakes ran about −644 TRx beyond them before launch (four weeks) and −911 after it (six weeks).
  - **A contaminated control.** In June 2026, New England missed by 11.0%. Against other territories including Pacific (−15.4%, pulled down by Pacific's supply shortfall), New England looks 4.4 points better than its peers. Against a control without Pacific (−10.2%) it is in line.
  - **Given** a comparison window where one control territory had its own shock. **When** the agent picks controls. **Then** it drops that territory, says why, and lowers confidence if too few controls remain.
  - **Must not say** "New England outperformed peers in June."
  - **Action.** The Forecasting Manager accepts estimates only where the control is named and justified.
  - **Eval items** FE-12, FE-10, FE-15.
### **FM-Q5 · Should any forecast assumptions be reviewed?**
*As the Forecasting Manager, I want a review trigger, not an automatic edit, so that systematic errors are separated from one-off shocks.*
  - **Answer from the data.** Yes, the competitor assumption. Before launch the national forecast ran 0.6% high over 72 weeks. After launch it ran 5.4% high in March and April, 12.7% in May and June, 13.7% in July and August, and 12.4% from September to October 5. The gap is persistent, broad and matches BXA's share loss to Metacora.
  - **Given** a persistent, broad miss that starts with a launch the forecast leaves out. **When** the report concludes. **Then** it recommends reviewing the competitor assumption, with the evidence, and changes no forecast itself.
  - **Must not say** a revised forecast figure, or "the forecast has been updated."
  - **Action.** The Forecasting Manager puts the competitor assumption on the next forecast review agenda with Finance.
  - **Eval items** FE-23, FE-22.
### **FM-Q6 · Is the explanation auditable and reconciled?**
*As the Forecasting Manager, I want arithmetic Finance can check line by line, so that the review rests on source-linked numbers.*
  - **Answer from the data.** For 2026-08-24 the split in BM-Q3 reconciles: −32 − 655 − 204 − 145 = −1,036. In all 104 weeks, territory forecasts and actuals sum exactly to NATIONAL.
  - **Given** a report with driver contributions and a residual. **When** Finance checks it. **Then** contributions plus residual equal V within the stated tolerance, and each figure opens its tool record.
  - **Must not say** a contribution with no tool record behind it.
  - **Action.** The Forecasting Manager forwards the reconciled report to Finance.
  - **Eval items** FE-16, FE-20, FE-06.
# **Coverage and gaps**
## **Coverage: question to anchor, eval items and stage**
All 42 persona questions have a story on real data. Stages follow the System Architecture doc: 3a and 4a are the Briefing lane, 3b and 4b the Forecast lane.
| Question | Anchor in the data | Eval items | Stage |
| :- | :- | :- | :- |
| P1-Q1 | Great Lakes duplicates, 2026-07-06 | EV-1.1, EV-2.1, EV-2.3 | 2, 6 |
| P1-Q2 | New England incomplete feed, 2026-05-04 | EV-2.1, EV-2.3, EV-1.1 | 2 |
| P1-Q3 | Quiet week, 2025-04-21 | EV-3.2, EV-3.3 | 3a |
| P1-Q4 | Mid-Atlantic access change, Aug to Oct 2025 | EV-6.1, EV-6.2, EV-6.3 | 6, 7 |
| P1-Q5 | Pacific supply plus Metacora, 2026-06-08 | EV-3.1, EV-3.3 | 3a, 4a |
| P1-Q6 | Draft for 2026-08-24 | EV-8.1, EV-7.4, EV-9.2 | 5, 7 |
| P2-Q1 | Mid-Atlantic cut withheld, 2026-04-06 | EV-2.2, EV-2.1, EV-3.2 | 2, 4a |
| P2-Q2 | Mid-Atlantic access change | EV-4.1, EV-4.2, EV-5.1 | 4a |
| P2-Q3 | South Central gap, Sep 2026 | EV-5.1, EV-5.2, EV-5.3 | 4a, 6 |
| P2-Q4 | Mid-Atlantic access change | EV-4.3, EV-3.1 | 4a |
| P2-Q5 | Mid-Atlantic restatement, 692 to 742 | EV-6.2, EV-1.2 | 1, 6 |
| P2-Q6 | Held-out stretch with artifacts and holidays | EV-8.2 to EV-8.5 | Cross-cutting |
| P3-Q1 | Metacora at 8 weeks, 2026-04-27 | EV-3.1, EV-3.3 | 3a |
| P3-Q2 | Holiday weeks, Dec 2025 | EV-3.4, EV-3.2 | 3a |
| P3-Q3 | Pacific supply, Jun 2026 | EV-7.1 | 5 |
| P3-Q4 | Metacora at 31 weeks, 2026-09-28 | EV-7.2 | 4a, 5 |
| P3-Q5 | Southeast coverage gap, Aug 2026 | EV-7.3, EV-9.1 | 5, 6 |
| P3-Q6 | Restatement disclosed, 2026-07-13 | EV-1.1, EV-1.2 | 2, 5, 6 |
| P4-Q1 | Great Lakes coverage gap, Feb to Apr 2026 | EV-4.5, EV-4.1 | 4a |
| P4-Q2 | Great Lakes and Southeast splits | EV-4.3, EV-7.5 | 4a, 5 |
| P4-Q3 | Impressions without reach data | EV-7.5 | 5 |
| P4-Q4 | Mid-Atlantic rebound, Nov to Dec 2025 | EV-4.5, EV-4.2, EV-3.4 | 4a |
| P4-Q5 | Great Lakes and Southeast together | EV-5.1, EV-4.4, EV-7.2 | 4a |
| P4-Q6 | Great Lakes and Southeast together | EV-7.3, EV-9.1 | 5, 6 |
| CA-Q1 | New England 2026-05-04; Great Lakes 2026-07-06 | FE-01, FE-03, FE-02 | 2, 4b |
| CA-Q2 | National miss, 2026-08-24 | FE-04, FE-05, FE-06 | 3b, 4b |
| CA-Q3 | Candidates around 2026-08-24 | FE-07, FE-09, FE-08 | 4b |
| CA-Q4 | Pacific supply, Jun 2026 | FE-10, FE-11, FE-12 | 4b |
| CA-Q5 | Mid-Atlantic access, Aug to Oct 2025 | FE-13, FE-14, FE-16, FE-18 | 4b, 6 |
| CA-Q6 | Version 2026-07-27 for 2026-08-24 | FE-19, FE-20, FE-21 | 1, 6 |
| BM-Q1 | Jul to Aug 2026 | FE-04, FE-05, FE-24 | 3b, 5 |
| BM-Q2 | Mar to Sep 2026 | FE-07, FE-09, FE-25 | 4b |
| BM-Q3 | Waterfall, 2026-08-24 | FE-13, FE-16, FE-18 | 4b, 6 |
| BM-Q4 | 2026-08-24 and South Central | FE-17, FE-18, FE-25 | 4b, 5 |
| BM-Q5 | Follow-ups for 2026-08-24 | FE-22 | 5 |
| BM-Q6 | Summary for 2026-08-24 | FE-24, FE-25 | 5, 6 |
| FM-Q1 | National miss, 2026-08-24 | FE-04, FE-02 | 1, 3b |
| FM-Q2 | Mar to Oct 2026 | FE-07, FE-10 | 4b |
| FM-Q3 | South Central gap, Sep 2026 | FE-16, FE-17, FE-18 | 4b, 6 |
| FM-Q4 | Great Lakes overlap; New England in June | FE-12, FE-10, FE-15 | 4b |
| FM-Q5 | Post-launch bias, Mar to Oct 2026 | FE-23, FE-22 | 5 |
| FM-Q6 | Reconciliation, 2026-08-24 | FE-16, FE-20, FE-06 | 6 |

## **What the data cannot answer yet**
The release answers most questions, but seven gaps limit the stories. Each points to an open item already logged elsewhere.
| Gap | Stories affected | Open item |
| :- | :- | :- |
| No answer key in the repo, so no story can confirm the injected truth | All | Evaluation Pack 8 |
| The validation report counts 6 seeded business events; 5 show a driver in the context tables (Mid-Atlantic access, Metacora launch, Great Lakes and Southeast coverage gaps, Pacific supply). The South Central gap in September 2026 shows none: it may be the sixth event or noise | P2-Q3, BM-Q4, FM-Q3 | Answer key decides |
| No reach by target segment, channel spend or consumer campaigns; rep and digital effects cannot be separated | P4-Q3, P4-Q6 | Architecture A16 |
| No geography below territory (no NY metro boroughs) | P4-Q2 | Architecture A17 |
| Mid-Atlantic was restated 14 weeks after the fact, against a proposed 3-week refresh window. The forecast table carries the revised actual (742) with no provisional flag | P2-Q5, P3-Q6, CA-Q1 | System S4; Evaluation Pack 18 |
| Edit burden and time saved come from timed runs, not data | P1-Q6, P2-Q6 | Evaluation Pack 6 (gold briefs) |
| Some eval items match no persona question: EV-2.4, EV-5.4, EV-9.3, EV-9.4 and FE-26 to FE-31 | None | Covered by stress and governance cases |

**Next step for Spec Kit.** Each Given / When / Then above pastes into a spec's acceptance scenarios as written. A spec cites the story ID (for example P2-Q2) and its eval items, and the anchor week becomes a dev test case.
